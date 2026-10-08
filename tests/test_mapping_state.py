"""B/C/D scopes protect current bindings and retain historical evidence."""
import json
import subprocess
import sys

import pytest

from model_factory import make_model_contract
from mapping_factory import make_mapping_contract
from runtime_common import ROOT, load_document, sha256_file
from test_model_state import write_model_state
from validate_project_state import validate_project_state


def write_mapping_state(root, mapping, *, stage="MODEL_APPROVED", profile=None,
                        implementation_profile=None, artefacts=None):
    value = load_document(mapping)
    model = root / value["model"]["path"]
    state = write_model_state(root, model, stage=stage, profile=profile, artefacts=artefacts)
    state_value = load_document(state)
    state_value["mapping"] = {"path": mapping.relative_to(root).as_posix(), "sha256": sha256_file(mapping)}
    if implementation_profile:
        from validate_implementation_profile import contract
        receipt = implementation_profile.parent / contract()["evidence"]["receipt"]
        state_value["implementation_environment"] = {
            "profile_path": implementation_profile.relative_to(root).as_posix(),
            "profile_sha256": sha256_file(implementation_profile), "receipt_sha256": sha256_file(receipt)}
    state.write_text(json.dumps(state_value), encoding="utf-8")
    return state


def d_artefact(root, path, role, identity, depends):
    return {"id": identity, "role": role, "path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path), "status": "accepted", "depends_on": depends}


def mapping_artefacts(root, mapping):
    value = load_document(mapping)
    parameters = root / value["parameters"]["path"]
    anchors = ["problem", "model", "approval"]
    return [d_artefact(root, parameters, "parameter_provenance", "parameter-record", anchors),
            d_artefact(root, mapping, "mapping_contract", "mapping-record", anchors + ["mapping", "parameter-record"])]


def test_implementation_ready_requires_a_mapping_binding(tmp_path):
    model = make_model_contract(tmp_path, status="approved")
    state = write_model_state(tmp_path, model, stage="IMPLEMENTATION_READY")
    result = validate_project_state(state, scope="implementation")
    assert not result["valid"]
    assert not result["implementation_ready"]


@pytest.mark.parametrize("scope", ["problem", "model"])
def test_existing_partial_scopes_do_not_assess_d_or_claim_ready(tmp_path, scope):
    model = make_model_contract(tmp_path, status="approved")
    state = write_model_state(tmp_path, model, stage="IMPLEMENTATION_READY")
    value = load_document(state)
    value["mapping"] = {"path": "unassessed-mapping.json", "sha256": "0" * 64}
    state.write_text(json.dumps(value), encoding="utf-8")
    before = state.read_bytes()
    result = validate_project_state(state, scope=scope)
    assert result["valid"], result["errors"]
    assert result["implementation_checked"] is False
    assert result["implementation_ready"] is False
    assert "mapping_validation" not in result
    assert state.read_bytes() == before


@pytest.mark.parametrize("scope", ["problem", "model", "implementation", "all"])
def test_d_bindings_and_profiles_cannot_escape_project_in_any_scope(tmp_path, scope):
    model = make_model_contract(tmp_path, status="approved")
    state = write_model_state(tmp_path, model)
    value = load_document(state)
    value["mapping"] = {"path": "../escape.json", "sha256": "0" * 64}
    state.write_text(json.dumps(value), encoding="utf-8")
    result = validate_project_state(state, scope=scope)
    assert not result["valid"] and any("leaves project root" in error for error in result["errors"])
    value.pop("mapping")
    value["implementation_environment"] = {"profile_path": "../escape.json",
                                         "profile_sha256": "0" * 64, "receipt_sha256": "0" * 64}
    state.write_text(json.dumps(value), encoding="utf-8")
    result = validate_project_state(state, scope=scope)
    assert not result["valid"] and any("leaves project root" in error for error in result["errors"])


def test_d_accepted_role_cannot_fall_through_to_environment_only_validation(tmp_path):
    model = make_model_contract(tmp_path, status="approved")
    item = d_artefact(tmp_path, model, "parameter_provenance", "parameters", ["problem", "model", "approval"])
    state = write_model_state(tmp_path, model, artefacts=[item])
    result = validate_project_state(state, scope="implementation")
    assert not result["valid"]
    assert "parameters" in result["stale_artefacts"]
    assert any("accepted D evidence" in error for error in result["errors"])
    assert not any("accepted evidence must depend on the bound environment" in error for error in result["errors"])


def test_implementation_scope_cli_is_explicit_and_never_writes_state(tmp_path):
    model = make_model_contract(tmp_path, status="approved")
    state = write_model_state(tmp_path, model, stage="MODEL_APPROVED")
    before = state.read_bytes()
    completed = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/validate_project_state.py"),
                                str(state), "--scope", "implementation"], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout
    report = json.loads(completed.stdout)
    assert report["scope"] == "implementation"
    assert report["stage_assessment"] == "problem_model_and_implementation_only"
    assert report["environment_checked"] is False
    assert report["model_checked"] is True
    assert report["implementation_ready"] is False
    assert state.read_bytes() == before


