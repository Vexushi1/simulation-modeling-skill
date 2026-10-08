"""Parameter bindings preserve approved values and never estimate missing ones."""
from __future__ import annotations

import copy

import pytest

from mapping_factory import make_mapping_contract
from model_factory import approve_contract, file_ref
from problem_factory import read_contract, write_contract
from runtime_common import canonical_digest
from validate_parameter_provenance import validate_parameter_provenance


def parameter_path(tmp_path, **kwargs):
    mapping = read_contract(make_mapping_contract(tmp_path, **kwargs))
    return tmp_path / mapping["parameters"]["path"]


def mutate(path, action):
    contract = read_contract(path)
    action(contract)
    write_contract(path, contract)
    return validate_parameter_provenance(path)


@pytest.mark.parametrize("known", [True, False])
def test_parameter_binding_preserves_known_and_unknown_values(tmp_path, known):
    path = parameter_path(tmp_path, known_parameters=known)
    before = path.read_bytes()
    report = validate_parameter_provenance(path, require_bound=True)
    assert report["valid"] and report["binding_complete"] and report["current_model_approved"]
    assert report["parameters"][0]["value"] == (2.0 if known else None)
    assert path.read_bytes() == before
    assert report["model_approval_path"] and report["locked_model_path"]


def test_legal_empty_draft_does_not_bind_a_model(tmp_path):
    path = write_contract(tmp_path / "draft.json", {"schema_version": 1, "project_id": "draft", "status": "draft", "model": None, "parameters": []})
    report = validate_parameter_provenance(path)
    assert report["schema_valid"] and report["valid"] and not report["binding_complete"]
    assert not validate_parameter_provenance(path, require_bound=True)["valid"]


def test_complete_draft_reports_content_without_becoming_bound(tmp_path):
    path = parameter_path(tmp_path)
    report = mutate(path, lambda contract: contract.update(status="draft"))
    assert report["valid"] and report["binding_complete"] and report["status"] == "draft"
    assert not validate_parameter_provenance(path, require_bound=True)["valid"]
    assert read_contract(path)["status"] == "draft"


@pytest.mark.parametrize("field,value", [("value", True), ("value", 2), ("value", 7.0), ("unit", "W"),
    ("provenance", "identified"), ("source_ids", []), ("symbol", "replacement")])
def test_parameter_fields_match_current_c_with_exact_json_types(tmp_path, field, value):
    path = parameter_path(tmp_path)
    report = mutate(path, lambda contract: contract["parameters"][0].update({field: value}))
    assert not report["valid"] and not report["binding_complete"]
    assert any(f"{field} differs" in error for error in report["errors"])


@pytest.mark.parametrize("change", [
    lambda contract: contract["parameters"].append(copy.deepcopy(contract["parameters"][0])),
    lambda contract: contract["parameters"][0]["reference"].update(variable_id="missing"),
    lambda contract: contract["parameters"].clear(),
    lambda contract: contract["parameters"][0].update(code_name="for"),
    lambda contract: contract["parameters"][0]["scope"].update(data_source="MAT-File"),
    lambda contract: contract["parameters"][0]["uncertainty"].update(value=0),
    lambda contract: contract["parameters"][0]["uncertainty"].update(status="specified"),
])
def test_incomplete_or_inconsistent_parameter_bindings_fail(tmp_path, change):
    path = parameter_path(tmp_path)
    report = mutate(path, change)
    assert not report["valid"] and not report["binding_complete"]


def test_code_names_are_unique_in_same_model_workspace(tmp_path):
    path = parameter_path(tmp_path, case="feedback")
    report = mutate(path, lambda contract: contract["parameters"][1].update(code_name=contract["parameters"][0]["code_name"]))
    assert not report["valid"] and any("duplicate code_name" in error for error in report["errors"])


def test_changed_design_source_invalidates_current_parameter_bindings(tmp_path):
    path = parameter_path(tmp_path)
    source = tmp_path / "design-foundation.txt"
    source.write_text(source.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
    report = validate_parameter_provenance(path)
    assert not report["valid"] and not report["current_model_approved"] and report["changed_sources"]


def test_byte_rebinding_cannot_reuse_old_human_decision(tmp_path):
    path = parameter_path(tmp_path)
    model_path = tmp_path / "model.json"
    model = read_contract(model_path)
    model["designs"][0]["models"][0]["body"]["variables"][-1]["parameter"]["value"] = 3.0
    write_contract(model_path, model)
    contract = read_contract(path)
    contract["model"] = file_ref(tmp_path, model_path)
    contract["parameters"][0]["value"] = 3.0
    write_contract(path, contract)
    report = validate_parameter_provenance(path)
    assert not report["valid"] and not report["current_model_approved"]


def test_valid_c_alternative_does_not_skip_selected_parameter_coverage(tmp_path):
    path = parameter_path(tmp_path)
    contract = read_contract(path)
    alternate = copy.deepcopy(contract["parameters"][0])
    alternate["reference"]["model_id"] = "missing_model"
    contract["parameters"] = [alternate]
    write_contract(path, contract)
    report = validate_parameter_provenance(path)
    assert not report["valid"] and "main_model_parameter_coverage" in report["missing_gates"]


@pytest.mark.parametrize("body", ['{"x":NaN}', '{"x":1,"x":2}', "[]", "broken: ["])
def test_malformed_and_nonfinite_inputs_fail_without_writes(tmp_path, body):
    path = tmp_path / ("parameters.yaml" if body == "broken: [" else "parameters.json")
    path.write_text(body, encoding="utf-8")
    before = path.read_bytes()
    assert not validate_parameter_provenance(path)["valid"] and path.read_bytes() == before


def test_bound_file_paths_cannot_escape_project_root(tmp_path):
    path = parameter_path(tmp_path)
    report = mutate(path, lambda contract: contract["model"].update(path="../outside.json"))
    assert not report["valid"] and any("leaves project root" in error for error in report["errors"])


def test_parameter_semantic_digest_excludes_only_status(tmp_path):
    path = parameter_path(tmp_path)
    before = validate_parameter_provenance(path)["semantic_sha256"]
    report = mutate(path, lambda contract: contract.update(status="draft"))
    assert report["semantic_sha256"] == before
    report = mutate(path, lambda contract: contract["parameters"][0]["tunability"].update(reason="Changed review rationale"))
    assert report["semantic_sha256"] != before
