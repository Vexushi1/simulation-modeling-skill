"""Problem state gates and stale evidence remain independent of environment TTL."""
import json
import subprocess
import sys

import pytest

from problem_factory import make_contract, read_contract, write_contract
from runtime_common import ROOT, sha256_file
from test_runtime import make_profile
from validate_project_state import validate_project_state


def write_problem_state(root, *, problem=None, profile=None, stage="NEW", artefacts=None,
                        project_id=None):
    root.mkdir(parents=True, exist_ok=True)
    project_id = project_id or (read_contract(problem)["project_id"] if problem else "synthetic-tank")
    value = {"schema_version": 1, "project_id": project_id, "project_root": ".",
             "current_stage": stage, "environment": None, "artefacts": artefacts or []}
    if profile:
        value["environment"] = {"profile_path": profile.relative_to(root).as_posix(),
                                "profile_sha256": sha256_file(profile),
                                "receipt_sha256": sha256_file(profile.parent / "receipt.json")}
    if problem:
        value["problem"] = {"path": problem.relative_to(root).as_posix(), "sha256": sha256_file(problem)}
    path = root / "project-state.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def problem_artefact(path, root, *, identity="contract", status="accepted", depends=None):
    return {"id": identity, "role": "problem_contract", "path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path), "status": status,
            "depends_on": ["problem"] if depends is None else depends}


@pytest.mark.parametrize("stage,status", [("PROBLEM_AUDITED", "audited"), ("PROBLEM_FROZEN", "frozen")])
def test_problem_stages_and_accepted_contract_need_no_environment(tmp_path, stage, status):
    contract = make_contract(tmp_path, status=status)
    state = write_problem_state(tmp_path, problem=contract, stage=stage,
                                artefacts=[problem_artefact(contract, tmp_path)])
    before = state.read_bytes()
    for scope in ("all", "problem"):
        result = validate_project_state(state, scope=scope)
        assert result["valid"] and result["scope"] == scope
        assert result["environment_checked"] is False
        assert result["problem_contract_sha256"] == sha256_file(contract)
    assert state.read_bytes() == before


def test_scope_problem_does_not_masquerade_as_whole_state_validation(tmp_path):
    profile = make_profile(tmp_path / "runtime", age_hours=25)
    contract = make_contract(tmp_path, status="frozen")
    state = write_problem_state(tmp_path, problem=contract, profile=profile, stage="PROBLEM_FROZEN",
                                artefacts=[problem_artefact(contract, tmp_path)])
    full = validate_project_state(state)
    assert full["scope"] == "all" and full["environment_checked"] is True
    assert full["valid"] is False
    assert "environment" in full["stale_artefacts"] and "problem" not in full["stale_artefacts"]
    partial = validate_project_state(state, scope="problem")
    assert partial["valid"] is True and partial["scope"] == "problem"
    assert partial["environment_checked"] is False
    assert partial["stale_artefacts"] == []


@pytest.mark.parametrize("stage", ["PROBLEM_AUDITED", "PROBLEM_FROZEN"])
def test_hand_written_problem_stage_without_binding_is_invalid(tmp_path, stage):
    state = write_problem_state(tmp_path, stage=stage)
    assert not validate_project_state(state, scope="problem")["valid"]


def test_frozen_stage_requires_actual_current_review_not_only_status_text(tmp_path):
    contract = make_contract(tmp_path)
    value = read_contract(contract)
    value["status"] = "frozen"
    write_contract(contract, value)
    state = write_problem_state(tmp_path, problem=contract, stage="PROBLEM_FROZEN")
    result = validate_project_state(state, scope="problem")
    assert not result["valid"] and "problem" in result["stale_artefacts"]
    assert read_contract(contract)["freeze"] is None


def test_complete_draft_cannot_claim_audited_stage_or_accepted_contract(tmp_path):
    contract = make_contract(tmp_path, status="draft")
    state = write_problem_state(tmp_path, problem=contract, stage="PROBLEM_AUDITED")
    assert not validate_project_state(state, scope="problem")["valid"]
    state = write_problem_state(tmp_path, problem=contract,
                                artefacts=[problem_artefact(contract, tmp_path)])
    result = validate_project_state(state, scope="problem")
    assert not result["valid"] and "contract" in result["stale_artefacts"]


