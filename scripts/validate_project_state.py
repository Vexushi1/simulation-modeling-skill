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


def validate_project_state(state_path: Path, *, profile_path: Path | None = None) -> dict:
    errors = []
    stale = set()
    stage = None
    try:
        state_path = Path(state_path).resolve()
        state = load_document(state_path)
        errors = schema_errors(state, load_contract("core/project_state.schema.yaml"))
        if errors:
            return {"valid": False, "errors": errors, "stale_artefacts": [], "current_stage": None}
        stage = state["current_stage"]
        project_root = (state_path.parent / state["project_root"]).resolve()
        if not project_root.is_dir():
            errors.append("project_root is not an existing directory")
        environment = state["environment"]
        report = None
        bound_profile = None
        if environment:
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

        artefacts = state["artefacts"]
        by_id = {item["id"]: item for item in artefacts}
        if len(by_id) != len(artefacts):
            errors.append("artefact IDs must be unique")
        known = set(by_id) | ({"environment"} if environment else set())
        visiting, visited = set(), set()

        def visit(identity):
            if identity == "environment" or identity in visited:
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
            if item["status"] == "accepted" and item["id"] in stale:
                errors.append(f"{item['id']}: accepted artefact has stale dependencies")
    except (ValueError, OSError, TypeError, KeyError) as error:
        errors.append(str(error))
    return {"valid": not errors, "errors": errors, "stale_artefacts": sorted(stale), "current_stage": stage}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    parser.add_argument("--profile", type=Path)
    args = parser.parse_args()
    result = validate_project_state(args.state, profile_path=args.profile)
    emit(result)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
