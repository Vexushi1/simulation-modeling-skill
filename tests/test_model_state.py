"""Current mathematical proposals and human decisions bind C project states."""
import json
import subprocess
import sys

import pytest

from model_factory import make_model_contract
from runtime_common import ROOT, contained_path, load_document, sha256_file
from test_runtime import make_profile
from validate_project_state import validate_project_state


def write_model_state(root, model, *, stage="NEW", profile=None, artefacts=None,
                      project_id=None, bind_approval=True):
    value = load_document(model)
    state = {"schema_version": 1, "project_id": project_id or value["project_id"],
             "project_root": ".", "current_stage": stage, "environment": None,
             "problem": value["problem"],
             "model": {"path": model.relative_to(root).as_posix(), "sha256": sha256_file(model)},
             "artefacts": artefacts or []}
    if value["approval"] and bind_approval:
        state["approval"] = value["approval"]
    if profile:
        state["environment"] = {"profile_path": profile.relative_to(root).as_posix(),
                                "profile_sha256": sha256_file(profile),
                                "receipt_sha256": sha256_file(profile.parent / "receipt.json")}
    path = root / "project-state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


def model_artefact(path, root, *, role="model_contract", identity="design", depends=None):
    defaults = ["model", "problem"]
    if role == "model_approval":
        defaults.append("approval")
    return {"id": identity, "role": role, "path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path), "status": "accepted",
            "depends_on": defaults if depends is None else depends}


@pytest.mark.parametrize("status,stage", [("proposed", "MODEL_PROPOSED"),
                                         ("challenged", "MODEL_CHALLENGED"),
                                         ("approved", "MODEL_APPROVED")])
def test_c_states_require_current_frozen_problem_and_current_design_without_runtime(tmp_path, status, stage):
    model = make_model_contract(tmp_path, status=status)
    artefacts = [model_artefact(model, tmp_path)]
    if status == "approved":
        approval = contained_path(tmp_path, load_document(model)["approval"]["path"])
        artefacts.append(model_artefact(approval, tmp_path, role="model_approval", identity="decision"))
    state = write_model_state(tmp_path, model, stage=stage, artefacts=artefacts)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    for scope in ("all", "model"):
        result = validate_project_state(state, scope=scope)
        assert result["valid"], result["errors"]
        assert result["model_checked"] is True and result["environment_checked"] is False
        assert result["model_validation"]["approved"] is (status == "approved")
        assert result["model_approved"] is (status == "approved")
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("stage", ["MODEL_PROPOSED", "MODEL_CHALLENGED", "MODEL_APPROVED"])
def test_complete_draft_does_not_claim_a_c_state(tmp_path, stage):
    model = make_model_contract(tmp_path, status="draft")
    state = write_model_state(tmp_path, model, stage=stage)
    assert not validate_project_state(state, scope="model")["valid"]


def test_recorded_blocked_challenge_can_be_challenged_but_never_approved(tmp_path):
    model = make_model_contract(tmp_path, status="challenged", blocked_challenge=True)
    state = write_model_state(tmp_path, model, stage="MODEL_CHALLENGED")
    result = validate_project_state(state, scope="model")
    assert result["valid"], result["errors"]
    assert result["model_validation"]["challenge_complete"] is True
    assert result["model_validation"]["ready_for_approval"] is False
    assert result["model_approved"] is False
    state = write_model_state(tmp_path, model, stage="MODEL_APPROVED")
    assert not validate_project_state(state, scope="model")["valid"]


def test_problem_scope_never_claims_model_or_whole_project_qualification(tmp_path):
    model = make_model_contract(tmp_path, status="approved")
    state = write_model_state(tmp_path, model, stage="MODEL_APPROVED")
    value = load_document(model)
    source = contained_path(tmp_path, value["brief"]["path"])
    source.write_bytes(source.read_bytes() + b"\nchanged brief\n")
    full = validate_project_state(state, scope="model")
    assert not full["valid"] and "model" in full["stale_artefacts"]
    partial = validate_project_state(state, scope="problem")
    assert partial["valid"], partial["errors"]
    assert partial["model_checked"] is False
    assert partial["stage_assessment"] == "problem_only"
    assert partial["model_approved"] is False
    assert "model_validation" not in partial