@pytest.mark.parametrize("known_parameters", [True, False])
def test_current_mapping_and_parameter_chain_are_valid_without_runtime(tmp_path, known_parameters):
    mapping = make_mapping_contract(tmp_path, known_parameters=known_parameters)
    state = write_mapping_state(tmp_path, mapping, artefacts=mapping_artefacts(tmp_path, mapping))
    before = state.read_bytes()
    result = validate_project_state(state, scope="implementation")
    assert result["valid"], result["errors"]
    assert result["model_approved"] and result["implementation_checked"]
    assert result["mapping_validation"]["mapping_complete"]
    assert result["mapping_validation"]["build_ready"] is known_parameters
    assert not result["implementation_ready"] and not result["environment_checked"]
    assert not result["stale_artefacts"]
    assert state.read_bytes() == before


def test_mapped_file_and_hand_written_ready_stage_do_not_supply_structure_evidence(tmp_path):
    mapping = make_mapping_contract(tmp_path)
    state = write_mapping_state(tmp_path, mapping, stage="IMPLEMENTATION_READY")
    result = validate_project_state(state, scope="implementation")
    assert not result["valid"] and not result["implementation_ready"]
    assert "mapping" in result["stale_artefacts"]
    value = load_document(mapping)
    value["status"] = "ready"
    mapping.write_text(json.dumps(value), encoding="utf-8")
    state = write_mapping_state(tmp_path, mapping, stage="IMPLEMENTATION_READY")
    result = validate_project_state(state, scope="implementation")
    assert not result["valid"] and not result["implementation_ready"]


@pytest.mark.parametrize("change", ["mapping_sha", "mapping_path", "parameter_path", "missing_parameter_chain"])
def test_accepted_mapping_requires_exact_binding_and_parameter_dependency(tmp_path, change):
    mapping = make_mapping_contract(tmp_path)
    artefacts = mapping_artefacts(tmp_path, mapping)
    if change == "mapping_path":
        copy = tmp_path / "copied-mapping.json"
        copy.write_bytes(mapping.read_bytes())
        artefacts[1]["path"] = copy.name
    elif change == "parameter_path":
        copy = tmp_path / "copied-parameters.json"
        copy.write_bytes((tmp_path / artefacts[0]["path"]).read_bytes())
        artefacts[0]["path"] = copy.name
    elif change == "missing_parameter_chain":
        artefacts[1]["depends_on"].remove("parameter-record")
    state = write_mapping_state(tmp_path, mapping, artefacts=artefacts)
    if change == "mapping_sha":
        value = load_document(state)
        value["mapping"]["sha256"] = "0" * 64
        state.write_text(json.dumps(value), encoding="utf-8")
    result = validate_project_state(state, scope="implementation")
    assert not result["valid"]
    assert "mapping-record" in result["stale_artefacts"]


@pytest.mark.parametrize("role", ["mapping_contract", "parameter_provenance"])
@pytest.mark.parametrize("indirect", [False, True])
def test_text_d_evidence_rejects_current_environment_dependencies(tmp_path, role, indirect):
    from test_runtime import make_profile

    mapping = make_mapping_contract(tmp_path)
    profile = make_profile(tmp_path / "runtime")
    artefacts = mapping_artefacts(tmp_path, mapping)
    dependency = "environment"
    if indirect:
        dependency = "profile-record"
        artefacts.append(d_artefact(tmp_path, profile, "environment_profile", dependency, ["environment"]))
    selected = next(item for item in artefacts if item["role"] == role)
    selected["depends_on"].append(dependency)
    state = write_mapping_state(tmp_path, mapping, profile=profile, artefacts=artefacts)
    result = validate_project_state(state, scope="implementation")
    assert not result["valid"]
    assert any("cannot depend on current environment" in error for error in result["errors"])


def test_parameter_change_invalidates_mapping_and_transitive_evidence_without_rewriting_state(tmp_path):
    mapping = make_mapping_contract(tmp_path)
    artefacts = mapping_artefacts(tmp_path, mapping)
    state = write_mapping_state(tmp_path, mapping, artefacts=artefacts)
    assert validate_project_state(state, scope="implementation")["valid"]
    parameters = tmp_path / artefacts[0]["path"]
    parameters.write_bytes(parameters.read_bytes() + b"\nchanged bytes\n")
    before = state.read_bytes()
    result = validate_project_state(state, scope="implementation")
    assert not result["valid"]
    assert {"mapping", "mapping-record", "parameter-record"} <= set(result["stale_artefacts"])
    assert state.read_bytes() == before


