"""Resolve A through G gates without writing project state."""
from __future__ import annotations

import argparse
from pathlib import Path

from runtime_common import ROOT, emit, load_contract, load_document

IMPLEMENTATION_OPERATION = "simulink.core_build_structure"


def _implementation_route(result, *, router, module_id, resources, state_result, state_path,
                          profile_path, implementation_profile_path, problem_path, model_path,
                          approval_path, mapping_path, requested, expected_root):
    """Text review and native construction have separate evidence and permissions."""
    intent = result["intent"]
    fallback = router["fallback"]["mapping_contract_invalid"]
    if intent == "domain_mapping":
        result.update(execution_scope="domain_mapping", activated_modules=[module_id],
                      activated_resources=list(resources))

    def block(gates, errors, *, selected_fallback=None):
        selected_fallback = selected_fallback or fallback
        result.update(status="blocked", missing_gates=gates, errors=errors,
                      fallback=selected_fallback, next_step=selected_fallback["reason"])
        return result

    selected = {}
    for supplied, label in ((problem_path, "problem"), (model_path, "model"),
                            (approval_path, "approval"), (mapping_path, "mapping")):
        bound = state_result.get(f"{label}_path") if state_result else None
        if bound and supplied is not None and Path(supplied).resolve() != Path(bound):
            return block([f"{label}_state_binding_matches"],
                         [f"requested {label} differs from project-state binding"])
        selected[label] = supplied if supplied is not None else bound
    project_root = state_result.get("project_root") if state_result else None
    mapping_report = None
    if selected["mapping"] is not None:
        from validate_domain_mapping import validate_domain_mapping

        mapping_report = validate_domain_mapping(selected["mapping"], project_root=project_root)
        result.update(mapping_validation=mapping_report,
                      mapping_path=str(Path(selected["mapping"]).resolve()),
                      mapping_contract_sha256=mapping_report["contract_sha256"],
                      mapping_semantic_sha256=mapping_report.get("semantic_sha256"),
                      parameters_sha256=mapping_report.get("parameters_sha256"),
                      build_spec_sha256=mapping_report.get("build_spec_sha256"))
        if not mapping_report["valid"]:
            return block(mapping_report["missing_gates"] or ["mapping_contract_valid"],
                         mapping_report["errors"] or ["mapping contract is invalid"])
        mapped_model = mapping_report.get("model_path")
        if mapped_model:
            if selected["model"] is not None and Path(selected["model"]).resolve() != Path(mapped_model):
                return block(["model_mapping_binding_matches"],
                             ["requested model differs from the mapping binding"])
            selected["model"] = mapped_model
    if selected["model"] is None:
        return block(["model_design_approved"], ["D requires the current complete approved model contract"],
                     selected_fallback=router["fallback"]["model_contract_invalid"])
    from validate_model_contract import validate_model_contract

    model_report = validate_model_contract(
        selected["model"], project_root=project_root, problem_path=selected["problem"],
        approval_path=selected["approval"], require_approved=True)
    result.update(model_validation=model_report,
                  model_contract_sha256=model_report["contract_sha256"],
                  model_approval_sha256=model_report.get("approval_sha256"),
                  problem_contract_sha256=model_report.get("problem_sha256"))
    if "problem_validation" in model_report:
        result["problem_validation"] = model_report["problem_validation"]
    if not model_report["valid"] or not model_report["approved"]:
        return block(["model_design_approved"], model_report["errors"] or ["current human model approval is missing"],
                     selected_fallback=router["fallback"]["model_contract_invalid"])
    if state_path is not None and model_report["project_id"] != load_document(Path(state_path))["project_id"]:
        return block(["model_project_id_matches"], ["model project_id differs from project state"])
    if mapping_report is not None:
        if (mapping_report["project_id"] != model_report["project_id"] or
                (mapping_report.get("model_path") and
                 mapping_report.get("model_sha256") != model_report["contract_sha256"])):
            return block(["mapping_model_binding_matches"], ["mapping differs from the current approved model identity"])
    if intent == "domain_mapping":
        if mapping_report is None:
            result.update(status="allowed", missing_gates=["mapping_contract_supplied", "mapping_complete"],
                          next_step="Prepare a mapping and parameter draft from the current approved design; preserve unknown values and unsupported domains.")
        else:
            result.update(status="inspected", missing_gates=list(mapping_report["missing_gates"]))
        return result
    if mapping_report is None or not mapping_report["build_ready"]:
        missing = ["mapping_contract_build_ready"]
        if mapping_report is not None:
            missing += list(mapping_report["missing_gates"])
        return block(list(dict.fromkeys(missing)),
                     ["native construction requires a complete mapping within the supported core block and parameter scope"])

    # A and D qualification are independent; neither can replace the other.
    selected_profiles = {}
    for supplied, label in ((profile_path, "environment"),
                            (implementation_profile_path, "implementation_environment")):
        bound = state_result.get(f"{label}_path") if state_result else None
        if bound and supplied is not None and Path(supplied).resolve() != Path(bound):
            return block([f"{label}_state_binding_matches"],
                         [f"requested {label} profile differs from project-state binding"])
        selected_profiles[label] = supplied if supplied is not None else bound
    profile_path = selected_profiles["environment"]
    implementation_profile_path = selected_profiles["implementation_environment"]
    operations = list(dict.fromkeys(load_contract("core/runtime_assurance_contract.yaml")["core_operations"]
                                   + [IMPLEMENTATION_OPERATION] + requested))
    result["selected_operations"] = operations
    if profile_path is None:
        return block(["capability_profile_current"], ["a current A runtime profile is required for native construction"],
                     selected_fallback=router["fallback"]["missing_or_stale_profile"])
    from validate_environment import _path, validate_environment

    assurance = validate_environment(profile_path, expected_root=expected_root,
                                     required_operations=[op for op in operations if op != IMPLEMENTATION_OPERATION])
    result["environment_validation"] = assurance
    if not (assurance["valid"] and assurance["runtime_assured"] and assurance["profile_current"]):
        return block(["capability_profile_current", "requested_operations_qualified"], assurance["errors"],
                     selected_fallback=router["fallback"]["missing_or_stale_profile"])
    if implementation_profile_path is None:
        return block(["implementation_profile_current"], ["the independent D operation profile is required"],
                     selected_fallback=router["fallback"]["implementation_profile_invalid"])
    from validate_implementation_profile import validate_implementation_profile

    native = validate_implementation_profile(implementation_profile_path, expected_root=expected_root)
    result["implementation_environment_validation"] = native
    if not (native["valid"] and native["profile_current"] and native["implementation_assured"] and
            IMPLEMENTATION_OPERATION in native["qualified_operations"]):
        return block(["implementation_profile_current", "simulink_core_build_structure_qualified"], native["errors"],
                     selected_fallback=router["fallback"]["implementation_profile_invalid"])
    runtime_fields = ("release", "version", "matlabroot", "executable", "executable_sha256",
                      "version_file_sha256", "platform")
    a_runtime = load_document(Path(profile_path))["runtime"]
    if any((_path(a_runtime[key]) != _path(native["runtime"][key])
            if key in {"matlabroot", "executable"} else a_runtime.get(key) != native["runtime"].get(key))
           for key in runtime_fields):
        return block(["implementation_runtime_matches"], ["A and D profiles describe different runtime installations"],
                     selected_fallback=router["fallback"]["implementation_profile_invalid"])
    if state_path is not None:
        state = load_document(Path(state_path))
        for label, validation in (("environment", assurance), ("implementation_environment", native)):
            binding = state.get(label)
            if binding and any(binding[key] != validation.get(key) for key in ("profile_sha256", "receipt_sha256")):
                return block([f"{label}_state_binding_matches"], [f"{label} evidence differs from project-state SHA bindings"])
    result.update(status="allowed", missing_gates=[], execution_allowed=True,
                  implementation_execution_allowed=True, execution_scope="implementation_execution",
                  activated_modules=[module_id], activated_resources=list(resources),
                  profile_sha256=assurance["profile_sha256"], receipt_sha256=assurance["receipt_sha256"],
                  implementation_profile_path=str(Path(implementation_profile_path).resolve()),
                  implementation_profile_sha256=native["profile_sha256"],
                  implementation_receipt_sha256=native["receipt_sha256"])
    return result