def test_runtime_expiry_does_not_expire_unchanged_mathematical_design(tmp_path):
    model = make_model_contract(tmp_path, status="approved")
    profile = make_profile(tmp_path / "runtime", age_hours=25)
    state = write_model_state(tmp_path, model, stage="MODEL_APPROVED", profile=profile,
                              artefacts=[model_artefact(model, tmp_path)])
    full = validate_project_state(state)
    assert not full["valid"] and "environment" in full["stale_artefacts"]
    assert "model" not in full["stale_artefacts"]
    partial = validate_project_state(state, scope="model")
    assert partial["valid"] and partial["model_approved"]
    assert partial["environment_checked"] is False
    assert partial["stage_assessment"] == "problem_and_model_only"


@pytest.mark.parametrize("change", ["project_id", "model_sha", "approval_sha", "approval_path"])
def test_current_project_and_c_bindings_cannot_be_substituted(tmp_path, change):
    model = make_model_contract(tmp_path, status="approved")
    state = write_model_state(tmp_path, model, stage="MODEL_APPROVED")
    value = load_document(state)
    if change == "project_id":
        value["project_id"] = "other-project"
    elif change == "model_sha":
        value["model"]["sha256"] = "0" * 64
    elif change == "approval_sha":
        value["approval"]["sha256"] = "0" * 64
    else:
        original = contained_path(tmp_path, value["approval"]["path"])
        copied = tmp_path / "copied-approval.json"
        copied.write_bytes(original.read_bytes())
        value["approval"]["path"] = copied.name
    state.write_text(json.dumps(value), encoding="utf-8")
    assert not validate_project_state(state, scope="model")["valid"]


def test_current_approval_requires_an_explicit_matching_state_binding(tmp_path):
    model = make_model_contract(tmp_path, status="approved")
    state = write_model_state(tmp_path, model, stage="NEW", bind_approval=False)
    result = validate_project_state(state, scope="model")
    assert not result["valid"] and not result["model_approved"]


@pytest.mark.parametrize("role", ["model_contract", "model_approval"])
@pytest.mark.parametrize("indirect", [False, True])
def test_accepted_model_evidence_rejects_environment_dependencies(tmp_path, role, indirect):
    model = make_model_contract(tmp_path, status="approved")
    profile = make_profile(tmp_path / "runtime")
    path = model if role == "model_contract" else contained_path(tmp_path, load_document(model)["approval"]["path"])
    item = model_artefact(path, tmp_path, role=role)
    artefacts = [item]
    environment_dependency = "environment"
    if indirect:
        environment_dependency = "runtime-evidence"
        artefacts.append({"id": environment_dependency, "role": "environment_profile",
                          "path": profile.relative_to(tmp_path).as_posix(), "sha256": sha256_file(profile),
                          "status": "accepted", "depends_on": ["environment"]})
    item["depends_on"].append(environment_dependency)
    state = write_model_state(tmp_path, model, stage="MODEL_APPROVED", profile=profile, artefacts=artefacts)
    for scope in ("all", "model"):
        result = validate_project_state(state, scope=scope)
        assert not result["valid"]
        assert any("cannot depend on environment" in error for error in result["errors"])


@pytest.mark.parametrize("role", ["model_contract", "model_approval"])
def test_accepted_c_evidence_requires_exact_path_and_all_project_anchors(tmp_path, role):
    model = make_model_contract(tmp_path, status="approved")
    path = model if role == "model_contract" else contained_path(tmp_path, load_document(model)["approval"]["path"])
    copy = tmp_path / "copied.json"
    copy.write_bytes(path.read_bytes())
    item = model_artefact(copy, tmp_path, role=role)
    state = write_model_state(tmp_path, model, artefacts=[item])
    assert not validate_project_state(state, scope="model")["valid"]
    item = model_artefact(path, tmp_path, role=role, depends=["model"])
    state = write_model_state(tmp_path, model, artefacts=[item])
    assert not validate_project_state(state, scope="model")["valid"]


