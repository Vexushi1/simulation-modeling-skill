"""Validate only implemented project states and their evidence dependencies."""
from __future__ import annotations

import argparse
from pathlib import Path

from runtime_common import contained_path, emit, load_contract, load_document, schema_errors, sha256_file


def affected_artefacts(artefacts: list[dict], changed_ids: set[str]) -> set[str]:
    affected = set(changed_ids)
    while True:
        added = {item["id"] for item in artefacts if set(item["depends_on"]) & affected}
        if added <= affected:
            return affected
        affected.update(added)


def validate_project_state(state_path: Path, *, profile_path: Path | None = None,
                           scope: str = "all") -> dict:
    """Partial scopes validate only declared evidence, never the whole project."""
    errors = []
    stale = set()
    stage = None
    result = {"scope": scope, "environment_checked": False, "model_checked": False,
              "stage_assessment": {"all": "all_implemented_evidence", "problem": "problem_only",
                                   "model": "problem_and_model_only"}.get(scope),
              "problem_path": None, "problem_contract_sha256": None,
              "model_path": None, "model_contract_sha256": None,
              "approval_path": None, "approval_sha256": None, "model_approved": False,
              "project_root": None}
    if scope not in ("all", "problem", "model"):
        return {**result, "valid": False, "errors": [f"unknown validation scope: {scope}"],
                "stale_artefacts": [], "current_stage": None}
    try:
        state_path = Path(state_path).resolve()
        state = load_document(state_path)
        errors = schema_errors(state, load_contract("core/project_state.schema.yaml"))
        if errors:
            return {**result, "valid": False, "errors": errors,
                    "stale_artefacts": [], "current_stage": None}
        stage = state["current_stage"]
        project_root = (state_path.parent / state["project_root"]).resolve()
        result["project_root"] = str(project_root)
        if not project_root.is_dir():
            errors.append("project_root is not an existing directory")
        environment = state["environment"]
        report = None
        bound_profile = None
        if environment and scope == "all":
            result["environment_checked"] = True
            from validate_environment import validate_environment

            bound_profile = contained_path(project_root, environment["profile_path"])
            if profile_path is not None and Path(profile_path).resolve() != bound_profile:
                errors.append("requested profile differs from project-state binding")
            report = validate_environment(bound_profile)
            if not report["valid"]:
                errors.extend(f"environment: {error}" for error in report["errors"])
                stale.add("environment")
            if report.get("profile_sha256") != environment["profile_sha256"]:
                errors.append("environment profile SHA differs from project-state binding")
                stale.add("environment")
            if report.get("receipt_sha256") != environment["receipt_sha256"]:
                errors.append("environment receipt SHA differs from project-state binding")
                stale.add("environment")
        elif environment:
            # Containment is structural safety; this does not assess runtime evidence.
            contained_path(project_root, environment["profile_path"])

        problem = state.get("problem")
        bound_problem = None
        problem_report = None
        problem_status = None
        model_stages = {"MODEL_PROPOSED", "MODEL_CHALLENGED", "MODEL_APPROVED"}
        if problem:
            from validate_problem_contract import validate_problem_contract

            bound_problem = contained_path(project_root, problem["path"])
            result["problem_path"] = str(bound_problem)
            problem_report = validate_problem_contract(
                bound_problem, require_frozen=stage == "PROBLEM_FROZEN" or stage in model_stages,
                project_root=project_root)
            result["problem_validation"] = problem_report
            if problem_report["schema_valid"]:
                problem_status = load_document(bound_problem)["status"]
            result["problem_contract_sha256"] = problem_report["contract_sha256"]
            if problem_report["contract_sha256"] != problem["sha256"]:
                errors.append("problem contract SHA differs from project-state binding")
                stale.add("problem")
            if not problem_report["valid"]:
                errors.extend(f"problem: {error}" for error in problem_report["errors"])
                if not problem_report["errors"]:
                    errors.append("problem contract validation failed")
                stale.add("problem")
            if problem_report["project_id"] != state["project_id"]:
                errors.append("problem contract project_id differs from project state")
                stale.add("problem")
            if stage in ("PROBLEM_AUDITED", "PROBLEM_FROZEN") and not problem_report["audit_complete"]:
                errors.append(f"{stage} requires a complete problem audit")
                stale.add("problem")
            if stage == "PROBLEM_AUDITED" and problem_status not in ("audited", "frozen"):
                errors.append("PROBLEM_AUDITED requires a declared audited or frozen contract")
                stale.add("problem")
            if stage == "PROBLEM_FROZEN" and not problem_report["frozen"]:
                errors.append("PROBLEM_FROZEN requires a current recorded freeze review")
                stale.add("problem")

        model = state.get("model")
        approval = state.get("approval")
        bound_model = contained_path(project_root, model["path"]) if model else None
        bound_approval = contained_path(project_root, approval["path"]) if approval else None
        model_report = None
        model_status = None
        if scope != "problem" and model:
            from validate_model_contract import validate_model_contract

            result["model_checked"] = True
            result["model_path"] = str(bound_model)
            model_report = validate_model_contract(
                bound_model, project_root=project_root, problem_path=bound_problem,
                approval_path=bound_approval, require_proposed=stage == "MODEL_PROPOSED",
                require_challenged=stage == "MODEL_CHALLENGED",
                require_approved=stage == "MODEL_APPROVED")
            result["model_validation"] = model_report
            result["model_contract_sha256"] = model_report["contract_sha256"]
            result["approval_path"] = model_report.get("approval_path")
            result["approval_sha256"] = model_report.get("approval_sha256")
            if model_report["schema_valid"]:
                model_status = load_document(bound_model)["status"]
            if model_report["contract_sha256"] != model["sha256"]:
                errors.append("model contract SHA differs from project-state binding")
                stale.add("model")
            if not model_report["valid"]:
                errors.extend(f"model: {error}" for error in model_report["errors"])
                if not model_report["errors"]:
                    errors.append("model contract validation failed")
                stale.add("model")
            if model_report["project_id"] != state["project_id"]:
                errors.append("model contract project_id differs from project state")
                stale.add("model")
            if (not problem or model_report.get("problem_path") != str(bound_problem) or
                    model_report.get("problem_sha256") != problem["sha256"]):
                errors.append("model contract must match the project problem binding")
                stale.add("model")
            if approval:
                if (model_report.get("approval_path") != str(bound_approval) or
                        model_report.get("approval_sha256") != approval["sha256"]):
                    errors.append("model approval differs from project-state binding")
                    stale.add("approval")
                if not model_report["approved"]:
                    errors.append("approval binding requires a current approved model")
                    stale.add("approval")
            elif model_report["approved"]:
                errors.append("approved model requires a project approval binding")
                stale.add("approval")
            result["model_approved"] = bool(
                model_report["approved"] and approval and "model" not in stale and "approval" not in stale)
            required_statuses = {
                "MODEL_PROPOSED": {"proposed", "challenged", "approved"},
                "MODEL_CHALLENGED": {"challenged", "approved"},
                "MODEL_APPROVED": {"approved"},
            }
            if stage in required_statuses and model_status not in required_statuses[stage]:
                errors.append(f"{stage} requires the corresponding declared model status")
                stale.add("model")
        elif scope != "problem" and approval:
            errors.append("approval binding requires a model binding")
            stale.add("approval")

        artefacts = state["artefacts"]
        by_id = {item["id"]: item for item in artefacts}
        if len(by_id) != len(artefacts):
            errors.append("artefact IDs must be unique")
        for item in artefacts:
            contained_path(project_root, item["path"])
        environment_ids = {"environment"} | {
            item["id"] for item in artefacts if item["role"] in ("environment_profile", "route_decision")}
        environment_dependents = affected_artefacts(artefacts, environment_ids)
        anchors = ({"environment"} if environment else set()) | ({"problem"} if problem else set())
        anchors |= ({"model"} if model else set()) | ({"approval"} if approval else set())
        known = set(by_id) | anchors
        scoped_roles = {"problem_contract"}
        if scope == "model":
            scoped_roles |= {"model_contract", "model_approval"}
        checked_ids = set(by_id) if scope == "all" else {
            item["id"] for item in artefacts if item["role"] in scoped_roles}
        if scope != "all":
            while True:
                ancestors = {dependency for identity in checked_ids
                             for dependency in by_id[identity]["depends_on"] if dependency in by_id}
                if ancestors <= checked_ids:
                    break
                checked_ids.update(ancestors)
        result["checked_artefacts"] = sorted(checked_ids)
        result["unchecked_artefacts"] = sorted(set(by_id) - checked_ids)
        visiting, visited = set(), set()

        def visit(identity):
            if identity in anchors or identity in visited:
                return
            if identity in visiting:
                errors.append(f"dependency cycle at {identity}")
                return
            visiting.add(identity)
            for dependency in by_id[identity]["depends_on"]:
                if dependency not in known:
                    errors.append(f"{identity}: unknown dependency {dependency}")
                else:
                    visit(dependency)
            visiting.remove(identity)
            visited.add(identity)

        for item in artefacts:
            if item["id"] not in checked_ids:
                continue
            visit(item["id"])
            path = contained_path(project_root, item["path"])
            if item["status"] == "stale":
                stale.add(item["id"])
            if item["status"] == "accepted":
                pending = [dependency for dependency in item["depends_on"]
                           if dependency in by_id and by_id[dependency]["status"] != "accepted"]
                if pending:
                    errors.append(f"{item['id']}: accepted artefact depends on unaccepted evidence: {pending}")
                    stale.add(item["id"])
                if not path.is_file() or sha256_file(path) != item["sha256"]:
                    stale.add(item["id"])
                    errors.append(f"{item['id']}: accepted artefact file is missing or changed")
                    continue
                if item["role"] == "problem_contract":
                    if item["id"] in environment_dependents:
                        errors.append(f"{item['id']}: accepted problem evidence cannot depend on environment evidence")
                        stale.add(item["id"])
                    if (not problem or "problem" not in item["depends_on"] or
                            path != bound_problem or item["sha256"] != problem["sha256"]):
                        errors.append(f"{item['id']}: accepted problem contract must match and depend on the problem binding")
                        stale.add(item["id"])
                    elif not problem_report["valid"] or not problem_report["audit_complete"]:
                        errors.append(f"{item['id']}: accepted problem contract lacks a complete current audit")
                        stale.add(item["id"])
                    elif problem_status not in ("audited", "frozen"):
                        errors.append(f"{item['id']}: accepted problem contract requires a declared audited or frozen status")
                        stale.add(item["id"])
                    continue
                if item["role"] in ("model_contract", "model_approval"):
                    if item["id"] in environment_dependents:
                        errors.append(f"{item['id']}: accepted model evidence cannot depend on environment evidence")
                        stale.add(item["id"])
                    required_anchors = {"model", "problem"}
                    if item["role"] == "model_approval":
                        required_anchors.add("approval")
                    expected_path = bound_model if item["role"] == "model_contract" else bound_approval
                    binding = model if item["role"] == "model_contract" else approval
                    if (not binding or not required_anchors <= set(item["depends_on"]) or
                            path != expected_path or item["sha256"] != binding["sha256"]):
                        errors.append(f"{item['id']}: accepted model evidence must match and depend on its project bindings")
                        stale.add(item["id"])
                    elif (not model_report or not model_report["valid"] or
                          not model_report["proposal_complete"] or
                          model_status not in ("proposed", "challenged", "approved")):
                        errors.append(f"{item['id']}: accepted model evidence requires a current declared proposal")
                        stale.add(item["id"])
                    elif not problem_report or not problem_report["frozen"]:
                        errors.append(f"{item['id']}: accepted model evidence requires the current frozen problem")
                        stale.add(item["id"])
                    elif item["role"] == "model_approval" and not result["model_approved"]:
                        errors.append(f"{item['id']}: accepted approval lacks a current approved model")
                        stale.add(item["id"])
                    continue
                if scope != "all":
                    # Byte/dependency checks above do not qualify an environment ancestor.
                    continue
                if not environment or "environment" not in item["depends_on"]:
                    errors.append(f"{item['id']}: accepted evidence must depend on the bound environment")
                    stale.add(item["id"])
                    continue
                if item["role"] == "environment_profile":
                    if path != bound_profile or item["sha256"] != environment["profile_sha256"]:
                        errors.append(f"{item['id']}: environment profile differs from the state binding")
                        stale.add(item["id"])
                else:
                    route = load_document(path)
                    from resolve_runtime import resolve_runtime

                    expected_route = resolve_runtime("assure_environment", profile_path=bound_profile,
                                                     required_operations=route.get("selected_operations"))
                    decision_fields = (
                        "intent", "phase", "status", "execution_scope", "execution_allowed",
                        "business_execution_allowed", "activated_modules", "activated_resources",
                        "activated_packs", "upstream_skills", "selected_operations", "required_gates",
                        "missing_gates", "state_mutated", "profile_sha256", "receipt_sha256",
                    )
                    valid_route = (
                        route.get("status") == "allowed"
                        and route.get("intent") == "assure_environment"
                        and route.get("execution_scope") == "environment_assurance"
                        and route.get("execution_allowed") is True
                        and route.get("business_execution_allowed") is False
                        and route.get("profile_sha256") == environment["profile_sha256"]
                        and route.get("receipt_sha256") == environment["receipt_sha256"]
                        and isinstance(route.get("selected_operations"), list)
                        and set(load_contract("core/runtime_assurance_contract.yaml")["core_operations"])
                            <= set(route["selected_operations"])
                        and set(route["selected_operations"]) <= set(report.get("qualified_operations", []))
                        and all(route.get(key) == expected_route.get(key) for key in decision_fields)
                    )
                    if not valid_route:
                        errors.append(f"{item['id']}: route decision is outside the bound qualified Phase A scope")
                        stale.add(item["id"])
        stale = affected_artefacts(artefacts, stale)
        for item in artefacts:
            if item["id"] in checked_ids and item["status"] == "accepted" and item["id"] in stale:
                errors.append(f"{item['id']}: accepted artefact has stale dependencies")
    except (ValueError, OSError, TypeError, KeyError) as error:
        errors.append(str(error))
    return {**result, "valid": not errors, "errors": errors,
            "stale_artefacts": sorted(stale), "current_stage": stage}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--scope", choices=["all", "problem", "model"], default="all")
    args = parser.parse_args()
    result = validate_project_state(args.state, profile_path=args.profile, scope=args.scope)
    emit(result)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
