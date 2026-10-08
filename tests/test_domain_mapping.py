"""Source-bound D mapping gates, support bounds and read-only failure paths."""
from __future__ import annotations

import copy
import subprocess
import sys

import pytest

from mapping_factory import make_mapping_contract
from model_factory import approve_contract, file_ref
from problem_factory import read_contract, write_contract
from runtime_common import ROOT, sha256_file
from validate_domain_mapping import semantic_digest, validate_domain_mapping
from validate_implementation_profile import validate_build_spec


def mutate(path, action):
    contract = read_contract(path)
    action(contract)
    write_contract(path, contract)
    return validate_domain_mapping(path)


def rebind_parameters(path, action):
    mapping = read_contract(path)
    parameter_path = path.parent / mapping["parameters"]["path"]
    parameters = read_contract(parameter_path)
    action(parameters)
    write_contract(parameter_path, parameters)
    mapping["parameters"] = file_ref(path.parent, parameter_path)
    write_contract(path, mapping)
    return validate_domain_mapping(path)


@pytest.mark.parametrize("case", ["static", "feedback", "constant"])
def test_source_bound_distinct_native_specs_without_simulation(tmp_path, case):
    path = make_mapping_contract(tmp_path, case=case)
    before = {item: item.read_bytes() for item in tmp_path.iterdir() if item.is_file()}
    report = validate_domain_mapping(path, require_mapped=True)
    assert report["valid"] and report["mapping_complete"] and report["build_ready"]
    assert not report["built"] and not report["structure_checked"] and not report["implementation_ready"]
    assert report["model_sha256"] == sha256_file(tmp_path / "model.json")
    assert report["parameters_sha256"] == sha256_file(tmp_path / "parameters.json")
    assert report["build_spec"]["model_name"] == f"synthetic_{case}"
    assert validate_build_spec(report["build_spec"]) == report["build_spec"]
    assert {item: item.read_bytes() for item in before} == before


def test_empty_draft_is_legal_without_environment_or_model_approval(tmp_path):
    path = make_mapping_contract(tmp_path, status="draft")
    contract = read_contract(path)
    contract.update(model=None, parameters=None, targets=[], sources=[], implementation=None)
    for review in contract["reviews"].values():
        review.update(status="pending", source_ids=[])
    write_contract(path, contract)
    report = validate_domain_mapping(path)
    assert report["schema_valid"] and report["valid"] and not report["mapping_complete"]
    assert not report["build_ready"] and not validate_domain_mapping(path, require_mapped=True)["valid"]


def test_complete_draft_never_becomes_a_formal_build(tmp_path):
    path = make_mapping_contract(tmp_path, status="draft")
    report = validate_domain_mapping(path)
    assert report["valid"] and report["mapping_complete"] and not report["build_ready"]
    assert read_contract(path)["status"] == "draft"


def test_parameters_draft_content_does_not_activate_mapped_build(tmp_path):
    path = make_mapping_contract(tmp_path)
    report = rebind_parameters(path, lambda parameters: parameters.update(status="draft"))
    assert not report["valid"] and not report["mapping_complete"] and not report["build_ready"]
    assert report["parameter_validation"]["binding_complete"]
    assert "current_parameter_bindings" in report["missing_gates"]


def test_parameter_code_name_cannot_collide_with_native_model_name(tmp_path):
    path = make_mapping_contract(tmp_path)
    before = validate_domain_mapping(path)
    invalid_spec = copy.deepcopy(before["build_spec"])
    name = invalid_spec["model_name"]
    invalid_spec["parameters"][0]["code_name"] = name
    invalid_spec["blocks"][2]["parameters"]["Gain"] = name
    with pytest.raises(ValueError, match="parameter name"):
        validate_build_spec(invalid_spec)
    report = rebind_parameters(path, lambda parameters: parameters["parameters"][0].update(code_name=name))
    assert report["valid"] and report["mapping_complete"] and not report["build_ready"]
    assert report["build_spec"] is None
    assert f"native_parameter_model_name_collision:{name}" in report["native_missing_gates"]


