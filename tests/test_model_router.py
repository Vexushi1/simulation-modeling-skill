"""Mathematical-design routes inspect current contracts without execution."""
import json
import subprocess
import sys

import pytest

from model_factory import make_model_contract
from problem_factory import make_contract
from resolve_runtime import resolve_runtime
from runtime_common import ROOT, contained_path, load_contract, load_document, sha256_file
from test_model_state import write_model_state
from test_problem_state import write_problem_state
from test_runtime import make_profile


def assert_design_only(route):
    assert route["phase"] == "C"
    assert route["execution_scope"] == "model_design"
    assert route["execution_allowed"] is False and route["business_execution_allowed"] is False
    assert route["activated_modules"] == ["model_design"]
    assert route["selected_operations"] == []
    assert not route["activated_packs"] and not route["upstream_skills"]
    assert route["state_mutated"] is False


def test_frozen_problem_opens_draft_design_without_a_profile_or_model(tmp_path):
    problem = make_contract(tmp_path, status="frozen")
    route = resolve_runtime("model_design", problem_path=problem)
    assert route["status"] == "allowed"
    assert route["problem_contract_sha256"] == sha256_file(problem)
    assert route["model_contract_sha256"] is None
    assert "model_contract_supplied" in route["missing_gates"]
    assert "human_model_approval_current" in route["missing_gates"]
    assert_design_only(route)
    state = write_problem_state(tmp_path, problem=problem, stage="PROBLEM_FROZEN")
    assert resolve_runtime("model_design", state_path=state)["status"] == "allowed"


@pytest.mark.parametrize("status", [None, "draft", "audited"])
def test_model_design_requires_actual_current_frozen_problem(tmp_path, status):
    problem = make_contract(tmp_path, status=status) if status else None
    route = resolve_runtime("model_design", problem_path=problem)
    assert route["status"] == "blocked"
    assert "problem_contract_frozen" in route["missing_gates"]
    assert route["fallback"]["action"] == "review_problem_sources_and_contract"
    assert_design_only(route)


@pytest.mark.parametrize("status", ["draft", "proposed", "challenged", "approved"])
def test_model_inspection_never_approves_or_writes_files(tmp_path, status):
    model = make_model_contract(tmp_path, status=status)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    route = resolve_runtime("model_design", model_path=model)
    assert route["status"] == "inspected", route["errors"]
    assert route["model_contract_sha256"] == sha256_file(model)
    assert route["model_validation"]["approved"] is (status == "approved")
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before
    assert_design_only(route)


def test_blocked_challenge_remains_visible_and_never_becomes_approval(tmp_path):
    model = make_model_contract(tmp_path, status="challenged", blocked_challenge=True)
    route = resolve_runtime("model_design", model_path=model)
    assert route["status"] == "inspected", route["errors"]
    assert route["model_validation"]["challenge_complete"] is True
    assert route["model_validation"]["ready_for_approval"] is False
    assert route["model_validation"]["approved"] is False
    assert route["missing_gates"]
    assert_design_only(route)