def test_source_change_marks_problem_model_and_transitive_accepted_evidence_stale(tmp_path):
    model = make_model_contract(tmp_path, status="approved")
    artefacts = [model_artefact(model, tmp_path)]
    approval = contained_path(tmp_path, load_document(model)["approval"]["path"])
    artefacts.append(model_artefact(approval, tmp_path, role="model_approval", identity="decision",
                                    depends=["approval", "model", "problem", "design"]))
    state = write_model_state(tmp_path, model, stage="MODEL_APPROVED", artefacts=artefacts)
    assert validate_project_state(state, scope="model")["valid"]
    problem = contained_path(tmp_path, load_document(model)["problem"]["path"])
    source = contained_path(tmp_path, load_document(problem)["sources"][0]["path"])
    source.write_bytes(source.read_bytes() + b"\nchanged statement\n")
    before = state.read_bytes()
    result = validate_project_state(state, scope="model")
    assert not result["valid"]
    assert {"problem", "model", "design", "decision"} <= set(result["stale_artefacts"])
    assert state.read_bytes() == before


@pytest.mark.parametrize("source_kind", ["freeze", "decision", "locked_model_spec", "foundation"])
def test_review_and_model_basis_changes_invalidate_current_c_evidence(tmp_path, source_kind):
    model = make_model_contract(tmp_path, status="approved")
    value = load_document(model)
    approval = contained_path(tmp_path, value["approval"]["path"])
    artefacts = [model_artefact(model, tmp_path),
                 model_artefact(approval, tmp_path, role="model_approval", identity="decision")]
    state = write_model_state(tmp_path, model, stage="MODEL_APPROVED", artefacts=artefacts)
    assert validate_project_state(state, scope="model")["valid"]
    if source_kind == "freeze":
        problem = contained_path(tmp_path, value["problem"]["path"])
        source_ref = load_document(problem)["freeze"]["decision"]
    elif source_kind == "foundation":
        source_ref = next(source for source in value["sources"] if source["id"] == "foundation")
    else:
        source_ref = load_document(approval)[source_kind]
    source = contained_path(tmp_path, source_ref["path"])
    source.write_bytes(source.read_bytes() + b"\nchanged bound evidence\n")
    result = validate_project_state(state, scope="model")
    assert not result["valid"] and not result["model_approved"]
    assert {"model", "design", "decision"} <= set(result["stale_artefacts"])
    if source_kind == "freeze":
        assert "problem" in result["stale_artefacts"]


def test_rebinding_changed_model_bytes_cannot_reuse_old_human_approval(tmp_path):
    model = make_model_contract(tmp_path, status="approved")
    value = load_document(model)
    value["designs"][0]["models"][0]["solver_plan"]["method"] = "ode15s; still unexecuted"
    model.write_text(json.dumps(value), encoding="utf-8")
    state = write_model_state(tmp_path, model, stage="MODEL_APPROVED")
    result = validate_project_state(state, scope="model")
    assert not result["valid"] and not result["model_approved"]
    assert any("model_semantic_sha256" in error for error in result["errors"])
    assert "model" in result["stale_artefacts"]


def test_complete_unapproved_draft_cannot_be_an_accepted_model_artefact(tmp_path):
    model = make_model_contract(tmp_path, status="draft")
    state = write_model_state(tmp_path, model, artefacts=[model_artefact(model, tmp_path)])
    result = validate_project_state(state, scope="model")
    assert not result["valid"] and "design" in result["stale_artefacts"]


def test_model_scope_still_rejects_global_path_escape_and_c_dependency_cycles(tmp_path):
    model = make_model_contract(tmp_path, status="proposed")
    item = model_artefact(model, tmp_path, depends=["problem", "model", "design"])
    state = write_model_state(tmp_path, model, artefacts=[item])
    assert not validate_project_state(state, scope="model")["valid"]
    state = write_model_state(tmp_path, model)
    value = load_document(state)
    value["approval"] = {"path": "../escape.json", "sha256": "0" * 64}
    state.write_text(json.dumps(value), encoding="utf-8")
    result = validate_project_state(state, scope="problem")
    assert not result["valid"] and any("leaves project root" in error for error in result["errors"])


def test_model_scope_cli_reports_partial_evidence_without_state_mutation(tmp_path):
    model = make_model_contract(tmp_path, status="challenged")
    state = write_model_state(tmp_path, model, stage="MODEL_CHALLENGED")
    before = state.read_bytes()
    completed = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/validate_project_state.py"),
                                str(state), "--scope", "model"], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout
    report = json.loads(completed.stdout)
    assert report["scope"] == "model" and report["environment_checked"] is False
    assert report["model_checked"] is True and report["model_approved"] is False
    assert state.read_bytes() == before
