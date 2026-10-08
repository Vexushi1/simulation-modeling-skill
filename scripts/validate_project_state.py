"""Validate only implemented project states and their evidence dependencies."""
from __future__ import annotations

import argparse
from pathlib import Path

from runtime_common import contained_path, emit, load_contract, load_document, schema_errors, sha256_file
from simulation_state import STAGES as E_STAGES, HISTORICAL_ROLES as E_HISTORICAL_ROLES, CURRENT_ROLES as E_CURRENT_ROLES

D_EVIDENCE_ROLES = {"mapping_contract", "parameter_provenance", "implementation_model", "structure_evidence"}


def affected_artefacts(artefacts: list[dict], changed_ids: set[str]) -> set[str]:
    affected = set(changed_ids)
    while True:
        added = {item["id"] for item in artefacts if set(item["depends_on"]) & affected}
        if added <= affected:
            return affected
        affected.update(added)


def validate_project_state(state_path: Path, *, profile_path: Path | None = None,
                           implementation_profile_path: Path | None = None,
                           simulation_profile_path: Path | None = None,
                           scope: str = "all") -> dict:
    """Partial scopes validate only declared evidence, never the whole project."""
    errors = []
    stale = set()
    stage = None
    result = {"scope": scope, "environment_checked": False, "model_checked": False,
              "implementation_checked": False, "implementation_ready": False,
              "implementation_environment_checked": False,
              "stage_assessment": {"all": "all_implemented_evidence", "problem": "problem_only",
                                   "model": "problem_and_model_only",
                                   "implementation": "problem_model_and_implementation_only",
                                   "simulation": "problem_model_implementation_and_simulation_only"}.get(scope),
              "problem_path": None, "problem_contract_sha256": None,
              "model_path": None, "model_contract_sha256": None,
              "approval_path": None, "approval_sha256": None, "model_approved": False,
              "mapping_path": None, "mapping_contract_sha256": None,
              "environment_path": None, "implementation_environment_path": None,
              "project_root": None}
    if scope not in ("all", "problem", "model", "implementation", "simulation"):
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
        bound_profile = contained_path(project_root, environment["profile_path"]) if environment else None
        result["environment_path"] = str(bound_profile) if bound_profile else None
        if environment and scope == "all":
            result["environment_checked"] = True
            from validate_environment import validate_environment

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

        implementation_environment = state.get("implementation_environment")
        bound_implementation_profile = (contained_path(project_root, implementation_environment["profile_path"])
                                        if implementation_environment else None)
        result["implementation_environment_path"] = (str(bound_implementation_profile)
                                                     if bound_implementation_profile else None)
        implementation_environment_report = None
        if implementation_environment and scope == "all":
            from validate_implementation_profile import validate_implementation_profile

            result["implementation_environment_checked"] = True
            if (implementation_profile_path is not None and
                    Path(implementation_profile_path).resolve() != bound_implementation_profile):
                errors.append("requested implementation profile differs from project-state binding")
            implementation_environment_report = validate_implementation_profile(bound_implementation_profile)
            if not implementation_environment_report["valid"]:
                errors.extend(f"implementation environment: {error}"
                              for error in implementation_environment_report["errors"])
                stale.add("implementation_environment")
            if any(implementation_environment_report.get(key) != implementation_environment[key]
                   for key in ("profile_sha256", "receipt_sha256")):
                errors.append("implementation profile or receipt SHA differs from project-state binding")
                stale.add("implementation_environment")

        problem = state.get("problem")
        bound_problem = None
        problem_report = None
        problem_status = None
        model_stages = {"MODEL_PROPOSED", "MODEL_CHALLENGED", "MODEL_APPROVED", "IMPLEMENTATION_READY"} | E_STAGES
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
                require_approved=stage in {"MODEL_APPROVED", "IMPLEMENTATION_READY"} | E_STAGES)
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
                "IMPLEMENTATION_READY": {"approved"},
            }
            required_statuses.update({item: {"approved"} for item in E_STAGES})
            if stage in required_statuses and model_status not in required_statuses[stage]:
                errors.append(f"{stage} requires the corresponding declared model status")
                stale.add("model")
        elif scope != "problem" and approval:
            errors.append("approval binding requires a model binding")
            stale.add("approval")

        mapping = state.get("mapping")
        bound_mapping = contained_path(project_root, mapping["path"]) if mapping else None
        mapping_report = None
        if scope in {"all", "implementation", "simulation"} and mapping:
            from validate_domain_mapping import validate_domain_mapping

            result["implementation_checked"] = True
            result["mapping_path"] = str(bound_mapping)
            mapping_report = validate_domain_mapping(
                bound_mapping, project_root=project_root,
                require_ready=stage == "IMPLEMENTATION_READY" or stage in E_STAGES)
            result["mapping_validation"] = mapping_report
            result["mapping_contract_sha256"] = mapping_report["contract_sha256"]
            if mapping_report["contract_sha256"] != mapping["sha256"]:
                errors.append("mapping contract SHA differs from project-state binding")
                stale.add("mapping")
            if not mapping_report["valid"]:
                errors.extend(f"mapping: {error}" for error in mapping_report["errors"])
                if not mapping_report["errors"]:
                    errors.append("mapping contract validation failed")
                stale.add("mapping")
            if (mapping_report["project_id"] != state["project_id"] or not model or
                    mapping_report.get("model_path") != str(bound_model) or
                    mapping_report.get("model_sha256") != model["sha256"]):
                errors.append("mapping contract must match the project and current model binding")
                stale.add("mapping")
            if not result["model_approved"]:
                errors.append("project mapping requires the current bound approved model")
                stale.add("mapping")
            result["implementation_ready"] = bool(
                mapping_report["implementation_ready"] and result["model_approved"] and "mapping" not in stale)
            if (stage == "IMPLEMENTATION_READY" or stage in E_STAGES) and not result["implementation_ready"]:
                errors.append("IMPLEMENTATION_READY requires current mapping, parameter and actual structure evidence")
                stale.add("mapping")

        from simulation_state import validate_bindings, validate_artifact
        validate_bindings(state, project_root, result, errors, stale, scope, simulation_profile_path)
        artefacts = state["artefacts"]
        by_id = {item["id"]: item for item in artefacts}
        if len(by_id) != len(artefacts):
            errors.append("artefact IDs must be unique")
        for item in artefacts:
            contained_path(project_root, item["path"])
        environment_ids = {"environment", "implementation_environment", "simulation_environment"} | {
            item["id"] for item in artefacts if item["role"] in
            ("environment_profile", "route_decision", "implementation_profile", "implementation_route_decision", "simulation_profile", "simulation_route_decision")}
        environment_dependents = affected_artefacts(artefacts, environment_ids)
        anchors = ({"environment"} if environment else set()) | ({"problem"} if problem else set())
        anchors |= ({"model"} if model else set()) | ({"approval"} if approval else set())
        anchors |= ({"mapping"} if mapping else set())
        anchors |= ({"implementation_environment"} if implementation_environment else set())
        anchors |= {anchor for anchor in ("protocol", "primary_run", "simulation_environment") if state.get(anchor)}
        known = set(by_id) | anchors
        scoped_roles = {"problem_contract"}
        if scope in {"model", "implementation", "simulation"}:
            scoped_roles |= {"model_contract", "model_approval"}
        if scope in {"implementation", "simulation"}:
            scoped_roles |= D_EVIDENCE_ROLES
        if scope == "simulation":
            scoped_roles |= E_HISTORICAL_ROLES
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

        def ancestor_roles(item):
            pending = list(item["depends_on"])
            seen = set()
            roles = set()
            while pending:
                identity = pending.pop()
                if identity in seen or identity not in by_id:
                    continue
                seen.add(identity)
                roles.add(by_id[identity]["role"])
                pending.extend(by_id[identity]["depends_on"])
            return roles

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
                if item["role"] in D_EVIDENCE_ROLES:
                    native = (mapping_report.get("native_structure_validation") or {}) if mapping_report else {}
                    expected = {
                        "mapping_contract": (bound_mapping, mapping["sha256"] if mapping else None),
                        "parameter_provenance": (mapping_report.get("parameters_path"), mapping_report.get("parameters_sha256")) if mapping_report else (None, None),
                        "implementation_model": (native.get("model_path"), native.get("model_sha256")),
                        "structure_evidence": (mapping_report.get("implementation_path"), mapping_report.get("implementation_sha256")) if mapping_report else (None, None),
                    }[item["role"]]
                    required_anchors = {"problem", "model", "approval"}
                    if item["role"] != "parameter_provenance":
                        required_anchors.add("mapping")
                    required_roles = {
                        "mapping_contract": {"parameter_provenance"},
                        "parameter_provenance": set(),
                        "implementation_model": {"mapping_contract", "parameter_provenance"},
                        "structure_evidence": {"mapping_contract", "parameter_provenance", "implementation_model"},
                    }[item["role"]]
                    invalid = []
                    if item["id"] in environment_dependents:
                        invalid.append("historical mapping/implementation evidence cannot depend on current environment evidence")
                    if (not expected[0] or path != Path(expected[0]).resolve() or item["sha256"] != expected[1] or
                            not required_anchors <= set(item["depends_on"])):
                        invalid.append("accepted D evidence must match and depend on its project bindings")
                    if not required_roles <= ancestor_roles(item):
                        invalid.append("accepted D evidence lacks the required parameter/mapping/native dependency chain")
                    parameter_report = mapping_report.get("parameter_validation", {}) if mapping_report else {}
                    evidence_valid = (bool(parameter_report.get("valid") and parameter_report.get("binding_complete") and
                                           parameter_report.get("status") == "bound" and model and approval and
                                           parameter_report.get("project_id") == state["project_id"] and
                                           parameter_report.get("model_path") == str(bound_model) and
                                           parameter_report.get("model_sha256") == model["sha256"] and
                                           parameter_report.get("model_approval_path") == str(bound_approval) and
                                           parameter_report.get("model_approval_sha256") == approval["sha256"])
                                      if item["role"] == "parameter_provenance" else
                                      bool(mapping_report and mapping_report["valid"]))
                    if not evidence_valid or not result["model_approved"]:
                        invalid.append("accepted D evidence requires a current mapping and approved model")
                    elif item["role"] == "mapping_contract" and not (
                            mapping_report["mapping_complete"] and load_document(bound_mapping)["status"] in {"mapped", "ready"}):
                        invalid.append("accepted mapping requires complete reviewed trace coverage")
                    elif item["role"] in {"implementation_model", "structure_evidence"} and not (
                            native.get("valid") and native.get("built") and native.get("structure_checked")):
                        invalid.append("accepted native evidence requires the actual bound structure receipt")
                    if invalid:
                        errors.extend(f"{item['id']}: {error}" for error in invalid)
                        stale.add(item["id"])
                    continue
                if item["role"] in E_HISTORICAL_ROLES | E_CURRENT_ROLES:
                    if scope != "all" and item["role"] in E_CURRENT_ROLES:
                        continue
                    invalid = validate_artifact(item, state=state, result=result, root=project_root,
                        environment_dependents=environment_dependents, ancestor_roles=ancestor_roles)
                    if invalid:
                        errors.extend(f"{item['id']}: {error}" for error in invalid)
                        stale.add(item["id"])
                    continue
                if scope != "all":
                    # Byte/dependency checks above do not qualify an environment ancestor.
                    continue
                if item["role"] in {"implementation_profile", "implementation_route_decision"}:
                    if (not implementation_environment or
                            "implementation_environment" not in item["depends_on"]):
                        errors.append(f"{item['id']}: accepted D operation evidence requires the implementation environment binding")
                        stale.add(item["id"])
                        continue
                    if item["role"] == "implementation_profile":
                        if (path != bound_implementation_profile or
                                item["sha256"] != implementation_environment["profile_sha256"]):
                            errors.append(f"{item['id']}: implementation profile differs from the state binding")
                            stale.add(item["id"])
                    else:
                        from resolve_runtime import resolve_runtime

                        route = load_document(path)
                        expected_route = resolve_runtime(
                            "simulink_build", profile_path=bound_profile,
                            implementation_profile_path=bound_implementation_profile,
                            mapping_path=bound_mapping, model_path=bound_model,
                            problem_path=bound_problem, approval_path=bound_approval,
                            required_operations=route.get("selected_operations"))
                        fields = (
                            "intent", "phase", "status", "execution_scope", "execution_allowed",
                            "business_execution_allowed", "simulation_execution_allowed", "implementation_execution_allowed",
                            "activated_modules", "activated_resources", "activated_packs", "upstream_skills",
                            "selected_operations", "required_gates", "missing_gates", "state_mutated",
                            "profile_sha256", "receipt_sha256", "implementation_profile_sha256",
                            "implementation_receipt_sha256", "mapping_contract_sha256", "model_contract_sha256",
                            "model_approval_sha256", "parameters_sha256", "build_spec_sha256",
                        )
                        if (not {"environment", "mapping", "model", "approval", "problem"} <= set(item["depends_on"]) or
                                not {"mapping_contract", "parameter_provenance"} <= ancestor_roles(item) or
                                expected_route["status"] != "allowed" or
                                any(route.get(key) != expected_route.get(key) for key in fields)):
                            errors.append(f"{item['id']}: build route differs from current bound A/D qualification and mapping")
                            stale.add(item["id"])
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
                            "business_execution_allowed", "simulation_execution_allowed", "implementation_execution_allowed",
                            "activated_modules", "activated_resources",
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
                        # Pre-D A routes had no implementation/simulation fields;
                        # their absence never conveyed either permission.
                        and all(route.get(key, False if key in {"simulation_execution_allowed", "implementation_execution_allowed"} else None)
                                == expected_route.get(key) for key in decision_fields)
                    )
                    if not valid_route:
                        errors.append(f"{item['id']}: route decision is outside the bound qualified Phase A scope")
                        stale.add(item["id"])
        stale = affected_artefacts(artefacts, stale)
        if {"protocol", "mapping", "model", "approval", "problem"} & stale:
            result["protocol_frozen"] = False
            result["primary_run_complete"] = False
        if "primary_run" in stale or any(item["id"] in stale and item["role"] in E_HISTORICAL_ROLES for item in artefacts):
            result["primary_run_complete"] = False
        if stage in E_STAGES and scope in {"all", "simulation"}:
            if not result["protocol_frozen"]:
                errors.append("frozen simulation stage cannot retain stale protocol dependencies")
            if stage == "PRIMARY_RUN_COMPLETE" and not result["primary_run_complete"]:
                errors.append("PRIMARY_RUN_COMPLETE cannot retain stale run dependencies")
        if "mapping" in stale or any(item["id"] in stale and item["role"] in D_EVIDENCE_ROLES
                                     for item in artefacts if item["id"] in checked_ids):
            result["implementation_ready"] = False
        if ((stage == "IMPLEMENTATION_READY" or stage in E_STAGES) and scope in {"all", "implementation", "simulation"} and
                not result["implementation_ready"]):
            errors.append("IMPLEMENTATION_READY cannot retain stale implementation dependencies")
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
    parser.add_argument("--implementation-profile", type=Path)
    parser.add_argument("--simulation-profile", type=Path)
    parser.add_argument("--scope", choices=["all", "problem", "model", "implementation", "simulation"], default="all")
    args = parser.parse_args()
    result = validate_project_state(args.state, profile_path=args.profile,
                                    implementation_profile_path=args.implementation_profile,
                                    simulation_profile_path=args.simulation_profile, scope=args.scope)
    emit(result)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
