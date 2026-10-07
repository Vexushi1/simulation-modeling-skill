"""Behavioral routing tests using complete simulated runtime-evidence chains."""
import json
import subprocess
import sys

import pytest

from resolve_runtime import resolve_runtime
from runtime_common import ROOT, load_contract, sha256_file
from test_runtime import make_profile


CORE = ["matlab.basic_execution", "simulink.library_load"]


def write_state(tmp_path, *, profile=None, stage="NEW", artefacts=None):
    environment = None
    if profile is not None:
        environment = {
            "profile_path": profile.relative_to(tmp_path).as_posix(),
            "profile_sha256": sha256_file(profile),
            "receipt_sha256": sha256_file(profile.parent / "receipt.json"),
        }
    state = {"schema_version": 1, "project_id": "router-fixture", "project_root": ".",
             "current_stage": stage, "environment": environment, "artefacts": artefacts or []}
    path = tmp_path / "project-state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


def assert_no_business_permission(route):
    assert route["business_execution_allowed"] is False
    assert route["activated_packs"] == []
    assert route["upstream_skills"] == []
    assert route["state_mutated"] is False


def test_inspect_needs_no_profile_and_does_not_select_operations(tmp_path):
    state = write_state(tmp_path)
    before = state.read_bytes()
    route = resolve_runtime("inspect", state_path=state)
    assert route["status"] == "inspected"
    assert route["execution_allowed"] is False
    assert route["execution_scope"] == "none"
    assert route["activated_modules"] == ["environment_assurance"]
    assert all((ROOT / path).is_file() for path in route["activated_resources"])
    assert route["selected_operations"] == []
    assert route["profile_sha256"] is None
    assert state.read_bytes() == before
    assert list(tmp_path.iterdir()) == [state]
    assert_no_business_permission(route)


