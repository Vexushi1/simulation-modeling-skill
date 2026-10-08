"""Resolve Phase A/B/C intents without writing files or granting business execution."""
from __future__ import annotations

import argparse
from pathlib import Path

from runtime_common import ROOT, emit, load_contract, load_document


def resolve_runtime(intent, *, profile_path=None, state_path=None,
                    required_operations=None, expected_root=None, problem_path=None,
                    model_path=None, approval_path=None) -> dict:
    router = load_contract("core/workflow_router.yaml")
    taxonomy = load_contract(router["capability_taxonomy"])["capabilities"]
    manifest = load_contract(router["module_manifest"])["modules"]
    result = {
        "intent": intent,
        "phase": "A",
        "status": "invalid",
        "execution_allowed": False,
        "business_execution_allowed": False,
        "execution_scope": "none",
        "activated_modules": [],
        "activated_resources": [],
        "activated_packs": [],
        "upstream_skills": [],
        "selected_operations": [],
        "required_gates": [],
        "missing_gates": [],
        "expected_artefacts": [],
        "fallback": None,
        "next_step": "Use inspect, assure_environment, or a declared capability intent.",
        "errors": [],
        "state_mutated": False,
        "profile_sha256": None,
        "receipt_sha256": None,
        "problem_contract_sha256": None,
        "model_contract_sha256": None,
        "model_approval_sha256": None,
    }
    if not isinstance(intent, str) or (intent not in router["intents"] and intent not in taxonomy):
        result["errors"] = [f"unknown intent: {intent}"]
        return result

    if required_operations is not None and (
        not isinstance(required_operations, (list, tuple)) or
        not all(isinstance(operation, str) for operation in required_operations)
    ):
        result["errors"] = ["required_operations must be an array of operation identifiers"]
        return result
    requested = list(required_operations or [])
    runtime_contract = load_contract(router["runtime_contract"])
    unknown_operations = [op for op in requested
                          if not isinstance(op, str) or op not in runtime_contract["operations"]]
    if unknown_operations:
        result["errors"] = [f"unknown operation: {op}" for op in unknown_operations]
        return result

    current_stage = None
    state_result = None
    if state_path is not None:
        from validate_project_state import validate_project_state

        scope = router["intents"].get(intent, {}).get("state_validation_scope", "all")
        state_result = validate_project_state(state_path, profile_path=profile_path, scope=scope)
        result["state_validation"] = state_result
        if not state_result["valid"]:
            result.update(status="blocked", missing_gates=["project_state_valid"],
                          errors=state_result["errors"],
                          fallback=router["fallback"]["invalid_project_state"],
                          next_step="Repair the project state and its bound evidence before retrying.")
            return result
        current_stage = state_result.get("current_stage")
        if current_stage is None:
            current_stage = load_document(Path(state_path))["current_stage"]

    if intent in taxonomy and intent not in router["intents"]:
        phase = taxonomy[intent]["phase"]
        policy = router["future_capabilities"]
        gates = [gate.replace("requested_capability", intent)
                 for gate in policy["common_missing_gates"]]
        gates += policy["prerequisite_gates_by_phase"].get(phase, [])
        satisfied = set()
        if state_result and state_result.get("problem_validation", {}).get("frozen"):
            satisfied.add("problem_contract_frozen")
        if (state_result and state_result.get("model_checked") and
                state_result.get("model_approved") and
                state_result.get("model_validation", {}).get("approved")):
            satisfied.add("model_design_approved")
        missing = [gate for gate in gates if gate not in satisfied]
        result.update(status="deferred", phase=phase, required_gates=gates,
                      missing_gates=missing,
                      fallback=router["fallback"]["future_capability"],
                      next_step=policy["next_step_template"].format(phase=phase),
                      errors=[f"{intent} is not implemented in Phase A/B/C (declared Phase {phase})"])
        return result

    route = router["intents"][intent]
    module_id = route["module"]
    module = manifest.get(module_id, {})
    resources = module.get("resources", [])
    missing_resources = [path for path in resources if not (ROOT / path).is_file()]
    if module.get("status") != "implemented" or not resources or missing_resources:
        result.update(status="blocked", missing_gates=[f"{module_id}_module_implemented"],
                      errors=[f"{module_id} module resources unavailable: {missing_resources}"],
                      next_step=f"Complete the declared {module_id} module before routing this intent.")
        return result

    result.update(phase=route.get("phase", "A"), required_gates=list(route["required_gates"]),
                  expected_artefacts=list(route["expected_artefacts"]),
                  next_step=route["next_step"])
    if intent == "inspect":
        result.update(status="inspected", activated_modules=[module_id],
                      activated_resources=list(resources))
        return result

    if intent == "problem_audit":
        result.update(execution_scope="problem_audit", activated_modules=[module_id],
                      activated_resources=list(resources))
        bound_problem = state_result.get("problem_path") if state_result else None
        if bound_problem and problem_path is not None and Path(problem_path).resolve() != Path(bound_problem):
            result.update(status="blocked", missing_gates=["problem_state_binding_matches"],
                          errors=["requested problem contract differs from project-state binding"],
                          fallback=router["fallback"]["problem_contract_invalid"])
            return result
        selected_problem = problem_path if problem_path is not None else bound_problem
        if selected_problem is None:
            result.update(status="allowed", next_step="Create a draft from the problem-contract template and preserve unknown information; no audit or freeze is established.")
            result["missing_gates"] = ["problem_contract_supplied", "problem_audit_complete", "problem_contract_frozen"]
            return result
        from validate_problem_contract import validate_problem_contract

        project_root = state_result.get("project_root") if state_result else None
        validation = validate_problem_contract(selected_problem, project_root=project_root)
        result["problem_validation"] = validation
        result["problem_contract_sha256"] = validation["contract_sha256"]
        if state_path is not None and validation["project_id"] is not None:
            if validation["project_id"] != load_document(Path(state_path))["project_id"]:
                result.update(status="blocked", missing_gates=["problem_project_id_matches"],
                              errors=["problem contract project_id differs from project state"],
                              fallback=router["fallback"]["problem_contract_invalid"])
                return result
        if not validation["valid"]:
            result.update(status="blocked", missing_gates=list(validation["missing_gates"]) or ["problem_contract_valid"],
                          errors=validation["errors"] or ["problem contract validation failed"],
                          fallback=router["fallback"]["problem_contract_invalid"],
                          next_step=router["fallback"]["problem_contract_invalid"]["reason"])
            return result
        result.update(status="inspected", missing_gates=list(validation["missing_gates"]))
        return result

    if intent == "model_design":
        result.update(execution_scope="model_design", activated_modules=[module_id],
                      activated_resources=list(resources))
        bound_problem = state_result.get("problem_path") if state_result else None
        bound_model = state_result.get("model_path") if state_result else None
        bound_approval = state_result.get("approval_path") if state_result else None
        for supplied, bound, label in ((problem_path, bound_problem, "problem"),
                                       (model_path, bound_model, "model"),
                                       (approval_path, bound_approval, "approval")):
            if bound and supplied is not None and Path(supplied).resolve() != Path(bound):
                result.update(status="blocked", missing_gates=[f"{label}_state_binding_matches"],
                              errors=[f"requested {label} differs from project-state binding"],
                              fallback=router["fallback"]["model_contract_invalid"])
                return result
        selected_problem = problem_path if problem_path is not None else bound_problem
        selected_model = model_path if model_path is not None else bound_model
        selected_approval = approval_path if approval_path is not None else bound_approval
        project_root = state_result.get("project_root") if state_result else None
        model_validation = None
        if selected_model is not None:
            from validate_model_contract import validate_model_contract

            model_validation = validate_model_contract(
                selected_model, project_root=project_root, problem_path=selected_problem,
                approval_path=selected_approval)
            result["model_validation"] = model_validation
            result["model_contract_sha256"] = model_validation["contract_sha256"]
            result["model_approval_sha256"] = model_validation.get("approval_sha256")
            if not model_validation["valid"]:
                result.update(status="blocked", errors=model_validation["errors"] or ["model contract validation failed"],
                              missing_gates=list(model_validation["missing_gates"]) or ["model_contract_valid"],
                              fallback=router["fallback"]["model_contract_invalid"],
                              next_step=router["fallback"]["model_contract_invalid"]["reason"])
                return result
            if selected_problem is None:
                selected_problem = model_validation.get("problem_path")
            if state_path is not None and model_validation["project_id"] != load_document(Path(state_path))["project_id"]:
                result.update(status="blocked", missing_gates=["model_project_id_matches"],
                              errors=["model contract project_id differs from project state"],
                              fallback=router["fallback"]["model_contract_invalid"])
                return result
        elif selected_approval is not None:
            result.update(status="blocked", missing_gates=["model_contract_supplied"],
                          errors=["an approval cannot replace the current model contract"],
                          fallback=router["fallback"]["model_contract_invalid"])
            return result
        if selected_problem is None:
            result.update(status="blocked", missing_gates=["problem_contract_frozen"],
                          errors=["model design requires the current frozen problem contract"],
                          fallback=router["fallback"]["problem_contract_invalid"],
                          next_step="Complete the problem audit and its recorded freeze review before model design.")
            return result
        from validate_problem_contract import validate_problem_contract

        problem_validation = validate_problem_contract(
            selected_problem, require_frozen=True, project_root=project_root)
        result["problem_validation"] = problem_validation
        result["problem_contract_sha256"] = problem_validation["contract_sha256"]
        if not problem_validation["valid"] or not problem_validation["frozen"]:
            result.update(status="blocked", missing_gates=["problem_contract_frozen"],
                          errors=problem_validation["errors"] or ["problem contract is not currently frozen"],
                          fallback=router["fallback"]["problem_contract_invalid"],
                          next_step="Review the problem sources and record the necessary freeze decision before model design.")
            return result
        if state_path is not None and problem_validation["project_id"] != load_document(Path(state_path))["project_id"]:
            result.update(status="blocked", missing_gates=["problem_project_id_matches"],
                          errors=["problem contract project_id differs from project state"],
                          fallback=router["fallback"]["problem_contract_invalid"])
            return result
        if model_validation is None:
            result.update(status="allowed", missing_gates=["model_contract_supplied", "model_proposal_complete",
                                                           "model_challenge_complete", "human_model_approval_current"],
                          next_step="Create a mathematical model draft from the current frozen problem, then prepare the challenge review and human approval brief.")
        else:
            result.update(status="inspected", missing_gates=list(model_validation["missing_gates"]))
        return result

    selected = list(dict.fromkeys(module["required_operations"] + requested))
    result["selected_operations"] = selected
    if profile_path is None:
        result.update(status="blocked", missing_gates=["capability_profile_current"],
                      errors=["a repository-probed capability profile is required"],
                      fallback=router["fallback"]["missing_or_stale_profile"],
                      next_step="Run the repository probe in a new directory, then supply --profile.")
        return result

    from validate_environment import validate_environment

    assurance = validate_environment(profile_path, required_operations=selected,
                                     expected_root=expected_root)
    result["environment_validation"] = assurance
    if not (assurance["valid"] and assurance["runtime_assured"] and assurance["profile_current"]):
        missing = []
        if not assurance["profile_current"]:
            missing.append("capability_profile_current")
        if not assurance["valid"] or not assurance["runtime_assured"]:
            missing.append("requested_operations_qualified")
        optional_only = (assurance["runtime_assured"] and assurance["profile_current"]
                         and any(op not in module["required_operations"] for op in selected))
        fallback_key = "optional_operation_unavailable" if optional_only else "missing_or_stale_profile"
        result.update(status="blocked", missing_gates=missing,
                      errors=assurance["errors"], fallback=router["fallback"][fallback_key],
                      next_step=router["fallback"][fallback_key]["reason"])
        return result

    result.update(status="allowed", execution_allowed=True,
                  execution_scope="environment_assurance",
                  activated_modules=[module_id], activated_resources=list(resources),
                  profile_sha256=assurance["profile_sha256"],
                  receipt_sha256=assurance["receipt_sha256"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intent", required=True)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--problem", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--require-operation", action="append", default=[])
    parser.add_argument("--matlab-root", type=Path)
    args = parser.parse_args()
    try:
        result = resolve_runtime(args.intent, profile_path=args.profile, state_path=args.state,
                                 required_operations=args.require_operation,
                                 expected_root=args.matlab_root, problem_path=args.problem,
                                 model_path=args.model, approval_path=args.approval)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {"status": "blocked", "execution_allowed": False,
                  "business_execution_allowed": False, "errors": [str(error)]}
    emit(result)
    return 0 if result["status"] in ("inspected", "allowed", "deferred") else 1


if __name__ == "__main__":
    raise SystemExit(main())