def test_invalid_mapping_source_preserves_independent_current_parameter_record(tmp_path):
    mapping = make_mapping_contract(tmp_path)
    artefacts = mapping_artefacts(tmp_path, mapping)
    state = write_mapping_state(tmp_path, mapping, artefacts=artefacts)
    source = tmp_path / load_document(mapping)["sources"][0]["path"]
    source.write_bytes(source.read_bytes() + b"\nchanged mapping review\n")
    result = validate_project_state(state, scope="implementation")
    assert not result["valid"]
    assert {"mapping", "mapping-record"} <= set(result["stale_artefacts"])
    assert "parameter-record" not in result["stale_artefacts"]


def test_parameter_record_cannot_depend_on_a_different_c_path_with_identical_bytes(tmp_path):
    mapping = make_mapping_contract(tmp_path)
    value = load_document(mapping)
    model = tmp_path / value["model"]["path"]
    copy = tmp_path / "copied-approved-model.json"
    copy.write_bytes(model.read_bytes())
    parameters = tmp_path / value["parameters"]["path"]
    parameter_value = load_document(parameters)
    parameter_value["model"]["path"] = copy.name
    parameters.write_text(json.dumps(parameter_value), encoding="utf-8")
    value["parameters"]["sha256"] = sha256_file(parameters)
    mapping.write_text(json.dumps(value), encoding="utf-8")
    state = write_mapping_state(tmp_path, mapping, artefacts=mapping_artefacts(tmp_path, mapping))
    result = validate_project_state(state, scope="implementation")
    assert not result["valid"]
    assert "parameter-record" in result["stale_artefacts"]


def test_d_dependency_cycle_is_rejected_without_recursion(tmp_path):
    mapping = make_mapping_contract(tmp_path)
    artefacts = mapping_artefacts(tmp_path, mapping)
    artefacts[0]["depends_on"].append("mapping-record")
    state = write_mapping_state(tmp_path, mapping, artefacts=artefacts)
    result = validate_project_state(state, scope="implementation")
    assert not result["valid"]
    assert any("dependency cycle" in error for error in result["errors"])


def ready_native_project(root, *, artefacts=True):
    """Complete Python evidence fixtures; no actual MATLAB qualification is implied."""
    from native_factory import make_implementation_profile, make_implementation_receipt
    from test_runtime import make_profile
    from validate_domain_mapping import validate_domain_mapping

    mapping = make_mapping_contract(root)
    profile = make_profile(root / "runtime")
    native_profile = make_implementation_profile(root / "native-profile", profile)
    receipt = make_implementation_receipt(root / "native-run", mapping, profile, native_profile)
    value = load_document(mapping)
    value["status"] = "ready"
    value["implementation"] = {"path": receipt.relative_to(root).as_posix(), "sha256": sha256_file(receipt)}
    mapping.write_text(json.dumps(value), encoding="utf-8")
    report = validate_domain_mapping(mapping, project_root=root, require_ready=True)
    assert report["valid"] and report["implementation_ready"], report["errors"]
    items = mapping_artefacts(root, mapping) if artefacts else []
    if artefacts:
        model_path = root / report["native_structure_validation"]["model_path"]
        anchors = ["problem", "model", "approval", "mapping"]
        items.append(d_artefact(root, model_path, "implementation_model", "native-model-record", anchors + ["mapping-record"]))
        items.append(d_artefact(root, receipt, "structure_evidence", "structure-record", anchors + ["native-model-record"]))
    state = write_mapping_state(root, mapping, stage="IMPLEMENTATION_READY", profile=profile,
                                implementation_profile=native_profile, artefacts=items)
    return mapping, profile, native_profile, receipt, state


