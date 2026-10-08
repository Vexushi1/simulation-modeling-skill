"""Protect accepted evidence, transitive stale history and project boundaries."""
import json
import subprocess
import sys

import pytest

from resolve_runtime import resolve_runtime
from runtime_common import ROOT, sha256_file
from test_runtime import make_profile
from validate_project_state import affected_artefacts, validate_project_state


def write_state(directory, *, profile=None, stage="NEW", artefacts=None):
    environment = None if profile is None else {
        "profile_path": profile.relative_to(directory).as_posix(),
        "profile_sha256": sha256_file(profile),
        "receipt_sha256": sha256_file(profile.parent / "receipt.json"),
    }
    state = {"schema_version": 1, "project_id": "state-fixture", "project_root": ".",
             "current_stage": stage, "environment": environment, "artefacts": artefacts or []}
    path = directory / "project-state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


def artifact(path, root, *, identity="route", role="route_decision", status="accepted", depends=None):
    return {"id": identity, "role": role, "path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path), "status": status,
            "depends_on": ["environment"] if depends is None else depends}


def write_route(tmp_path, profile):
    route = resolve_runtime("assure_environment", profile_path=profile)
    path = tmp_path / "route.json"
    path.write_text(json.dumps(route), encoding="utf-8")
    return path


def test_new_state_is_valid_and_validator_never_writes(tmp_path):
    state = write_state(tmp_path)
    before = state.read_bytes()
    assert validate_project_state(state)["valid"]
    assert state.read_bytes() == before
    assert list(tmp_path.iterdir()) == [state]


@pytest.mark.parametrize("stage", ["MODEL_APPROVED", "SIMULATED", "Phase A"])
def test_unimplemented_or_development_states_rejected(tmp_path, stage):
    assert not validate_project_state(write_state(tmp_path, stage=stage))["valid"]


def test_assured_state_requires_current_bound_profile(tmp_path):
    assert not validate_project_state(write_state(tmp_path, stage="ENVIRONMENT_ASSURED"))["valid"]
    profile = make_profile(tmp_path)
    state = write_state(tmp_path, profile=profile, stage="ENVIRONMENT_ASSURED")
    assert validate_project_state(state)["valid"]
    value = json.loads(state.read_text())
    value["environment"]["receipt_sha256"] = "0" * 64
    state.write_text(json.dumps(value), encoding="utf-8")
    result = validate_project_state(state)
    assert not result["valid"] and "environment" in result["stale_artefacts"]


def test_accepted_profile_and_route_bind_the_same_environment(tmp_path):
    profile = make_profile(tmp_path)
    route = write_route(tmp_path, profile)
    items = [artifact(profile, tmp_path, identity="profile", role="environment_profile"),
             artifact(route, tmp_path)]
    state = write_state(tmp_path, profile=profile, stage="ENVIRONMENT_ASSURED", artefacts=items)
    assert validate_project_state(state)["valid"]
    assert not validate_project_state(state, profile_path=tmp_path / "other.json")["valid"]


@pytest.mark.parametrize("mutation", ["business_permission", "different_profile", "deferred", "missing_core", "unknown_operation",
                                     "business_module", "upstream_skill", "missing_gate", "state_mutation",
                                     "implementation_permission", "simulation_permission"])
def test_accepted_route_cannot_claim_unbound_or_business_qualification(tmp_path, mutation):
    profile = make_profile(tmp_path)
    path = write_route(tmp_path, profile)
    route = json.loads(path.read_text())
    if mutation == "business_permission":
        route["business_execution_allowed"] = True
    elif mutation == "implementation_permission":
        route["implementation_execution_allowed"] = True
    elif mutation == "simulation_permission":
        route["simulation_execution_allowed"] = True
    elif mutation == "different_profile":
        route["profile_sha256"] = "0" * 64
    elif mutation == "deferred":
        route["status"] = "deferred"
    elif mutation == "missing_core":
        route["selected_operations"] = []
    elif mutation == "unknown_operation":
        route["selected_operations"].append("model.simulate")
    elif mutation == "business_module":
        route["activated_modules"].append("business_model")
    elif mutation == "upstream_skill":
        route["upstream_skills"].append("simulate")
    elif mutation == "missing_gate":
        route["missing_gates"].append("model_approval")
    else:
        route["state_mutated"] = True
    path.write_text(json.dumps(route), encoding="utf-8")
    state = write_state(tmp_path, profile=profile, artefacts=[artifact(path, tmp_path)])
    result = validate_project_state(state)
    assert not result["valid"] and "route" in result["stale_artefacts"]


