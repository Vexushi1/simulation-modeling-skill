"""Protocol/freeze and source identity consumers; fixtures never qualify MATLAB."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from model_factory import approve_contract, file_ref
from problem_factory import write_contract
from runtime_common import ROOT, load_document, sha256_file
from simulation_factory import freeze_simulation_protocol, make_simulation_protocol
from validate_simulation_protocol import semantic_digest, validate_simulation_protocol


def rewrite(path, change, *, freeze=True):
    value = load_document(path)
    change(value)
    write_contract(path, value)
    if freeze:
        freeze_simulation_protocol(path)
    return value


def check(path, **kwargs):
    return validate_simulation_protocol(path, project_root=path.parent, **kwargs)


def test_legal_draft_template_is_read_only_and_preserves_unknowns(tmp_path):
    path = tmp_path / "protocol.yaml"
    path.write_bytes((ROOT / "templates/contracts/simulation_protocol.yaml").read_bytes())
    before = path.read_bytes()
    result = check(path)
    assert result["schema_valid"] and result["valid"], result["errors"]
    assert not result["protocol_complete"] and not result["frozen"] and not result["execution_ready"]
    assert not result["environment_checked"] and not result["execution_allowed"]
    assert {"solver_decision", "current_implementation_ready_mapping", "reviewed_scenario", "source_bound_protocol_freeze"} <= set(result["missing_gates"])
    assert path.read_bytes() == before
    assert not check(path, require_frozen=True)["valid"]


@pytest.mark.parametrize("case", ["feedback", "static", "constant", "passthrough"])
@pytest.mark.parametrize("solver", ["ode45", "ode4", "ode15s"])
def test_current_frozen_contract_exposes_exact_structural_run_spec_without_runtime_permission(tmp_path, case, solver):
    path = make_simulation_protocol(tmp_path, case=case, solver=solver)
    before = {item: item.read_bytes() for item in tmp_path.rglob("*") if item.is_file()}
    result = check(path, require_frozen=True)
    assert result["valid"] and result["frozen"] and result["protocol_complete"] and result["execution_ready"], result["errors"]
    assert result["mapping_validation"]["implementation_ready"]
    assert result["mapping_validation"]["current_model_approved"]
    assert result["problem_validation"]["frozen"]
    assert not result["environment_checked"] and not result["execution_allowed"]
    spec = result["run_spec"]
    assert spec["model_path"] == result["native_model_path"]
    assert spec["parameters"] == result["mapping_validation"]["build_spec"]["parameters"]
    assert spec["solver"]["name"] == solver
    assert result["selected_solver"] == solver and result["selected_operation_id"] == "simulink.core_simulation"
    assert spec["start_time"] == 0.0 and spec["stop_time"] == 1.0 and spec["seed"] == 1729
    assert spec["runtime_class"] == "normal_serial" and spec["warning_policy"] == "record"
    assert all(item["sample_time"] == 0 for item in spec["outputs"])
    assert len(spec["inputs"]) == int(case != "constant") and len(spec["outputs"]) == 1
    if case == "passthrough":
        assert spec["parameters"] == []
    if spec["inputs"]:
        assert spec["inputs"][0]["time"] == [0.0, 1.0]
        assert spec["inputs"][0]["values"] == [1.0, 1.0]
    assert {item: item.read_bytes() for item in tmp_path.rglob("*") if item.is_file()} == before


def test_complete_draft_is_not_frozen_and_cannot_execute(tmp_path):
    path = make_simulation_protocol(tmp_path, status="draft")
    result = check(path)
    assert result["valid"] and result["protocol_complete"] and result["run_spec"]
    assert not result["frozen"] and not result["execution_ready"]
    assert not check(path, require_frozen=True)["valid"]


@pytest.mark.parametrize("sample_time", [None, False, True, "0", -1, 0.1])
def test_root_output_sampling_requires_explicit_typed_continuous_setting(tmp_path, sample_time):
    path = make_simulation_protocol(tmp_path)
    rewrite(path, lambda value: value["logging"].update(sample_time=sample_time), freeze=False)
    result = check(path)
    assert not result["schema_valid"] and not result["execution_ready"]


def test_missing_output_sampling_cannot_reuse_existing_freeze(tmp_path):
    path = make_simulation_protocol(tmp_path)
    before = check(path)
    value = load_document(path)
    del value["logging"]["sample_time"]
    write_contract(path, value)
    result = check(path)
    assert not result["schema_valid"] and not result["frozen"] and not result["execution_ready"]
    assert sha256_file(Path(before["model_path"])) == before["model_sha256"]
    assert sha256_file(Path(before["native_model_path"])) == before["native_model_sha256"]


def test_historical_ready_d_structure_is_not_rejected_for_current_environment_ttl(tmp_path):
    path = make_simulation_protocol(tmp_path, age_hours=25)
    result = check(path, require_frozen=True)
    assert result["valid"] and result["execution_ready"], result["errors"]
    assert not result["environment_checked"]


@pytest.mark.parametrize("field", ["solver", "scenario", "time", "seed", "conditions", "logging", "warning_policy", "selection", "parameter_set", "mapping"])
def test_missing_required_content_cannot_be_frozen_even_after_review_rebound(tmp_path, field):
    path = make_simulation_protocol(tmp_path)
    rewrite(path, lambda value: value.update({field: None}))
    result = check(path)
    assert not result["valid"] and not result["protocol_complete"] and not result["frozen"]
    assert not result["execution_ready"] and result["missing_gates"]


@pytest.mark.parametrize("change", ["no_record", "no_decision", "wrong_project", "wrong_digest", "agent_approve_action", "bad_quote", "rejection_context", "duplicate_context"])
def test_frozen_flag_and_source_record_do_not_substitute_for_current_explicit_freeze(tmp_path, change):
    path = make_simulation_protocol(tmp_path)
    contract = load_document(path)
    record_path = tmp_path / contract["freeze_record"]["path"]
    record = load_document(record_path)
    if change == "no_record":
        contract["freeze_record"] = None
    elif change == "no_decision":
        (tmp_path / record["decision"]["path"]).unlink()
    elif change == "wrong_project":
        record["project_id"] = "different-project"
    elif change == "wrong_digest":
        record["protocol_semantic_sha256"] = "0" * 64
    elif change == "agent_approve_action":
        record["decision"]["action"] = "approve"
    elif change == "bad_quote":
        record["decision"]["quote"] += "not in the decision text"
    else:
        decision = record["decision"]
        quote = decision["quote"]
        quote = quote.replace("action=freeze", "action=reject") if change == "rejection_context" else quote + "\naction=freeze"
        decision_path = tmp_path / decision["path"]
        decision_path.write_text(quote + "\n", encoding="utf-8")
        decision.update(quote=quote, end=len(quote), sha256=sha256_file(decision_path))
    write_contract(record_path, record)
    if contract["freeze_record"] is not None:
        contract["freeze_record"]["sha256"] = sha256_file(record_path)
    write_contract(path, contract)
    result = check(path)
    assert not result["valid"] and not result["frozen"] and not result["execution_ready"]


def test_solver_only_change_preserves_c_d_identities_but_invalidates_old_freeze(tmp_path):
    path = make_simulation_protocol(tmp_path)
    before = check(path)
    rewrite(path, lambda value: value["solver"].update(rel_tol=1e-7), freeze=False)
    after = check(path)
    assert not after["valid"] and not after["frozen"]
    assert after["model_identity"] == before["model_identity"]
    assert after["model_sha256"] == before["model_sha256"] and after["mapping_sha256"] == before["mapping_sha256"]
    assert after["native_model_sha256"] == before["native_model_sha256"]
    freeze_simulation_protocol(path)
    assert check(path)["valid"]


@pytest.mark.parametrize("dependency", ["statement.txt", "design-foundation.txt", "model.json", "model-approval.json", "parameters.json", "mapping.json", "scenario-source.json", "implementation/synthetic_feedback.slx", "implementation/implementation-receipt.json"])
def test_actual_upstream_and_input_bytes_are_current_not_just_protocol_hash(tmp_path, dependency):
    path = make_simulation_protocol(tmp_path)
    target = tmp_path / dependency
    target.write_bytes(target.read_bytes() + b"\nchanged actual bytes\n")
    result = check(path)
    assert not result["valid"] and not result["frozen"] and not result["execution_ready"]


@pytest.mark.parametrize("change", ["wrong_project", "wrong_selection", "wrong_unit", "wrong_port", "wrong_trace", "duplicate_input", "duplicate_output", "no_input", "no_output", "changed_initial", "changed_boundary", "registry_copy"])
def test_current_identity_port_trace_and_condition_contracts_are_not_overridable(tmp_path, change):
    path = make_simulation_protocol(tmp_path)
    def modify(value):
        if change == "wrong_project":
            value["project_id"] = "different-project"
        elif change == "wrong_selection":
            value["selection"]["model_id"] = "different-model"
        elif change == "wrong_unit":
            value["inputs"][0]["unit"] = "m"
        elif change == "wrong_port":
            value["outputs"][0]["port"] = 2
        elif change == "wrong_trace":
            value["outputs"][0]["variable_id"] = "x"
        elif change == "duplicate_input":
            value["inputs"].append(dict(value["inputs"][0]))
        elif change == "duplicate_output":
            value["outputs"].append(dict(value["outputs"][0]))
        elif change == "no_input":
            value["inputs"] = []
        elif change == "no_output":
            value["outputs"] = []
        elif change == "changed_initial":
            value["conditions"]["initial_conditions"]["value"]["x"] = 0.0
        elif change == "changed_boundary":
            value["conditions"]["boundary_conditions"]["value"] = {"u": 1.0}
        else:
            original = tmp_path / value["parameter_set"]["path"]
            copied = tmp_path / "copied-parameters.json"
            copied.write_bytes(original.read_bytes())
            value["parameter_set"] = file_ref(tmp_path, copied)
    rewrite(path, modify)
    result = check(path)
    assert not result["valid"] and not result["execution_ready"]


def test_internal_output_is_valid_d_structure_but_cannot_supply_e_primary_run(tmp_path):
    path = make_simulation_protocol(tmp_path, case="constant", root_output=False)
    result = check(path)
    assert result["mapping_validation"]["implementation_ready"]
    assert not result["valid"] and not result["execution_ready"]
    assert "at_least_one_root_output" in result["missing_gates"]


@pytest.mark.parametrize("change", ["wrong_source", "invalid_selector", "data_mismatch", "value_type_mismatch", "text_source", "missing_source", "missing_data", "missing_requirement", "outside_scenario"])
def test_numeric_input_is_exactly_source_bound_and_reviewed(tmp_path, change):
    path = make_simulation_protocol(tmp_path)
    def modify(value):
        item = value["inputs"][0]
        if change == "wrong_source":
            item["source_ref"]["source_id"] = "unregistered"
        elif change == "invalid_selector":
            item["source_ref"]["selector"] = ["u", 0]
        elif change == "data_mismatch":
            item["data"]["value"] = 2.0
        elif change == "value_type_mismatch":
            item["data"]["value"] = 1
        elif change == "text_source":
            value["sources"][0].update(file_ref(tmp_path, tmp_path / "statement.txt"))
        elif change == "missing_source":
            item["source_ref"] = None
        elif change == "missing_data":
            item["source_ref"] = None
            item["data"] = None
        elif change == "missing_requirement":
            item["requirement_ids"] = []
        else:
            value["scenario"]["source_ids"] = []
    rewrite(path, modify)
    result = check(path)
    assert not result["valid"] and not result["execution_ready"]


@pytest.mark.parametrize("change", ["sampling_length", "nonmonotonic", "not_covered", "also_constant", "source_link", "source_id_collision"])
def test_sampled_input_and_source_links_have_precise_coverage_and_identity(tmp_path, change):
    path = make_simulation_protocol(tmp_path)
    value = load_document(path)
    data = {"kind": "sampled", "value": None, "time": [0.0, 0.5, 1.0], "values": [1.0, 2.0, 3.0], "interpolation": "linear"}
    if change == "sampling_length":
        data["values"] = [1.0]
    elif change == "nonmonotonic":
        data["time"] = [0.0, 1.0, 0.5]
    elif change == "not_covered":
        data["time"] = [0.1, 0.5, 0.9]
    elif change == "also_constant":
        data["value"] = 1.0
    elif change == "source_link":
        value["sources"][0]["model_source_id"] = "foundation"
    else:
        value["sources"].append(dict(value["sources"][0]))
    source = tmp_path / value["sources"][0]["path"]
    write_contract(source, {"u": data})
    value["inputs"][0]["data"] = data
    for item in value["sources"]:
        item["sha256"] = sha256_file(source)
    write_contract(path, value)
    freeze_simulation_protocol(path)
    assert not check(path)["valid"]


def test_explicit_sampled_source_is_flattened_without_expression_evaluation(tmp_path):
    path = make_simulation_protocol(tmp_path)
    value = load_document(path)
    data = {"kind": "sampled", "value": None, "time": [0.0, 0.5, 1.0], "values": [1.0, 2.0, 3.0], "interpolation": "linear"}
    source = tmp_path / value["sources"][0]["path"]
    write_contract(source, {"signals": [{"u": data}]})
    value["sources"][0]["sha256"] = sha256_file(source)
    value["inputs"][0].update(data=data, source_ref={"source_id": "scenario_data", "selector": ["signals", 0, "u"]})
    write_contract(path, value)
    freeze_simulation_protocol(path)
    result = check(path)
    assert result["valid"] and result["execution_ready"], result["errors"]
    assert result["run_spec"]["inputs"][0]["time"] == data["time"]
    assert result["run_spec"]["inputs"][0]["values"] == data["values"]


@pytest.mark.parametrize("input_value,accepted", [(2.0, True), (1.0, False), (2, False)])
def test_known_source_input_is_preserved_with_exact_type(tmp_path, input_value, accepted):
    path = make_simulation_protocol(tmp_path, approved_input=2.0, input_value=input_value)
    result = check(path)
    assert result["valid"] is accepted
    if not accepted:
        assert any("known approved value" in error for error in result["errors"])


@pytest.mark.parametrize("change", ["wrong_type", "fixed_tol", "negative_step", "reversed_steps", "large_initial", "zero_tol", "unknown_stiffness", "incorrect_dynamics", "dae", "events", "algebraic_loop", "multirate", "real_time_codegen", "bad_time", "known_time_changed", "no_metric", "unbounded_metric", "metric_units", "metric_order", "unknown_metric", "duplicate_metric"])
def test_solver_classification_time_and_metric_reviews_constrain_execution(tmp_path, change):
    path = make_simulation_protocol(tmp_path)
    def modify(value):
        solver = value["solver"]
        if change == "wrong_type":
            solver["type"] = "fixed-step"
        elif change == "fixed_tol":
            solver["fixed_step"] = 0.1
        elif change == "negative_step":
            solver["min_step"] = -1.0
        elif change == "reversed_steps":
            solver["min_step"] = 0.02
        elif change == "large_initial":
            solver.update(max_step=2.0, initial_step=2.0)
        elif change == "zero_tol":
            solver["rel_tol"] = 0.0
        elif change == "unknown_stiffness":
            solver["classification"]["stiffness"] = "unknown"
        elif change == "incorrect_dynamics":
            solver["classification"]["dynamics"] = "algebraic"
        elif change in {"dae", "events", "algebraic_loop", "multirate", "real_time_codegen"}:
            solver["classification"][change] = True
        elif change == "bad_time":
            value["time"]["stop"] = 0.0
        elif change == "known_time_changed":
            value["time"]["stop"] = 2.0
        elif change == "no_metric":
            value["metrics"] = []
        elif change == "unbounded_metric":
            value["metrics"][0].update(lower=None, upper=None)
        elif change == "metric_units":
            value["metrics"][0]["unit"] = "m"
        elif change == "metric_order":
            value["metrics"][0].update(lower=2.0, upper=1.0)
        elif change == "unknown_metric":
            value["metrics"][0]["output_port"] = 2
        else:
            value["metrics"].append(dict(value["metrics"][0]))
    rewrite(path, modify)
    assert not check(path)["valid"]


@pytest.mark.parametrize("operations", [["matlab.basic_execution"], ["statistics.fitlm"], []])
def test_protocol_cannot_drop_core_operations(tmp_path, operations):
    path = make_simulation_protocol(tmp_path)
    rewrite(path, lambda value: value.update(required_A_operations=operations))
    result = check(path)
    assert not result["valid"] and "required_core_operations" in result["missing_gates"]


def test_explicit_statistics_requirements_are_preserved_but_not_probed_by_reader(tmp_path):
    required = ["matlab.basic_execution", "simulink.library_load", "statistics.fitlm", "statistics.normcdf"]
    path = make_simulation_protocol(tmp_path, required_operations=required)
    result = check(path)
    assert result["valid"] and result["required_A_operations"] == required
    assert not result["environment_checked"] and not result["execution_allowed"]


@pytest.mark.parametrize("input_value,accepted", [(2.0, True), (1.0, False), (2, False)])
def test_known_single_input_scalar_fact_is_not_silently_ignored(tmp_path, input_value, accepted):
    path = make_simulation_protocol(tmp_path, approved_input=2.0, scalar_source_input=True, input_value=input_value)
    result = check(path)
    assert result["valid"] is accepted


def test_known_structured_time_range_and_finite_interval_are_enforced(tmp_path):
    path = make_simulation_protocol(tmp_path, source_time=[0.0, 1.0])
    assert check(path)["valid"]
    rewrite(path, lambda value: value["time"].update(stop=2.0))
    assert not check(path)["valid"]
    rewrite(path, lambda value: value["time"].update(start=-1e308, stop=1e308))
    assert any("finite interval" in error for error in check(path)["errors"])


@pytest.mark.parametrize("solver,start,stop,step,rel_tol", [
    ("ode45", -1.0, 1.0, None, 2.0),
    ("ode15s", -0.3, 0.83, None, 2.0),
    ("ode4", -0.3, 0.83, 0.1, None),
    ("ode4", 0.3, 1.03, 0.1, None),
])
def test_negative_time_and_positive_tolerance_use_public_solver_boundaries(tmp_path, solver, start, stop, step, rel_tol):
    source_time = {"start": start, "stop": stop, "unit": "s"}
    path = make_simulation_protocol(tmp_path, solver=solver, source_time=source_time)
    def modify(value):
        value["time"].update(start=start, stop=stop)
        value["solver"].update(fixed_step=step, rel_tol=rel_tol)
    rewrite(path, modify)
    result = check(path, require_frozen=True)
    assert result["valid"] and result["execution_ready"], result["errors"]
    assert result["run_spec"]["start_time"] == start
    assert result["run_spec"]["stop_time"] == stop


@pytest.mark.parametrize("start,stop,step", [(0.05, 1.0, 0.1), (-0.05, 1.0, 0.1), (-1e308, -9e307, 1e-308)])
def test_fixed_step_start_cannot_be_adjusted_silently_by_the_engine(tmp_path, start, stop, step):
    source_time = {"start": start, "stop": stop, "unit": "s"}
    path = make_simulation_protocol(tmp_path, solver="ode4", source_time=source_time)
    def modify(value):
        value["time"].update(start=start, stop=stop)
        value["solver"]["fixed_step"] = step
    rewrite(path, modify)
    result = check(path)
    assert not result["valid"] and not result["execution_ready"]
    assert any("integer multiple" in error for error in result["errors"])


@pytest.mark.parametrize("minimum,accepted", [(1e-12, True), (0.0, False), (-1e-12, False)])
def test_minimum_step_requires_positive_reviewed_value_before_native_execution(tmp_path, minimum, accepted):
    path = make_simulation_protocol(tmp_path)
    rewrite(path, lambda value: value["solver"].update(min_step=minimum))
    result = check(path)
    assert result["valid"] is accepted
    assert result["execution_ready"] is accepted
    if not accepted:
        assert any("min_step must be a supported finite positive" in error for error in result["errors"])


def test_unknown_parameter_unit_does_not_bypass_current_c_completeness(tmp_path):
    path = make_simulation_protocol(tmp_path)
    model_path = tmp_path / "model.json"
    model = load_document(model_path)
    for variable in model["designs"][0]["models"][0]["body"]["variables"]:
        if "parameter" in variable["roles"]:
            variable["unit"] = None
    write_contract(model_path, model)
    approve_contract(model_path)  # Synthetic invalid candidate; consumers must refuse it.
    parameters_path = tmp_path / "parameters.json"
    parameters = load_document(parameters_path)
    parameters["model"] = file_ref(tmp_path, model_path)
    for parameter in parameters["parameters"]:
        parameter["unit"] = None
    write_contract(parameters_path, parameters)
    mapping_path = tmp_path / "mapping.json"
    mapping = load_document(mapping_path)
    mapping.update(model=file_ref(tmp_path, model_path), parameters=file_ref(tmp_path, parameters_path))
    write_contract(mapping_path, mapping)
    rewrite(path, lambda value: value.update(mapping=file_ref(tmp_path, mapping_path), parameter_set=file_ref(tmp_path, parameters_path)))
    result = check(path)
    assert not result["valid"] and not result["execution_ready"]
    assert set(result["unknown_parameter_units"]) == {"a", "b"}
    assert {"unit:kernel_design.feedback_kernel.a", "unit:kernel_design.feedback_kernel.b"} <= set(result["mapping_validation"]["model_validation"]["missing_gates"])
    assert all(item["unit"] is None for item in load_document(parameters_path)["parameters"])


@pytest.mark.parametrize("field,value", [("schema_version", True), ("seed", {"value": True, "generator": "twister", "reason": "invalid boolean"}), ("inputs", {}), ("outputs", None), ("required_A_operations", ["unimplemented.api"]), ("unapproved_override", 1)])
def test_schema_is_strict_about_types_unknown_fields_and_operation_ids(tmp_path, field, value):
    path = make_simulation_protocol(tmp_path)
    rewrite(path, lambda contract: contract.update({field: value}), freeze=False)
    result = check(path)
    assert not result["valid"] and not result["schema_valid"]


def test_duplicate_keys_nonfinite_and_project_boundary_are_rejected(tmp_path):
    path = tmp_path / "protocol.json"
    path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    assert not check(path)["valid"]
    path.write_text('{"schema_version":NaN}', encoding="utf-8")
    assert not check(path)["valid"]
    assert not validate_simulation_protocol(path, project_root=tmp_path / "elsewhere")["valid"]


def test_recursive_yaml_alias_is_a_controlled_read_only_failure(tmp_path):
    path = tmp_path / "protocol.yaml"
    path.write_text("recursive: &self\n  recursive: *self\n", encoding="utf-8")
    before = path.read_bytes()
    result = check(path)
    assert not result["valid"] and result["errors"]
    assert path.read_bytes() == before


def test_source_selector_cannot_leave_project_root(tmp_path):
    project = tmp_path / "project"
    path = make_simulation_protocol(project)
    outside = tmp_path / "outside.json"
    outside.write_text('{"u":1}', encoding="utf-8")
    rewrite(path, lambda value: value["sources"][0].update(path="../outside.json", sha256=sha256_file(outside)))
    assert not check(path)["valid"]


def test_cli_requires_current_freeze_without_writing(tmp_path):
    path = make_simulation_protocol(tmp_path, status="draft")
    before = {item: item.read_bytes() for item in tmp_path.rglob("*") if item.is_file()}
    command = [sys.executable, str(ROOT / "scripts/validate_simulation_protocol.py"), str(path), "--project-root", str(tmp_path), "--require-frozen"]
    process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert process.returncode == 1
    result = json.loads(process.stdout)
    assert not result["frozen"] and not result["execution_allowed"]
    assert {item: item.read_bytes() for item in tmp_path.rglob("*") if item.is_file()} == before