def test_approved_constant_graph_requires_no_inport(tmp_path):
    path = make_mapping_contract(tmp_path, case="constant")
    model = read_contract(tmp_path / "model.json")
    assert model["designs"][0]["models"][0]["body"]["inputs"] == []
    assert "No external input is required" in (tmp_path / "statement.txt").read_text(encoding="utf-8")
    assert "y = k" in (tmp_path / "design-foundation.txt").read_text(encoding="utf-8")
    report = validate_domain_mapping(path, require_mapped=True)
    assert report["current_model_approved"] and report["build_ready"] and report["valid"]
    spec = report["build_spec"]
    assert {block["type"] for block in spec["blocks"]} == {"Constant", "Outport"}
    assert spec["connections"] == [{"source": {"block_id": "Coefficient", "port": 1}, "destination": {"block_id": "Output", "port": 1}}]
    assert validate_build_spec(spec) == spec


def test_internal_mathematical_output_requires_no_root_outport(tmp_path):
    path = make_mapping_contract(tmp_path, root_output=False)
    assert "no root Outport" in (tmp_path / "statement.txt").read_text(encoding="utf-8")
    report = validate_domain_mapping(path, require_mapped=True)
    assert report["current_model_approved"] and report["build_ready"] and report["valid"]
    spec = report["build_spec"]
    assert {block["type"] for block in spec["blocks"]} == {"Inport", "Gain"}
    assert spec["connections"] == [{"source": {"block_id": "Input", "port": 1}, "destination": {"block_id": "GainK", "port": 1}}]
    target = read_contract(path)["targets"][0]
    output = next(trace for trace in target["traces"] if trace["kind"] == "output")
    assert output["subject_id"] == "y" and output["block_ids"] == ["GainK"]
    assert validate_build_spec(spec) == spec


@pytest.mark.parametrize("case,root_output,gate", [("constant", True, "Output"), ("static", False, "GainK")])
def test_optional_root_ports_do_not_relax_required_block_input_connections(tmp_path, case, root_output, gate):
    path = make_mapping_contract(tmp_path, case=case, root_output=root_output)
    report = mutate(path, lambda mapping: mapping["targets"][0].update(connections=[]))
    assert report["valid"] and report["mapping_complete"] and not report["build_ready"]
    assert f"native_required_input_connection:{gate}" in report["native_missing_gates"]


def test_final_native_spec_check_catches_actual_builder_support_limits(tmp_path):
    path = make_mapping_contract(tmp_path)
    model_path = tmp_path / "model.json"
    model = read_contract(model_path)
    model["designs"][0]["models"][0]["body"]["variables"][-1]["unit"] = "x" * 129
    write_contract(model_path, model)
    approve_contract(model_path)
    parameters_path = tmp_path / "parameters.json"
    parameters = read_contract(parameters_path)
    parameters["parameters"][0]["unit"] = "x" * 129
    parameters["model"] = file_ref(tmp_path, model_path)
    write_contract(parameters_path, parameters)
    mapping = read_contract(path)
    mapping.update(model=file_ref(tmp_path, model_path), parameters=file_ref(tmp_path, parameters_path))
    write_contract(path, mapping)
    report = validate_domain_mapping(path)
    assert report["valid"] and report["mapping_complete"] and not report["build_ready"]
    assert any("native_builder_spec:build_spec: invalid unit" == gate for gate in report["native_missing_gates"])


def test_unknown_parameters_stay_unknown_and_block_native_only(tmp_path):
    path = make_mapping_contract(tmp_path, known_parameters=False)
    report = validate_domain_mapping(path, require_mapped=True)
    assert report["valid"] and report["mapping_complete"] and not report["build_ready"]
    assert "native_parameter_scalar_known:k" in report["missing_gates"]
    assert report["parameter_validation"]["parameters"][0]["value"] is None
    assert not validate_domain_mapping(path, require_ready=True)["valid"]


@pytest.mark.parametrize("domain", ["simscape", "stateflow", "system_composer", "matlab"])
def test_domain_decision_is_implemented_but_native_operation_deferred(tmp_path, domain):
    path = make_mapping_contract(tmp_path)
    report = mutate(path, lambda contract: contract["targets"][0].update(domain=domain, reason=f"Reviewed synthetic {domain} selection"))
    assert report["valid"] and report["mapping_complete"] and not report["build_ready"]
    assert f"native_domain_deferred:{domain}" in report["native_missing_gates"]