def test_accepted_evidence_requires_dependency_and_current_file(tmp_path):
    profile = make_profile(tmp_path)
    path = write_route(tmp_path, profile)
    item = artifact(path, tmp_path, depends=[])
    assert not validate_project_state(write_state(tmp_path, profile=profile, artefacts=[item]))["valid"]
    item["depends_on"] = ["environment"]
    state = write_state(tmp_path, profile=profile, artefacts=[item])
    path.write_text("{}", encoding="utf-8")
    result = validate_project_state(state)
    assert not result["valid"] and "route" in result["stale_artefacts"]


def test_pre_d_environment_route_without_new_false_permissions_remains_valid(tmp_path):
    profile = make_profile(tmp_path)
    path = write_route(tmp_path, profile)
    route = json.loads(path.read_text())
    route.pop("implementation_execution_allowed")
    route.pop("simulation_execution_allowed")
    path.write_text(json.dumps(route), encoding="utf-8")
    state = write_state(tmp_path, profile=profile, artefacts=[artifact(path, tmp_path)])
    assert validate_project_state(state)["valid"]


@pytest.mark.parametrize("status", ["draft", "stale", "accepted"])
def test_all_recorded_paths_stay_inside_project_root(tmp_path, status):
    item = {"id": "unsafe", "role": "route_decision", "path": "../outside.json",
            "sha256": "0" * 64, "status": status, "depends_on": []}
    result = validate_project_state(write_state(tmp_path, artefacts=[item]))
    assert not result["valid"] and any("leaves project root" in error for error in result["errors"])


def test_stale_history_is_preserved_but_accepted_dependents_are_rejected(tmp_path):
    profile = make_profile(tmp_path)
    route = write_route(tmp_path, profile)
    old = artifact(route, tmp_path, identity="old", status="stale")
    child = artifact(route, tmp_path, identity="child", depends=["environment", "old"])
    state = write_state(tmp_path, profile=profile, artefacts=[old, child])
    before = state.read_bytes()
    result = validate_project_state(state)
    assert not result["valid"] and result["stale_artefacts"] == ["child", "old"]
    assert state.read_bytes() == before
    child["status"] = "stale"
    assert validate_project_state(write_state(tmp_path, profile=profile, artefacts=[old, child]))["valid"]


def test_accepted_chain_rejects_draft_ancestors_before_and_after_file_changes(tmp_path):
    profile = make_profile(tmp_path)
    route = write_route(tmp_path, profile)
    parent = artifact(route, tmp_path, identity="parent")
    child = artifact(route, tmp_path, identity="child", depends=["environment", "parent"])
    assert validate_project_state(write_state(tmp_path, profile=profile, artefacts=[parent, child]))["valid"]
    draft = tmp_path / "draft.json"
    draft.write_text("{}", encoding="utf-8")
    parent = artifact(draft, tmp_path, identity="parent", status="draft")
    state = write_state(tmp_path, profile=profile, artefacts=[parent, child])
    for content in ("{}", '{"changed":true}'):
        draft.write_text(content, encoding="utf-8")
        result = validate_project_state(state)
        assert not result["valid"] and "child" in result["stale_artefacts"]
        assert any("unaccepted evidence" in error for error in result["errors"])


@pytest.mark.parametrize("problem", ["unknown", "cycle", "duplicate"])
def test_invalid_dependencies_are_rejected(tmp_path, problem):
    path = tmp_path / "draft.json"
    path.write_text("{}", encoding="utf-8")
    a = artifact(path, tmp_path, identity="a", status="draft", depends=[])
    b = artifact(path, tmp_path, identity="b", status="draft", depends=["a"])
    if problem == "unknown":
        a["depends_on"] = ["missing"]
    elif problem == "cycle":
        a["depends_on"] = ["b"]
    else:
        b["id"] = "a"
    assert not validate_project_state(write_state(tmp_path, artefacts=[a, b]))["valid"]


def test_transitive_stale_propagation():
    items = [{"id": "a", "depends_on": ["environment"]}, {"id": "b", "depends_on": ["a"]},
             {"id": "independent", "depends_on": []}]
    assert affected_artefacts(items, {"environment"}) == {"environment", "a", "b"}


def test_cli_rejects_bad_state_as_json(tmp_path):
    state = write_state(tmp_path, stage="SIMULATED")
    completed = subprocess.run([sys.executable, str(ROOT / "scripts/validate_project_state.py"), str(state)],
                               capture_output=True, text=True)
    assert completed.returncode == 1
    assert json.loads(completed.stdout)["valid"] is False
    assert not completed.stderr