def test_ready_state_requires_and_consumes_complete_native_evidence_without_writes(tmp_path):
    mapping, profile, native_profile, receipt, state = ready_native_project(tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    result = validate_project_state(state, scope="implementation")
    assert result["valid"] and result["implementation_ready"], result["errors"]
    assert result["implementation_checked"] and not result["environment_checked"]
    assert result["mapping_validation"]["native_structure_validation"]["receipt_sha256"] == sha256_file(receipt)
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before
    for scope in ("problem", "model"):
        report = validate_project_state(state, scope=scope)
        assert report["valid"] and not report["implementation_checked"] and not report["implementation_ready"]


def test_changed_slx_invalidates_structure_and_dependents_while_current_parameters_survive(tmp_path):
    mapping, profile, native_profile, receipt, state = ready_native_project(tmp_path)
    original = validate_project_state(state, scope="implementation")
    assert original["valid"], original["errors"]
    model_path = original["mapping_validation"]["native_structure_validation"]["model_path"]
    from pathlib import Path
    path = Path(model_path)
    path.write_bytes(path.read_bytes() + b"changed SLX bytes")
    result = validate_project_state(state, scope="implementation")
    assert not result["valid"] and not result["implementation_ready"]
    assert {"mapping", "mapping-record", "native-model-record", "structure-record"} <= set(result["stale_artefacts"])
    assert "parameter-record" not in result["stale_artefacts"]


def test_ready_stage_rejects_declared_stale_native_evidence_without_accepted_dependents(tmp_path):
    mapping, profile, native_profile, receipt, state = ready_native_project(tmp_path)
    value = load_document(state)
    value["artefacts"] = [item for item in value["artefacts"] if item["role"] != "structure_evidence"]
    native = next(item for item in value["artefacts"] if item["role"] == "implementation_model")
    native["status"] = "stale"
    state.write_text(json.dumps(value), encoding="utf-8")
    result = validate_project_state(state, scope="implementation")
    assert not result["valid"] and not result["implementation_ready"]
    assert any("cannot retain stale implementation dependencies" in error for error in result["errors"])


def test_expired_current_runtime_blocks_new_route_but_preserves_historical_structure(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    import validate_environment
    import validate_implementation_profile
    from resolve_runtime import resolve_runtime

    mapping, profile, native_profile, receipt, state = ready_native_project(tmp_path)
    future = datetime.now(timezone.utc) + timedelta(hours=25)

    class FutureClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromisoformat(future.isoformat()).astimezone(tz) if tz else cls.fromisoformat(future.replace(tzinfo=None).isoformat())

    monkeypatch.setattr(validate_environment, "datetime", FutureClock)
    monkeypatch.setattr(validate_implementation_profile, "datetime", FutureClock)
    partial = validate_project_state(state, scope="implementation")
    assert partial["valid"] and partial["implementation_ready"], partial["errors"]
    full = validate_project_state(state)
    assert not full["valid"]
    assert {"environment", "implementation_environment"} <= set(full["stale_artefacts"])
    assert not {"mapping", "mapping-record", "native-model-record", "structure-record"} & set(full["stale_artefacts"])
    route = resolve_runtime("simulink_build", state_path=state)
    assert route["status"] == "blocked" and not route["implementation_execution_allowed"]


@pytest.mark.parametrize("change", ["native_path", "receipt_path", "missing_native_dependency"])
def test_accepted_native_evidence_requires_exact_files_and_closed_chain(tmp_path, change):
    mapping, profile, native_profile, receipt, state = ready_native_project(tmp_path)
    value = load_document(state)
    if change == "native_path":
        item = next(item for item in value["artefacts"] if item["role"] == "implementation_model")
        copied = tmp_path / "copied.slx"
        copied.write_bytes((tmp_path / item["path"]).read_bytes())
        item["path"] = copied.name
    elif change == "receipt_path":
        item = next(item for item in value["artefacts"] if item["role"] == "structure_evidence")
        copied = tmp_path / "copied-receipt.json"
        copied.write_bytes(receipt.read_bytes())
        item["path"] = copied.name
    else:
        item = next(item for item in value["artefacts"] if item["role"] == "structure_evidence")
        item["depends_on"] = ["problem", "model", "approval", "mapping", "mapping-record"]
    state.write_text(json.dumps(value), encoding="utf-8")
    result = validate_project_state(state, scope="implementation")
    assert not result["valid"] and not result["implementation_ready"]


@pytest.mark.parametrize("field", ["implementation_execution_allowed", "business_execution_allowed", "simulation_execution_allowed", "mapping_contract_sha256"])
def test_accepted_build_route_is_recomputed_against_both_profiles_and_current_mapping(tmp_path, field):
    from resolve_runtime import resolve_runtime

    mapping, profile, native_profile, receipt, state = ready_native_project(tmp_path)
    route = resolve_runtime("simulink_build", state_path=state)
    assert route["status"] == "allowed", route["errors"]
    route_path = tmp_path / "build-route.json"
    route_path.write_text(json.dumps(route), encoding="utf-8")
    value = load_document(state)
    value["artefacts"].append(d_artefact(tmp_path, route_path, "implementation_route_decision", "build-route-record",
        ["environment", "implementation_environment", "problem", "model", "approval", "mapping", "mapping-record"]))
    state.write_text(json.dumps(value), encoding="utf-8")
    assert validate_project_state(state)["valid"]
    route[field] = "0" * 64 if field.endswith("sha256") else not route[field]
    route_path.write_text(json.dumps(route), encoding="utf-8")
    value["artefacts"][-1]["sha256"] = sha256_file(route_path)
    state.write_text(json.dumps(value), encoding="utf-8")
    result = validate_project_state(state)
    assert not result["valid"] and "build-route-record" in result["stale_artefacts"]