def test_environment_route_selects_only_core_without_loading_statistics(tmp_path):
    profile = make_profile(tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    route = resolve_runtime("assure_environment", profile_path=profile)
    assert route["status"] == "allowed"
    assert route["execution_allowed"] is True
    assert route["execution_scope"] == "environment_assurance"
    assert route["selected_operations"] == CORE
    assert route["activated_modules"] == ["environment_assurance"]
    assert route["profile_sha256"] == sha256_file(profile)
    assert route["receipt_sha256"] == sha256_file(profile.parent / "receipt.json")
    assert route["missing_gates"] == []
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before
    assert_no_business_permission(route)


def test_optional_failure_does_not_block_core_but_blocks_explicit_request(tmp_path):
    profile = make_profile(tmp_path, include_statistics=True,
                           failing_operations=("statistics.fitlm",))
    core_route = resolve_runtime("assure_environment", profile_path=profile)
    assert core_route["status"] == "allowed"
    assert core_route["selected_operations"] == CORE
    route = resolve_runtime("assure_environment", profile_path=profile,
                            required_operations=["statistics.fitlm"])
    assert route["status"] == "blocked"
    assert route["execution_allowed"] is False
    assert route["activated_modules"] == []
    assert route["selected_operations"] == CORE + ["statistics.fitlm"]
    assert any("statistics.fitlm" in error for error in route["errors"])
    assert route["fallback"]["action"] == "repair_or_review_optional_requirement"
    assert_no_business_permission(route)


def test_explicit_optional_selection_keeps_core_and_deduplicates(tmp_path):
    profile = make_profile(tmp_path, include_statistics=True)
    route = resolve_runtime("assure_environment", profile_path=profile,
                            required_operations=["statistics.normcdf", CORE[0], "statistics.normcdf"])
    assert route["status"] == "allowed"
    assert route["selected_operations"] == CORE + ["statistics.normcdf"]
    assert "statistics.fitlm" not in route["selected_operations"]
    assert_no_business_permission(route)


@pytest.mark.parametrize("intent,phase", [(key, value["phase"]) for key, value in
                         load_contract("core/capability_taxonomy.yaml")["capabilities"].items()
                         if key not in load_contract("core/workflow_router.yaml")["intents"]])
def test_all_future_intents_stay_deferred_without_activating_resources(intent, phase):
    route = resolve_runtime(intent)
    assert route["status"] == "deferred"
    assert route["phase"] == phase
    assert route["execution_allowed"] is False
    assert route["activated_modules"] == []
    assert route["activated_resources"] == []
    assert route["selected_operations"] == []
    assert f"{intent}_implemented" in route["missing_gates"]
    assert "phase_b_exit_reviewed" not in route["required_gates"]
    assert "phase_b_exit_reviewed" not in route["missing_gates"]
    assert f"Phase {phase}" in route["next_step"]
    assert_no_business_permission(route)


def test_environment_state_does_not_authorize_business_execution(tmp_path):
    profile = make_profile(tmp_path)
    state = write_state(tmp_path, profile=profile, stage="ENVIRONMENT_ASSURED")
    before = state.read_bytes()
    route = resolve_runtime("problem_audit", profile_path=profile, state_path=state)
    assert route["status"] == "allowed"
    assert "problem_contract_frozen" in route["missing_gates"]
    assert route["execution_allowed"] is False
    assert state.read_bytes() == before
    assert_no_business_permission(route)


@pytest.mark.parametrize("intent", ["inspect", "assure_environment", "simulation_execution"])
def test_forged_downstream_project_state_blocks_every_known_intent(tmp_path, intent):
    state = write_state(tmp_path, stage="MODEL_APPROVED")
    route = resolve_runtime(intent, state_path=state)
    assert route["status"] == "blocked"
    assert "project_state_valid" in route["missing_gates"]
    assert route["execution_allowed"] is False
    assert route["activated_modules"] == []
    assert_no_business_permission(route)


def test_unknown_intent_and_operations_return_invalid():
    assert resolve_runtime("invented_intent")["status"] == "invalid"
    assert resolve_runtime({"intent": "inspect"})["status"] == "invalid"
    assert resolve_runtime("assure_environment", required_operations=["invented.operation"])["status"] == "invalid"
    assert resolve_runtime("inspect", required_operations="statistics.fitlm")["status"] == "invalid"
    assert resolve_runtime("inspect", required_operations={"statistics.fitlm": True})["status"] == "invalid"
    assert resolve_runtime("inspect", required_operations=[None])["status"] == "invalid"


def test_missing_profile_and_core_failure_are_blocked(tmp_path):
    assert resolve_runtime("assure_environment")["status"] == "blocked"
    missing = resolve_runtime("assure_environment", profile_path=tmp_path / "missing.json")
    assert missing["status"] == "blocked"
    profile = make_profile(tmp_path, failing_operations=(CORE[1],))
    failed = resolve_runtime("assure_environment", profile_path=profile)
    assert failed["status"] == "blocked"
    assert any(CORE[1] in error for error in failed["errors"])
    assert failed["fallback"]["action"] == "reprobe_current_environment"


def test_stale_and_wrong_runtime_profiles_are_blocked(tmp_path):
    stale = make_profile(tmp_path / "stale", age_hours=25)
    assert resolve_runtime("assure_environment", profile_path=stale)["status"] == "blocked"
    current = make_profile(tmp_path / "current")
    route = resolve_runtime("assure_environment", profile_path=current,
                            expected_root=tmp_path / "different-matlab-root")
    assert route["status"] == "blocked"
    assert route["execution_allowed"] is False


def test_mutated_raw_evidence_and_stale_state_binding_block_execution(tmp_path):
    profile = make_profile(tmp_path)
    state = write_state(tmp_path, profile=profile, stage="ENVIRONMENT_ASSURED")
    raw = profile.parent / "raw-probe.json"
    raw.write_bytes(raw.read_bytes() + b"\n")
    route = resolve_runtime("assure_environment", profile_path=profile, state_path=state)
    assert route["status"] == "blocked"
    assert "project_state_valid" in route["missing_gates"]
    assert route["execution_allowed"] is False


def test_cli_inspect_and_invalid_intent_emit_json():
    inspect = subprocess.run([sys.executable, str(ROOT / "scripts/resolve_runtime.py"),
                              "--intent", "inspect"], capture_output=True, text=True, check=False)
    assert inspect.returncode == 0
    assert json.loads(inspect.stdout)["execution_allowed"] is False
    invalid = subprocess.run([sys.executable, str(ROOT / "scripts/resolve_runtime.py"),
                              "--intent", "nonexistent"], capture_output=True, text=True, check=False)
    assert invalid.returncode == 1
    assert json.loads(invalid.stdout)["status"] == "invalid"
