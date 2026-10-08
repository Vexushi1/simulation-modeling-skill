"""F study gates reject unlawful, leaky and unidentifiable candidate work.

All source and decision records here are explicitly synthetic infrastructure
fixtures. Passing these tests supplies no actual runtime or human approval.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from model_factory import approve_contract, file_ref
from parameter_study_factory import METHODS, make_parameter_study, review_parameter_study
from problem_factory import freeze_contract, read_contract, write_contract
from runtime_common import ROOT, sha256_file
from validate_model_contract import model_identity, validate_model_contract
from validate_parameter_study import semantic_digest, validate_parameter_study


def check(path, **kwargs):
    return validate_parameter_study(path, project_root=path.parent, **kwargs)


def rewrite(path, change, *, review=True):
    value = read_contract(path)
    change(value)
    write_contract(path, value)
    if review:
        review_parameter_study(path)
    return value


def rebind_current_sources(path, *, model_change=None, problem_change=None):
    """Re-review changed synthetic B/C inputs to isolate F semantic negatives."""
    root = path.parent
    problem_path, model_path = root / "problem.json", root / "model.json"
    problem = read_contract(problem_path)
    if problem_change:
        problem_change(problem)
    for source in problem["sources"]:
        source["sha256"] = sha256_file(root / source["path"])
        if source["text"]:
            source["text"]["sha256"] = sha256_file(root / source["text"]["path"])
    problem.update(status="draft", freeze=None)
    write_contract(problem_path, problem)
    freeze_contract(problem_path)
    model = read_contract(model_path)
    if model_change:
        model_change(model)
    for source in model["sources"]:
        source["sha256"] = sha256_file(root / source["path"])
    model.update(problem=file_ref(root, problem_path), status="challenged", approval=None)
    write_contract(model_path, model)
    approve_contract(model_path)
    study = read_contract(path)
    study["model"] = file_ref(root, model_path)
    for source in study["sources"]:
        source["sha256"] = sha256_file(root / source["path"])
    write_contract(path, study)
    review_parameter_study(path)


def snapshot(root):
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_unknown_template_is_legal_read_only_but_cannot_execute(tmp_path):
    path = tmp_path / "parameter-study.yaml"
    path.write_bytes((ROOT / "templates/contracts/parameter_study.yaml").read_bytes())
    before = snapshot(tmp_path)
    result = check(path)
    assert result["schema_valid"] and result["valid"], result["errors"]
    assert not result["study_ready"] and not result["reviewed"] and not result["trial_execution_ready"]
    assert not result["environment_checked"] and not result["execution_allowed"]
    assert result["missing_gates"]
    assert not check(path, require_reviewed=True)["valid"]
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("method", METHODS)
def test_current_reviewed_unknown_baseline_yields_trial_spec_without_runtime_permission(tmp_path, method):
    path = make_parameter_study(tmp_path, method)
    before = snapshot(tmp_path)
    result = check(path, require_reviewed=True)
    assert result["valid"] and result["study_ready"] and result["reviewed"] and result["trial_execution_ready"], result["errors"]
    assert not result["environment_checked"] and not result["execution_allowed"]
    spec = result["native_spec"]
    assert spec["method"] == method
    assert spec["parameter_ids"] == [item["variable_id"] for item in read_contract(path)["parameters"]]
    model = read_contract(tmp_path / "model.json")
    values = [item["parameter"]["value"] for item in model["designs"][0]["models"][0]["body"]["variables"] if item["parameter"]]
    assert values and all(value is None for value in values)
    assert validate_model_contract(tmp_path / "model.json", require_approved=True)["approved"]
    if method == METHODS[2]:
        assert spec["train"] is None and spec["holdout"] is None and spec["sample_time"] is None
        assert spec["objective"]["A"] == [[1.0, 1.0]] and spec["objective"]["b"] == [3.0]
    else:
        assert len(spec["train"]["time"]) == len(spec["holdout"]["time"]) == 20
        assert max(spec["train"]["time"]) < min(spec["holdout"]["time"])
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("method", METHODS)
def test_complete_draft_needs_actual_bound_review(tmp_path, method):
    path = make_parameter_study(tmp_path, method, status="draft")
    result = check(path)
    assert result["valid"] and result["study_ready"] and result["native_spec"]
    assert not result["reviewed"] and not result["trial_execution_ready"]
    assert not check(path, require_reviewed=True)["valid"]


@pytest.mark.parametrize("stage", ["draft", "proposed", "challenged"])
def test_study_review_does_not_replace_current_c_human_approval(tmp_path, stage):
    path = make_parameter_study(tmp_path)
    model_path = tmp_path / "model.json"
    model = read_contract(model_path)
    model.update(status=stage, approval=None)
    write_contract(model_path, model)
    rewrite(path, lambda study: study.update(model=file_ref(tmp_path, model_path)))
    result = check(path)
    assert result["model_validation"]["valid"]
    assert not result["model_validation"]["approved"] and not result["trial_execution_ready"]


def test_removed_b_freeze_blocks_trial_even_if_study_review_is_rebound(tmp_path):
    path = make_parameter_study(tmp_path)
    problem_path, model_path = tmp_path / "problem.json", tmp_path / "model.json"
    problem = read_contract(problem_path)
    problem.update(status="audited", freeze=None)
    write_contract(problem_path, problem)
    model = read_contract(model_path)
    model["problem"] = file_ref(tmp_path, problem_path)
    write_contract(model_path, model)
    approve_contract(model_path)
    rewrite(path, lambda study: study.update(model=file_ref(tmp_path, model_path)))
    assert not check(path)["trial_execution_ready"]


@pytest.mark.parametrize("change", ["missing_record", "missing_decision", "wrong_project", "wrong_digest", "wrong_quote", "reject_action", "duplicate_context"])
def test_review_status_cannot_substitute_for_current_source_bound_decision(tmp_path, change):
    path = make_parameter_study(tmp_path)
    study = read_contract(path)
    record_path = tmp_path / study["review_record"]["path"]
    record = read_contract(record_path)
    if change == "missing_record":
        study["review_record"] = None
    elif change == "missing_decision":
        (tmp_path / record["decision"]["path"]).unlink()
    elif change == "wrong_project":
        record["project_id"] = "other-project"
    elif change == "wrong_digest":
        record["study_semantic_sha256"] = "0" * 64
    elif change == "wrong_quote":
        record["decision"]["quote"] += "unrecorded text"
    else:
        decision = record["decision"]
        quote = decision["quote"].replace("action=review", "action=reject") if change == "reject_action" else decision["quote"] + "\naction=review"
        decision_path = tmp_path / decision["path"]
        decision_path.write_text(quote + "\n", encoding="utf-8")
        decision.update(quote=quote, start=0, end=len(quote), sha256=sha256_file(decision_path))
    write_contract(record_path, record)
    if change != "missing_record":
        study["review_record"] = file_ref(tmp_path, record_path)
    write_contract(path, study)
    result = check(path)
    assert not result["valid"] and not result["reviewed"] and not result["trial_execution_ready"]


def test_review_semantic_digest_excludes_only_stage_and_decision_reference(tmp_path):
    path = make_parameter_study(tmp_path)
    original = read_contract(path)
    digest = semantic_digest(original)
    original.update(status="draft", review_record=None)
    assert semantic_digest(original) == digest
    original["criteria"]["max_holdout_rmse"] *= 2
    assert semantic_digest(original) != digest


@pytest.mark.parametrize("field", ["model", "selection", "method", "budget", "criteria", "warning_policy", "identifiability"])
def test_reviewed_missing_required_study_semantics_still_blocks_trial(tmp_path, field):
    path = make_parameter_study(tmp_path)
    rewrite(path, lambda study: study.update({field: None}))
    result = check(path)
    assert not result["valid"] and not result["study_ready"] and not result["trial_execution_ready"]


@pytest.mark.parametrize("field,value", [("symbol", "not_k"), ("variable_id", "missing"), ("unit", "W"), ("role", "optimized")])
def test_candidate_identity_units_and_provenance_cannot_replace_approved_parameter(tmp_path, field, value):
    path = make_parameter_study(tmp_path)
    rewrite(path, lambda study: study["parameters"][0].update({field: value}))
    assert not check(path)["trial_execution_ready"]


@pytest.mark.parametrize("provenance", ["given", "derived"])
def test_source_given_parameter_cannot_be_recast_as_unknown_tunable_candidate(tmp_path, provenance):
    path = make_parameter_study(tmp_path)
    def change_model(model):
        parameter = next(item["parameter"] for item in model["designs"][0]["models"][0]["body"]["variables"] if item["id"] == "k")
        parameter.update(value=2.0, provenance=provenance, source_ids=["foundation"])
    rebind_current_sources(path, model_change=change_model)
    assert validate_model_contract(tmp_path / "model.json", require_approved=True)["approved"]
    assert not check(path)["trial_execution_ready"]


@pytest.mark.parametrize("change", ["initial_outside", "reversed_bounds", "flat_bounds", "unbound_basis", "wrong_basis", "boolean_initial"])
def test_candidate_bounds_and_initialization_are_source_backed_finite_values(tmp_path, change):
    path = make_parameter_study(tmp_path)
    def mutate(study):
        parameter = study["parameters"][0]
        if change == "initial_outside": parameter["initial"] = 5.0
        elif change == "reversed_bounds": parameter.update(lower=5.0, upper=0.0)
        elif change == "flat_bounds": parameter.update(lower=1.5, upper=1.5)
        elif change == "unbound_basis": parameter["numerical_basis"] = None
        elif change == "wrong_basis": parameter["numerical_basis"]["selector"] = ["parameters", "unknown"]
        else: parameter["initial"] = True
    rewrite(path, mutate)
    if change in {"initial_outside", "reversed_bounds", "flat_bounds"}:
        study = read_contract(path)
        settings_path = tmp_path / "study-settings.json"
        settings = read_contract(settings_path)
        settings["parameters"]["k"].update({key: study["parameters"][0][key] for key in ("initial", "lower", "upper")})
        write_contract(settings_path, settings)
        rebind_current_sources(path)
    assert not check(path)["trial_execution_ready"]


@pytest.mark.parametrize("change", ["overlap", "empty", "outside", "missing_column", "wrong_input_unit", "weight_length", "zero_weight", "wrong_role"])
def test_fit_holdout_source_ranges_units_and_weights_are_closed(tmp_path, change):
    path = make_parameter_study(tmp_path)
    def mutate(study):
        data = study["data"][1]
        if change == "overlap": data.update(start=10, end=30)
        elif change == "empty": data.update(start=20, end=20)
        elif change == "outside": data["end"] = 100
        elif change == "missing_column": data["columns"]["output"] = "missing"
        elif change == "wrong_input_unit": data["units"]["input"] = "W"
        elif change == "weight_length": data["weights"] = [1.0]
        elif change == "zero_weight": data["weights"][0] = 0.0
        else: data["role"] = "train"
    rewrite(path, mutate)
    assert not check(path)["trial_execution_ready"]


@pytest.mark.parametrize("method", METHODS[:2])
@pytest.mark.parametrize("change", ["missing", "nonfinite", "nonuniform", "rank_or_excitation"])
def test_source_current_csv_still_needs_finite_uniform_informative_measurements(tmp_path, method, change):
    path = make_parameter_study(tmp_path, method)
    csv_path = tmp_path / "observations.csv"
    rows = [line.split(",") for line in csv_path.read_text(encoding="utf-8").splitlines()]
    if change == "missing": rows[3][2] = ""
    elif change == "nonfinite": rows[3][2] = "nan"
    elif change == "nonuniform": rows[3][0] = "0.25"
    else:
        for row in rows[1:]:
            row[1] = "0"
            if method == METHODS[0]: row[2] = "0"
    csv_path.write_text("\n".join(",".join(row) for row in rows) + "\n", encoding="utf-8")
    rebind_current_sources(path)
    assert validate_model_contract(tmp_path / "model.json", require_approved=True)["approved"]
    assert not check(path)["trial_execution_ready"]


def test_equal_csv_bytes_under_different_names_cannot_hide_fit_holdout_leakage(tmp_path):
    path = make_parameter_study(tmp_path)
    copy_path = tmp_path / "heldout-copy.csv"
    copy_path.write_bytes((tmp_path / "observations.csv").read_bytes())
    def change_problem(problem):
        problem["sources"].append({"id": "measurements_copy", "kind": "data", **file_ref(tmp_path, copy_path), "text": None})
        use = next(item for item in problem["data_uses"] if item["id"] == "check")
        use.update(source_id="measurements_copy", scope={"kind": "rows", "start": 0, "end": 20}, independence_declared=False)
    def change_model(model):
        model["sources"].append({"id": "measurements_copy", **file_ref(tmp_path, copy_path), "purpose": "Synthetic duplicate-byte leakage negative", "problem_source_id": "measurements_copy"})
    study = read_contract(path)
    study["sources"].append({"id": "measurements_copy", **file_ref(tmp_path, copy_path), "purpose": "Synthetic duplicate-byte leakage negative",
                             "model_source_id": "measurements_copy", "problem_source_id": "measurements_copy"})
    study["data"][1].update(source_id="measurements_copy", start=0, end=20)
    write_contract(path, study)
    rebind_current_sources(path, model_change=change_model, problem_change=change_problem)
    assert validate_model_contract(tmp_path / "model.json", require_approved=True)["approved"]
    assert not check(path)["trial_execution_ready"]


@pytest.mark.parametrize("field,value", [("max_iterations", 0), ("max_evaluations", -1), ("process_timeout", 0), ("simulation_timeout", 240.0), ("max_evaluations", True)])
def test_explicit_finite_budgets_are_required_before_any_trial(tmp_path, field, value):
    path = make_parameter_study(tmp_path)
    rewrite(path, lambda study: study["budget"].update({field: value}))
    assert not check(path)["trial_execution_ready"]


@pytest.mark.parametrize("change", ["wrong_center", "negative_weight", "zero_scale", "wrong_unit", "missing_term", "wrong_constraint", "wrong_relation", "input_data"])
def test_quadratic_objective_and_constraints_must_match_sources_and_approved_math(tmp_path, change):
    path = make_parameter_study(tmp_path, METHODS[2])
    def mutate(study):
        if change == "wrong_center": study["objective"]["terms"][0]["center"] = 3.0
        elif change == "negative_weight": study["objective"]["terms"][0]["weight"] = -1.0
        elif change == "zero_scale": study["objective"]["terms"][0]["scale"] = 0.0
        elif change == "wrong_unit": study["objective"]["terms"][0]["unit"] = "W"
        elif change == "missing_term": study["objective"]["terms"].pop()
        elif change == "wrong_constraint": study["objective"]["constraints"][0]["rhs"] = 4.0
        elif change == "wrong_relation": study["selection"]["relation_id"] = "constraint"
        else: study["sample_time"] = 0.1
    rewrite(path, mutate)
    assert not check(path)["trial_execution_ready"]


@pytest.mark.parametrize("method", METHODS)
def test_reviewed_c_math_mutation_cannot_reuse_old_f_binding(tmp_path, method):
    path = make_parameter_study(tmp_path, method)
    before = check(path, require_reviewed=True)
    assert before["trial_execution_ready"]
    model_path = tmp_path / "model.json"
    model = read_contract(model_path)
    selected = model["designs"][0]["models"][0]
    identity = model_identity(selected)
    selected["body"]["relations"][0]["expression"] += "; source changes"
    assert model_identity(selected) != identity
    write_contract(model_path, model)
    approve_contract(model_path)
    assert validate_model_contract(model_path, require_approved=True)["approved"]
    assert not check(path)["trial_execution_ready"]


@pytest.mark.parametrize("method", METHODS)
def test_study_reviewer_cannot_approve_a_different_mathematical_kernel(tmp_path, method):
    path = make_parameter_study(tmp_path, method)
    rebind_current_sources(path, model_change=lambda model: model["designs"][0]["models"][0]["body"]["relations"][0].update(expression="a different unqualified relation"))
    assert validate_model_contract(tmp_path / "model.json", require_approved=True)["approved"]
    assert not check(path)["trial_execution_ready"]


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("field", ["initial_conditions", "boundary_conditions"])
@pytest.mark.parametrize("status", ["specified", "unknown"])
def test_trial_kernel_cannot_discard_current_approved_conditions(tmp_path, method, field, status):
    path = make_parameter_study(tmp_path, method)
    def change_model(model):
        model["designs"][0]["models"][0]["body"][field].update(
            status=status, value={"approved_condition": 0.25} if status == "specified" else None,
            reason="Explicit synthetic condition retained for unsupported-kernel rejection")
    rebind_current_sources(path, model_change=change_model)
    assert validate_model_contract(tmp_path / "model.json", require_approved=True)["approved"]
    report = check(path)
    assert not report["trial_execution_ready"]
    assert f"C_condition_not_applicable:{field}" in report["missing_gates"]


def test_condition_dependent_study_remains_a_legal_nonexecutable_draft(tmp_path):
    path = make_parameter_study(tmp_path)
    rebind_current_sources(path, model_change=lambda model: model["designs"][0]["models"][0]["body"]["initial_conditions"].update(
        status="unknown", value=None, reason="An unresolved initial condition cannot be silently discarded"))
    rewrite(path, lambda study: study.update(status="draft", review_record=None), review=False)
    report = check(path)
    assert report["schema_valid"] and report["valid"] and not report["study_ready"]
    assert not report["reviewed"] and not report["trial_execution_ready"]


@pytest.mark.parametrize("name", ["observations.csv", "study-settings.json", "human-model-decision.txt", "locked-model-spec.json", "study-review-decision.txt"])
def test_changed_or_missing_bound_sources_block_without_rewriting_history(tmp_path, name):
    path = make_parameter_study(tmp_path)
    source = tmp_path / name
    source.write_bytes(source.read_bytes() + b"\nchanged")
    before = snapshot(tmp_path)
    result = check(path)
    assert not result["trial_execution_ready"]
    assert snapshot(tmp_path) == before


def test_arx_weights_are_not_silently_used_by_unweighted_arx_method(tmp_path):
    path = make_parameter_study(tmp_path, METHODS[0])
    rewrite(path, lambda study: study["data"][0]["weights"].__setitem__(0, 2.0))
    assert not check(path)["trial_execution_ready"]


def test_exact_zero_fit_threshold_is_not_reinterpreted_as_missing(tmp_path):
    path = make_parameter_study(tmp_path)
    rewrite(path, lambda study: study["criteria"].update(max_train_rmse=0.0, max_holdout_rmse=0.0))
    assert check(path, require_reviewed=True)["trial_execution_ready"]


@pytest.mark.parametrize("method", METHODS)
def test_repeated_text_validation_preserves_required_optional_statistics_operations(tmp_path, method):
    path = make_parameter_study(tmp_path, method)
    requested = ["statistics.fitlm", "statistics.lhsdesign", "statistics.normcdf"]
    rewrite(path, lambda study: study["required_A_operations"].extend(requested))
    before = snapshot(tmp_path)
    report = check(path, require_reviewed=True)
    assert report["trial_execution_ready"]
    assert set(requested) <= set(report["required_A_operations"])
    assert not report["execution_allowed"] and not report["environment_checked"]
    assert snapshot(tmp_path) == before


def test_cli_public_required_review_check_emits_json_and_preserves_files(tmp_path):
    path = make_parameter_study(tmp_path)
    before = snapshot(tmp_path)
    completed = subprocess.run([sys.executable, str(ROOT / "scripts/validate_parameter_study.py"), str(path),
                                "--project-root", str(tmp_path), "--require-reviewed"], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["valid"] and result["reviewed"] and result["trial_execution_ready"]
    assert snapshot(tmp_path) == before
