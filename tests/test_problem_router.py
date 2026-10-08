"""Phase B routes consume real synthetic source contracts, without MATLAB."""
import json
import subprocess
import sys

import pytest

from problem_factory import make_contract, read_contract, write_contract
from resolve_runtime import resolve_runtime
from runtime_common import ROOT, load_contract, sha256_file
from test_problem_state import write_problem_state
from test_runtime import make_profile


def assert_text_only(route):
    assert route["execution_allowed"] is False
    assert route["business_execution_allowed"] is False
    assert route["execution_scope"] == "problem_audit"
    assert route["selected_operations"] == []
    assert route["activated_modules"] == ["problem_audit"]
    assert not route["activated_packs"] and not route["upstream_skills"]
    assert route["state_mutated"] is False


def test_new_problem_route_opens_draft_work_without_environment():
    route = resolve_runtime("problem_audit")
    assert route["status"] == "allowed"
    assert route["phase"] == "B"
    assert route["problem_contract_sha256"] is None
    assert "problem_contract_frozen" in route["missing_gates"]
    assert_text_only(route)


@pytest.mark.parametrize("status", ["draft", "audited", "frozen"])
def test_contract_inspection_does_not_freeze_or_write_state(tmp_path, status):
    contract = make_contract(tmp_path, status=status)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    route = resolve_runtime("problem_audit", problem_path=contract)
    assert route["status"] == "inspected"
    assert route["problem_contract_sha256"] == sha256_file(contract)
    assert route["problem_validation"]["frozen"] is (status == "frozen")
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before
    assert_text_only(route)


def test_open_critical_ambiguity_stays_unfrozen_without_being_fabricated(tmp_path):
    contract = make_contract(tmp_path, critical_ambiguity=True)
    route = resolve_runtime("problem_audit", problem_path=contract)
    assert route["status"] == "inspected"
    assert route["problem_validation"]["frozen"] is False
    assert route["problem_validation"]["freeze_ready"] is False
    assert route["missing_gates"]
    assert read_contract(contract)["ambiguities"][0]["status"] == "unresolved"
    assert_text_only(route)


def test_bad_contract_and_changed_source_offer_text_review_fallback(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{}", encoding="utf-8")
    invalid = resolve_runtime("problem_audit", problem_path=broken)
    assert invalid["status"] == "blocked"
    assert invalid["fallback"]["action"] == "review_problem_sources_and_contract"
    assert_text_only(invalid)
    contract = make_contract(tmp_path, status="frozen")
    source = tmp_path / read_contract(contract)["sources"][0]["path"]
    source.write_bytes(source.read_bytes() + b"changed")
    changed = resolve_runtime("problem_audit", problem_path=contract)
    assert changed["status"] == "blocked"
    assert changed["problem_validation"]["changed_sources"]
    assert changed["fallback"]["action"] == "review_problem_sources_and_contract"
    assert_text_only(changed)


def test_problem_route_survives_unrelated_environment_expiry(tmp_path):
    profile = make_profile(tmp_path / "runtime", age_hours=25)
    contract = make_contract(tmp_path, status="frozen")
    state = write_problem_state(tmp_path, problem=contract, profile=profile, stage="PROBLEM_FROZEN")
    route = resolve_runtime("problem_audit", state_path=state)
    assert route["status"] == "inspected"
    assert route["state_validation"]["scope"] == "problem"
    assert route["state_validation"]["environment_checked"] is False
    assert route["problem_validation"]["frozen"] is True
    assert_text_only(route)
    assert resolve_runtime("assure_environment", state_path=state, profile_path=profile)["status"] == "blocked"


def test_state_problem_and_project_identity_cannot_be_replaced_by_arguments(tmp_path):
    contract = make_contract(tmp_path, status="audited")
    state = write_problem_state(tmp_path, problem=contract, stage="PROBLEM_AUDITED")
    other = tmp_path / "other.json"
    other.write_bytes(contract.read_bytes())
    mismatch = resolve_runtime("problem_audit", state_path=state, problem_path=other)
    assert mismatch["status"] == "blocked"
    assert "problem_state_binding_matches" in mismatch["missing_gates"]
    new_state = write_problem_state(tmp_path, project_id="different-project")
    mismatch = resolve_runtime("problem_audit", state_path=new_state, problem_path=contract)
    assert mismatch["status"] == "blocked"
    assert "problem_project_id_matches" in mismatch["missing_gates"]


@pytest.mark.parametrize("intent", [key for key in load_contract("core/capability_taxonomy.yaml")["capabilities"]
                                   if key not in load_contract("core/workflow_router.yaml")["intents"]])
def test_even_frozen_problem_never_activates_future_capabilities(tmp_path, intent):
    contract = make_contract(tmp_path, status="frozen")
    state = write_problem_state(tmp_path, problem=contract, stage="PROBLEM_FROZEN")
    route = resolve_runtime(intent, state_path=state)
    assert route["status"] == "deferred"
    assert route["execution_allowed"] is False and route["business_execution_allowed"] is False
    assert not route["activated_modules"] and not route["activated_resources"]
    assert not route["selected_operations"] and not route["upstream_skills"]
    assert f"{intent}_implemented" in route["missing_gates"]


def test_problem_cli_needs_no_matlab_profile(tmp_path):
    contract = make_contract(tmp_path)
    completed = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/resolve_runtime.py"),
                                "--intent", "problem_audit", "--problem", str(contract)],
                               capture_output=True, text=True, check=False)
    assert completed.returncode == 0
    route = json.loads(completed.stdout)
    assert route["status"] == "inspected"
    assert_text_only(route)