def resolve_runtime(intent, *, profile_path=None, state_path=None,
                    required_operations=None, expected_root=None, problem_path=None,
                    model_path=None, approval_path=None, mapping_path=None,
                    implementation_profile_path=None, protocol_path=None,
                    simulation_profile_path=None, run_receipt_path=None, study_path=None,
                    parameter_study_profile_path=None, parameter_trial_receipt_path=None,
                    design_path=None, experiment_profile_path=None, campaign_receipt_path=None,
                    verification_plan_path=None, verification_receipt_path=None) -> dict:
    router = load_contract("core/workflow_router.yaml")
    taxonomy = load_contract(router["capability_taxonomy"])["capabilities"]
    manifest = load_contract(router["module_manifest"])["modules"]
    result = {
        "intent": intent,
        "phase": "A",
        "status": "invalid",
        "execution_allowed": False,
        "business_execution_allowed": False,
        "simulation_execution_allowed": False,
        "implementation_execution_allowed": False,
        "parameter_study_execution_allowed": False,
        "experiment_execution_allowed": False,
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
        "mapping_path": None,
        "mapping_contract_sha256": None,
        "mapping_semantic_sha256": None,
        "parameters_sha256": None,
        "build_spec_sha256": None,
        "implementation_profile_path": None,
        "implementation_profile_sha256": None,
        "implementation_receipt_sha256": None,
    }
    if not isinstance(intent, str) or (intent not in router["intents"] and intent not in taxonomy):
        result["errors"] = [f"unknown intent: {intent}"]
        return result
    result["phase"] = (router["intents"][intent].get("phase", "A")
                       if intent in router["intents"] else taxonomy[intent]["phase"])

    if required_operations is not None and (
        not isinstance(required_operations, (list, tuple)) or
        not all(isinstance(operation, str) for operation in required_operations)
    ):
        result["errors"] = ["required_operations must be an array of operation identifiers"]
        return result
    requested = list(required_operations or [])
    runtime_contract = load_contract(router["runtime_contract"])
    known_operations = set(runtime_contract["operations"])
    if intent == "simulink_build":
        known_operations.add(IMPLEMENTATION_OPERATION)
    if intent == "simulation_execution":
        known_operations.add("simulink.core_simulation")
    if intent in {"parameter_identification", "calibration", "optimization"}:
        from parameter_study_route import OPERATIONS
        known_operations.update(OPERATIONS)
    if intent == "experiment_campaign":
        from run_experiment import OPERATIONS
        known_operations.update(OPERATIONS)
        known_operations.add("simulink.core_simulation")
    unknown_operations = [op for op in requested if op not in known_operations]
    if unknown_operations:
        result["errors"] = [f"unknown operation: {op}" for op in unknown_operations]
        return result

    current_stage = None
    state_result = None
    if state_path is not None:
        from validate_project_state import validate_project_state

        scope = router["intents"].get(intent, {}).get("state_validation_scope", "all")
        state_result = validate_project_state(state_path, profile_path=profile_path,
                                              implementation_profile_path=implementation_profile_path,
                                              simulation_profile_path=simulation_profile_path,
                                              parameter_study_profile_path=parameter_study_profile_path,
                                              experiment_profile_path=experiment_profile_path, scope=scope)
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
        if (state_result and state_result.get("implementation_checked") and
                state_result.get("implementation_ready") and
                state_result.get("mapping_validation", {}).get("structure_checked")):
            satisfied.add("model_structure_checked")
        missing = [gate for gate in gates if gate not in satisfied]
        result.update(status="deferred", phase=phase, required_gates=gates,
                      missing_gates=missing,
                      fallback=router["fallback"]["future_capability"],
                      next_step=policy["next_step_template"].format(phase=phase),
                      errors=[f"{intent} is deferred (declared Phase {phase})"])
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

    if intent in {"numerical_verification", "sensitivity_analysis", "robustness_analysis", "model_comparison", "solver_comparison", "model_verification_review"}:
        from verification_route import verification_route
        return verification_route(result, resources=resources, state_result=state_result,
            state_path=state_path, plan_path=verification_plan_path,
            receipt_path=verification_receipt_path, requested=requested)

    if intent in {"experiment_design", "experiment_campaign", "campaign_review"}:
        from experiment_route import experiment_route
        return experiment_route(result, router=router, resources=resources,
            state_result=state_result, state_path=state_path, design_path=design_path,
            mapping_path=mapping_path,
            problem_path=problem_path, model_path=model_path, approval_path=approval_path,
            profile_path=profile_path, simulation_profile_path=simulation_profile_path,
            experiment_profile_path=experiment_profile_path, campaign_receipt_path=campaign_receipt_path,
            requested=requested, expected_root=expected_root)

    if intent in {"parameter_study", "parameter_candidate_review", "parameter_identification", "calibration", "optimization"}:
        from parameter_study_route import parameter_study_route
        return parameter_study_route(result, router=router, resources=resources,
            state_result=state_result, state_path=state_path, study_path=study_path,
            problem_path=problem_path, model_path=model_path, approval_path=approval_path,
            profile_path=profile_path, parameter_study_profile_path=parameter_study_profile_path,
            simulation_profile_path=simulation_profile_path, parameter_trial_receipt_path=parameter_trial_receipt_path,
            requested=requested, expected_root=expected_root)

    if intent in {"simulation_protocol", "simulation_execution", "solver_diagnostics"}:
        from simulation_route import simulation_route
        return simulation_route(result, router=router, resources=resources,
            state_result=state_result, state_path=state_path, protocol_path=protocol_path,
            mapping_path=mapping_path, problem_path=problem_path, model_path=model_path,
            approval_path=approval_path, profile_path=profile_path,
            simulation_profile_path=simulation_profile_path, run_receipt_path=run_receipt_path,
            requested=requested, expected_root=expected_root)

    if intent in {"domain_mapping", "simulink_build"}:
        return _implementation_route(
            result, router=router, module_id=module_id, resources=resources,
            state_result=state_result, state_path=state_path, profile_path=profile_path,
            implementation_profile_path=implementation_profile_path, problem_path=problem_path,
            model_path=model_path, approval_path=approval_path, mapping_path=mapping_path,
            requested=requested, expected_root=expected_root)

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
    parser.add_argument("--mapping", type=Path)
    parser.add_argument("--implementation-profile", type=Path)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--simulation-profile", type=Path)
    parser.add_argument("--run-receipt", type=Path)
    parser.add_argument("--study", type=Path)
    parser.add_argument("--parameter-study-profile", type=Path)
    parser.add_argument("--parameter-trial-receipt", type=Path)
    parser.add_argument("--experiment-design", type=Path)
    parser.add_argument("--experiment-profile", type=Path)
    parser.add_argument("--campaign-receipt", type=Path)
    parser.add_argument("--verification-plan", type=Path)
    parser.add_argument("--verification-receipt", type=Path)
    parser.add_argument("--require-operation", action="append", default=[])
    parser.add_argument("--matlab-root", type=Path)
    args = parser.parse_args()
    try:
        result = resolve_runtime(args.intent, profile_path=args.profile, state_path=args.state,
                                 required_operations=args.require_operation,
                                 expected_root=args.matlab_root, problem_path=args.problem,
                                 model_path=args.model, approval_path=args.approval, mapping_path=args.mapping,
                                 implementation_profile_path=args.implementation_profile,
                                 protocol_path=args.protocol, simulation_profile_path=args.simulation_profile,
                                 run_receipt_path=args.run_receipt, study_path=args.study,
                                 parameter_study_profile_path=args.parameter_study_profile,
                                 parameter_trial_receipt_path=args.parameter_trial_receipt,
                                 design_path=args.experiment_design, experiment_profile_path=args.experiment_profile,
                                 campaign_receipt_path=args.campaign_receipt,
                                 verification_plan_path=args.verification_plan,
                                 verification_receipt_path=args.verification_receipt)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        result = {"status": "blocked", "execution_allowed": False,
                  "business_execution_allowed": False, "simulation_execution_allowed": False,
                  "implementation_execution_allowed": False, "errors": [str(error)]}
    emit(result)
    return 0 if result["status"] in ("inspected", "allowed", "deferred") else 1


if __name__ == "__main__":
    raise SystemExit(main())