def test_changed_sources_and_invalid_model_offer_design_review_fallback(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{}", encoding="utf-8")
    route = resolve_runtime("model_design", model_path=broken)
    assert route["status"] == "blocked"
    assert route["fallback"]["action"] == "review_model_sources_and_design"
    assert_design_only(route)
    model = make_model_contract(tmp_path, status="approved")
    brief = contained_path(tmp_path, load_document(model)["brief"]["path"])
    brief.write_bytes(brief.read_bytes() + b"\nchanged brief\n")
    route = resolve_runtime("model_design", model_path=model)
    assert route["status"] == "blocked"
    assert route["model_validation"]["changed_sources"]
    assert route["fallback"]["action"] == "review_model_sources_and_design"
    assert_design_only(route)


def test_model_design_survives_environment_expiry_without_requalifying_runtime(tmp_path):
    model = make_model_contract(tmp_path, status="approved")
    profile = make_profile(tmp_path / "runtime", age_hours=25)
    state = write_model_state(tmp_path, model, stage="MODEL_APPROVED", profile=profile)
    route = resolve_runtime("model_design", state_path=state, profile_path=profile)
    assert route["status"] == "inspected", route["errors"]
    assert route["state_validation"]["scope"] == "model"
    assert route["state_validation"]["environment_checked"] is False
    assert route["model_validation"]["approved"] is True
    assert_design_only(route)
    assert resolve_runtime("assure_environment", state_path=state, profile_path=profile)["status"] == "blocked"


@pytest.mark.parametrize("argument", ["problem", "model", "approval"])
def test_route_arguments_cannot_override_current_project_bindings(tmp_path, argument):
    model = make_model_contract(tmp_path, status="approved")
    state = write_model_state(tmp_path, model, stage="MODEL_APPROVED")
    value = load_document(model)
    original = model if argument == "model" else contained_path(tmp_path, value[argument]["path"])
    copied = tmp_path / f"copied-{argument}.json"
    copied.write_bytes(original.read_bytes())
    route = resolve_runtime("model_design", state_path=state, **{f"{argument}_path": copied})
    assert route["status"] == "blocked"
    assert f"{argument}_state_binding_matches" in route["missing_gates"]
    assert_design_only(route)


def test_project_identity_cannot_be_replaced_by_model_arguments(tmp_path):
    model = make_model_contract(tmp_path, status="proposed")
    state = write_problem_state(tmp_path, project_id="different-project")
    route = resolve_runtime("model_design", state_path=state, model_path=model)
    assert route["status"] == "blocked"
    assert "model_project_id_matches" in route["missing_gates"]
    assert_design_only(route)


def test_separate_approval_cannot_replace_a_missing_model(tmp_path):
    model = make_model_contract(tmp_path, status="approved")
    approval = contained_path(tmp_path, load_document(model)["approval"]["path"])
    problem = contained_path(tmp_path, load_document(model)["problem"]["path"])
    route = resolve_runtime("model_design", problem_path=problem, approval_path=approval)
    assert route["status"] == "blocked"
    assert "model_contract_supplied" in route["missing_gates"]
    assert_design_only(route)


@pytest.mark.parametrize("intent", [key for key in load_contract("core/capability_taxonomy.yaml")["capabilities"]
                                   if key not in load_contract("core/workflow_router.yaml")["intents"]])
def test_even_current_human_approval_never_activates_deferred_capabilities(tmp_path, intent):
    model = make_model_contract(tmp_path, status="approved")
    state = write_model_state(tmp_path, model, stage="MODEL_APPROVED")
    route = resolve_runtime(intent, state_path=state)
    assert route["status"] == "deferred", route["errors"]
    assert route["execution_allowed"] is False and route["business_execution_allowed"] is False
    assert not route["activated_modules"] and not route["activated_resources"]
    assert not route["selected_operations"] and not route["upstream_skills"]
    assert "phase_b_exit_reviewed" not in route["missing_gates"]
    assert f"{intent}_implemented" in route["missing_gates"]
    if load_contract("core/capability_taxonomy.yaml")["capabilities"][intent]["phase"] == "D":
        assert "model_design_approved" not in route["missing_gates"]


def test_challenged_design_does_not_satisfy_future_human_approval_gate(tmp_path):
    model = make_model_contract(tmp_path, status="challenged")
    state = write_model_state(tmp_path, model, stage="MODEL_CHALLENGED")
    route = resolve_runtime("simulink_build", state_path=state)
    assert route["status"] == "blocked"
    assert "model_design_approved" in route["missing_gates"]
    assert not route["execution_allowed"]


def test_model_cli_inspection_is_read_only_and_needs_no_matlab(tmp_path):
    model = make_model_contract(tmp_path, status="proposed")
    before = model.read_bytes()
    completed = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/resolve_runtime.py"),
                                "--intent", "model_design", "--model", str(model)],
                               capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout
    route = json.loads(completed.stdout)
    assert route["status"] == "inspected"
    assert_design_only(route)
    assert model.read_bytes() == before