@pytest.mark.parametrize("change", [
    lambda contract: contract["targets"][0]["traces"].pop(),
    lambda contract: contract["targets"][0]["traces"][0].update(block_ids=["missing"]),
    lambda contract: contract["targets"][0]["traces"][0].update(subject_id="unknown_relation"),
    lambda contract: contract["targets"][0]["traces"][0].update(disposition="not_applicable", block_ids=[]),
    lambda contract: contract["targets"][0]["connections"][0]["destination"].update(block_id="missing"),
    lambda contract: contract["targets"][0]["connections"].append(copy.deepcopy(contract["targets"][0]["connections"][0])),
    lambda contract: contract["targets"][0]["blocks"].append(copy.deepcopy(contract["targets"][0]["blocks"][0])),
    lambda contract: contract["targets"][0].update(model_id="other"),
    lambda contract: contract["reviews"]["mathematical_semantics"].update(status="blocked"),
    lambda contract: contract["targets"][0]["blocks"][0].pop("purpose"),
])
def test_incomplete_traces_references_reviews_and_objects_fail_mapped(tmp_path, change):
    report = mutate(make_mapping_contract(tmp_path), change)
    assert not report["valid"] and not report["mapping_complete"] and not report["build_ready"]


def test_many_objects_can_trace_one_relation_without_fixed_hierarchy(tmp_path):
    path = make_mapping_contract(tmp_path, case="feedback")
    contract = read_contract(path)
    contract["targets"][0]["traces"][0]["block_ids"] = ["Input", "GainB", "Balance", "State", "GainA", "Output"]
    write_contract(path, contract)
    report = validate_domain_mapping(path)
    assert report["valid"] and report["mapping_complete"] and report["build_ready"]


def test_mixed_targets_collectively_cover_one_current_main_model(tmp_path):
    path = make_mapping_contract(tmp_path)
    contract = read_contract(path)
    other = copy.deepcopy(contract["targets"][0])
    other.update(id="other_domain", domain="stateflow", model_name="other_component", coupling="Synthetic explicit mixed-domain interface")
    other["traces"] = contract["targets"][0]["traces"][:2]
    contract["targets"][0]["traces"] = contract["targets"][0]["traces"][2:]
    contract["targets"].append(other)
    write_contract(path, contract)
    report = validate_domain_mapping(path)
    assert report["valid"] and report["mapping_complete"] and not report["build_ready"]
    assert "native_single_target_required" in report["native_missing_gates"]


@pytest.mark.parametrize("change,gate", [
    (lambda target: target["blocks"][2].update(type="MATLABFunction"), "native_block_deferred:MATLABFunction"),
    (lambda target: target["blocks"][2].update(path="other_model/GainK"), "native_flat_block_path:GainK"),
    (lambda target: target["blocks"][2]["parameters"].update(Gain={"setting": {"kind": "enum", "value": "1/k"}}), "native_parameter_ref_required:GainK.Gain"),
    (lambda target: target["connections"][0]["destination"].update(port=2), "native_endpoint:GainK:2"),
    (lambda target: target["blocks"][0]["parameters"]["Port"]["setting"].update(value=2), "native_contiguous_inport_ports"),
])
def test_native_supported_scope_is_separate_from_text_mapping(tmp_path, change, gate):
    path = make_mapping_contract(tmp_path)
    report = mutate(path, lambda contract: change(contract["targets"][0]))
    assert report["valid"] and report["mapping_complete"] and not report["build_ready"]
    assert gate in report["native_missing_gates"]


def test_arbitrary_literal_value_cannot_enter_block_schema(tmp_path):
    path = make_mapping_contract(tmp_path)
    report = mutate(path, lambda contract: contract["targets"][0]["blocks"][2]["parameters"].update(Gain={"value": "eval('1')"}))
    assert not report["schema_valid"] and not report["valid"]


@pytest.mark.parametrize("selector", [["missing"], [-1], [True], ["x", "code()"]])
def test_condition_selector_is_structured_current_c_reference(tmp_path, selector):
    path = make_mapping_contract(tmp_path, case="feedback")
    report = mutate(path, lambda contract: contract["targets"][0]["blocks"][-1]["parameters"]["InitialCondition"]["value_ref"].update(selector=selector))
    assert not report["valid"] and not report["build_ready"]