@pytest.mark.parametrize("dependency_kind", ["direct", "indirect"])
def test_problem_acceptance_rejects_environment_dependency_even_in_partial_scope(tmp_path, dependency_kind):
    profile = make_profile(tmp_path / "runtime")
    contract = make_contract(tmp_path, status="audited")
    artefacts = []
    environment_dependency = "environment"
    if dependency_kind == "indirect":
        environment_dependency = "runtime-source"
        artefacts.append({"id": environment_dependency, "role": "environment_profile",
                          "path": profile.relative_to(tmp_path).as_posix(), "sha256": sha256_file(profile),
                          "status": "accepted", "depends_on": ["environment"]})
    item = problem_artefact(contract, tmp_path, depends=["problem", environment_dependency])
    artefacts.append(item)
    state = write_problem_state(tmp_path, problem=contract, profile=profile,
                                stage="PROBLEM_AUDITED", artefacts=artefacts)
    for scope in ("all", "problem"):
        result = validate_project_state(state, scope=scope)
        assert not result["valid"]
        assert any("cannot depend on environment" in error for error in result["errors"])


def test_partial_scope_still_checks_global_path_containment(tmp_path):
    contract = make_contract(tmp_path, status="audited")
    outside = {"id": "unrelated", "role": "environment_profile", "path": "../outside.json",
               "sha256": "0" * 64, "status": "draft", "depends_on": []}
    state = write_problem_state(tmp_path, problem=contract, stage="PROBLEM_AUDITED", artefacts=[outside])
    result = validate_project_state(state, scope="problem")
    assert not result["valid"] and any("leaves project root" in error for error in result["errors"])


def test_project_id_and_contract_sha_are_bound(tmp_path):
    contract = make_contract(tmp_path, status="audited")
    state = write_problem_state(tmp_path, problem=contract, stage="PROBLEM_AUDITED",
                                project_id="different-project")
    assert not validate_project_state(state, scope="problem")["valid"]
    state = write_problem_state(tmp_path, problem=contract, stage="PROBLEM_AUDITED")
    value = json.loads(state.read_text(encoding="utf-8"))
    value["problem"]["sha256"] = "0" * 64
    state.write_text(json.dumps(value), encoding="utf-8")
    result = validate_project_state(state, scope="problem")
    assert not result["valid"] and "problem" in result["stale_artefacts"]


def test_source_change_invalidates_problem_and_transitive_accepted_evidence(tmp_path):
    contract = make_contract(tmp_path, status="frozen")
    parent = problem_artefact(contract, tmp_path)
    child = problem_artefact(contract, tmp_path, identity="dependent", depends=["problem", "contract"])
    state = write_problem_state(tmp_path, problem=contract, stage="PROBLEM_FROZEN", artefacts=[parent, child])
    assert validate_project_state(state, scope="problem")["valid"]
    source = tmp_path / read_contract(contract)["sources"][0]["path"]
    source.write_bytes(source.read_bytes() + b"\nchanged source\n")
    before = state.read_bytes()
    result = validate_project_state(state, scope="problem")
    assert not result["valid"]
    assert {"problem", "contract", "dependent"} <= set(result["stale_artefacts"])
    assert state.read_bytes() == before


def test_problem_artefact_requires_exact_binding_and_dependency(tmp_path):
    contract = make_contract(tmp_path, status="audited")
    item = problem_artefact(contract, tmp_path, depends=[])
    state = write_problem_state(tmp_path, problem=contract, stage="PROBLEM_AUDITED", artefacts=[item])
    assert not validate_project_state(state, scope="problem")["valid"]
    copy = tmp_path / "copied.json"
    copy.write_bytes(contract.read_bytes())
    item = problem_artefact(copy, tmp_path)
    state = write_problem_state(tmp_path, problem=contract, stage="PROBLEM_AUDITED", artefacts=[item])
    assert not validate_project_state(state, scope="problem")["valid"]


def test_problem_scope_rejects_path_escape_and_dependency_cycles(tmp_path):
    contract = make_contract(tmp_path, status="audited")
    item = problem_artefact(contract, tmp_path, depends=["problem", "contract"])
    state = write_problem_state(tmp_path, problem=contract, artefacts=[item])
    assert not validate_project_state(state, scope="problem")["valid"]
    value = json.loads(state.read_text(encoding="utf-8"))
    value["artefacts"] = []
    value["problem"]["path"] = "../outside.json"
    state.write_text(json.dumps(value), encoding="utf-8")
    result = validate_project_state(state, scope="problem")
    assert not result["valid"] and any("leaves project root" in error for error in result["errors"])


def test_bad_scope_and_problem_cli_result_are_explicit(tmp_path):
    state = write_problem_state(tmp_path)
    assert not validate_project_state(state, scope="invented")["valid"]
    completed = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/validate_project_state.py"),
                                str(state), "--scope", "problem"], capture_output=True, text=True)
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["scope"] == "problem"
