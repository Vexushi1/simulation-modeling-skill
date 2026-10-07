"""Resolve Phase A intents without writing files or granting business execution."""
from __future__ import annotations

import argparse
from pathlib import Path

from runtime_common import ROOT, emit, load_contract, load_document


def resolve_runtime(intent, *, profile_path=None, state_path=None,
                    required_operations=None, expected_root=None) -> dict:
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
    if state_path is not None:
        from validate_project_state import validate_project_state

        state_result = validate_project_state(state_path, profile_path=profile_path)
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

    if intent in taxonomy:
        phase = taxonomy[intent]["phase"]
        policy = router["future_capabilities"]
        gates = [gate.replace("requested_capability", intent)
                 for gate in policy["common_missing_gates"]]
        gates += policy["prerequisite_gates_by_phase"].get(phase, [])
        missing = [gate for gate in gates
                   if not (gate == "runtime_assured" and current_stage == "ENVIRONMENT_ASSURED")]
        result.update(status="deferred", phase=phase, required_gates=gates,
                      missing_gates=missing,
                      fallback=router["fallback"]["future_capability"],
                      next_step=policy["next_step_template"].format(phase=phase),
                      errors=[f"{intent} is not implemented in Phase A (declared Phase {phase})"])
        return result

    route = router["intents"][intent]
    module_id = route["module"]
    module = manifest.get(module_id, {})
    resources = module.get("resources", [])
    missing_resources = [path for path in resources if not (ROOT / path).is_file()]
    if module.get("status") != "implemented" or not resources or missing_resources:
        result.update(status="blocked", missing_gates=["environment_module_implemented"],
                      errors=[f"environment module resources unavailable: {missing_resources}"],
                      next_step="Complete the declared environment module before routing this intent.")
        return result

    result.update(required_gates=list(route["required_gates"]),
                  expected_artefacts=list(route["expected_artefacts"]),
                  next_step=route["next_step"])
    if intent == "inspect":
        result.update(status="inspected", activated_modules=[module_id],
                      activated_resources=list(resources))
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
    parser.add_argument("--require-operation", action="append", default=[])
    parser.add_argument("--matlab-root", type=Path)
    args = parser.parse_args()
    try:
        result = resolve_runtime(args.intent, profile_path=args.profile, state_path=args.state,
                                 required_operations=args.require_operation,
                                 expected_root=args.matlab_root)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {"status": "blocked", "execution_allowed": False,
                  "business_execution_allowed": False, "errors": [str(error)]}
    emit(result)
    return 0 if result["status"] in ("inspected", "allowed", "deferred") else 1


if __name__ == "__main__":
    raise SystemExit(main())