def test_integrator_default_initial_condition_cannot_supply_missing_approval(tmp_path):
    path = make_mapping_contract(tmp_path, case="feedback")
    report = mutate(path, lambda contract: contract["targets"][0]["blocks"][-1].update(parameters={}))
    assert report["valid"] and report["mapping_complete"] and not report["build_ready"]
    assert "native_explicit_parameters:State" in report["native_missing_gates"]


@pytest.mark.parametrize("value", [True, "2", [2], 2**53 + 1, 10**400])
def test_non_native_c_values_are_preserved_without_conversion(tmp_path, value):
    path = make_mapping_contract(tmp_path)
    model_path = tmp_path / "model.json"
    model = read_contract(model_path)
    model["designs"][0]["models"][0]["body"]["variables"][-1]["parameter"]["value"] = value
    write_contract(model_path, model)
    approve_contract(model_path)
    mapping = read_contract(path)
    parameters_path = tmp_path / "parameters.json"
    parameters = read_contract(parameters_path)
    parameters["model"] = file_ref(tmp_path, model_path)
    parameters["parameters"][0]["value"] = value
    write_contract(parameters_path, parameters)
    mapping.update(model=file_ref(tmp_path, model_path), parameters=file_ref(tmp_path, parameters_path))
    write_contract(path, mapping)
    report = validate_domain_mapping(path)
    assert report["valid"] and report["mapping_complete"] and not report["build_ready"]
    assert report["parameter_validation"]["parameters"][0]["value"] == value


def test_old_approval_cannot_be_reused_after_model_path_rebinding(tmp_path):
    path = make_mapping_contract(tmp_path)
    model_path = tmp_path / "model.json"
    model = read_contract(model_path)
    model["designs"][0]["selection_reason"] += " changed"
    write_contract(model_path, model)
    report = mutate(path, lambda contract: contract.update(model=file_ref(tmp_path, model_path)))
    assert not report["valid"] and not report["current_model_approved"]


def test_ready_flag_without_real_structure_evidence_fails(tmp_path):
    path = make_mapping_contract(tmp_path, status="ready")
    report = validate_domain_mapping(path, require_ready=True)
    assert not report["valid"] and not report["implementation_ready"] and not report["built"]
    assert "actual_native_structure_receipt" in report["missing_gates"]


def test_changed_mapping_review_source_invalidates_mapped(tmp_path):
    path = make_mapping_contract(tmp_path)
    source = tmp_path / "mapping-review.txt"
    source.write_text("changed review\n", encoding="utf-8")
    report = validate_domain_mapping(path)
    assert not report["valid"] and not report["mapping_complete"]
    assert "mapping_source:mapping_review" in report["changed_sources"]


def test_mapping_digest_excludes_status_and_receipt_only(tmp_path):
    path = make_mapping_contract(tmp_path)
    contract = read_contract(path)
    digest = semantic_digest(contract)
    contract.update(status="ready", implementation={"path": "future.json", "sha256": "a" * 64})
    assert semantic_digest(contract) == digest
    contract["targets"][0]["reason"] += " additional reasoning"
    assert semantic_digest(contract) != digest


def test_cli_validator_is_read_only_and_returns_missing_ready_gate(tmp_path):
    path = make_mapping_contract(tmp_path)
    before = path.read_bytes()
    completed = subprocess.run([sys.executable, str(ROOT / "scripts/validate_domain_mapping.py"), str(path), "--require-ready"], capture_output=True, text=True, check=False)
    assert completed.returncode == 1 and '"implementation_ready": false' in completed.stdout
    assert path.read_bytes() == before


def test_missing_and_path_escape_are_controlled_failures(tmp_path):
    assert not validate_domain_mapping(tmp_path / "missing.json")["valid"]
    path = make_mapping_contract(tmp_path)
    report = mutate(path, lambda contract: contract["parameters"].update(path="../parameters.json"))
    assert not report["valid"] and any("leaves project root" in error for error in report["errors"])
