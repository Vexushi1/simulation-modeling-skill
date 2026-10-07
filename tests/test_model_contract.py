"""Design gates distinguish source-bound proposals from actual approval."""
from __future__ import annotations

import copy
import json
import subprocess
import sys

import pytest

from model_factory import approve_contract, file_ref, make_model_contract
from problem_factory import read_contract, write_contract
from runtime_common import ROOT, sha256_file
from validate_model_contract import expected_locked_spec, model_identity, semantic_digest, validate_model_contract


def main_model(contract):
    return contract["designs"][0]["models"][0]


def mutate(path, change):
    contract = read_contract(path)
    change(contract)
    write_contract(path, contract)
    return validate_model_contract(path)


def mutate_approval(path, change):
    contract = read_contract(path)
    approval_path = path.parent / contract["approval"]["path"]
    approval = read_contract(approval_path)
    change(approval)
    write_contract(approval_path, approval)
    contract["approval"] = file_ref(path.parent, approval_path)
    write_contract(path, contract)
    return validate_model_contract(path)


@pytest.mark.parametrize("status", ["draft", "proposed", "challenged", "approved"])
def test_current_shared_design_statuses(tmp_path, status):
    path = make_model_contract(tmp_path, status=status)
    result = validate_model_contract(path)
    assert result["valid"] and result["schema_valid"] and result["proposal_complete"]
    assert result["challenge_complete"] == (status in {"challenged", "approved"})
    assert result["ready_for_approval"] == (status in {"challenged", "approved"})
    assert result["approved"] == (status == "approved")
    assert result["question_ids"] == ["Q1", "Q2"] and len(result["model_identities"]) == 1
    assert result["contract_sha256"] == sha256_file(path)
    assert result["problem_path"] == str((tmp_path / "problem.json").resolve())


def designs_with_dotted_ids(contract, *, collision):
    first = contract["designs"][0]
    second = copy.deepcopy(first)
    first.update(id="d.a", main_model="b")
    first["models"][0]["id"] = "b"
    second.update(id="d", main_model="a.b" if collision else "a.c")
    second["models"][0]["id"] = second["main_model"]
    contract["designs"].append(second)


@pytest.mark.parametrize("status", ["proposed", "challenged", "approved"])
def test_combined_identity_key_collision_cannot_pass_design_gates(tmp_path, status):
    path = make_model_contract(tmp_path, status=status)
    result = mutate(path, lambda contract: designs_with_dotted_ids(contract, collision=True))
    assert result["schema_valid"] and not result["valid"]
    assert not any(result[field] for field in ("proposal_complete", "challenge_complete", "ready_for_approval", "approved"))
    assert result["model_identities"] == {}
    assert any("identity key collision: d.a.b" in error for error in result["errors"])


def test_locked_spec_cannot_silently_drop_colliding_model_identity(tmp_path):
    contract = read_contract(make_model_contract(tmp_path, status="challenged"))
    designs_with_dotted_ids(contract, collision=True)
    with pytest.raises(ValueError, match="identity key collision: d.a.b"):
        expected_locked_spec(contract)


def test_noncolliding_dotted_ids_preserve_all_models_and_approval(tmp_path):
    path = make_model_contract(tmp_path, status="challenged")
    result = mutate(path, lambda contract: designs_with_dotted_ids(contract, collision=False))
    assert result["valid"] and result["ready_for_approval"]
    assert set(result["model_identities"]) == {"d.a.b", "d.a.c"}
    assert len(expected_locked_spec(read_contract(path))["model_identities"]) == 2
    approve_contract(path)
    assert validate_model_contract(path, require_approved=True)["approved"]


def test_template_is_a_legal_incomplete_draft():
    path = ROOT / "templates/contracts/model_contract.yaml"
    result = validate_model_contract(path)
    assert result["valid"] and result["schema_valid"]
    assert not result["proposal_complete"] and not result["challenge_complete"] and not result["approved"]
    assert {"current_frozen_problem", "approval_brief", "model_designs"} <= set(result["missing_gates"])


@pytest.mark.parametrize("body", ["{}", "[]", '{"schema_version":1,"schema_version":1}', '{"x":NaN}', "bad: ["])
def test_malformed_contract_is_controlled_failure(tmp_path, body):
    path = tmp_path / ("model.yaml" if body == "bad: [" else "model.json")
    path.write_text(body, encoding="utf-8")
    assert not validate_model_contract(path)["valid"]


def test_missing_contract_is_controlled_failure(tmp_path):
    result = validate_model_contract(tmp_path / "missing.json")
    assert not result["valid"] and result["contract_sha256"] is None


@pytest.mark.parametrize("required", ["require_proposed", "require_challenged", "require_approved"])
def test_complete_draft_cannot_promote_itself_by_validation(tmp_path, required):
    path = make_model_contract(tmp_path)
    assert validate_model_contract(path)["proposal_complete"]
    assert not validate_model_contract(path, **{required: True})["valid"]
    assert read_contract(path)["status"] == "draft" and read_contract(path)["approval"] is None


@pytest.mark.parametrize("status", ["proposed", "challenged", "approved"])
def test_nonfrozen_problem_cannot_support_formal_design(tmp_path, status):
    path = make_model_contract(tmp_path, status=status)
    problem_path = tmp_path / "problem.json"
    problem = read_contract(problem_path)
    problem.update(status="audited", freeze=None)
    write_contract(problem_path, problem)
    mutate(path, lambda contract: contract.update(problem=file_ref(tmp_path, problem_path)))
    result = validate_model_contract(path)
    assert not result["valid"] and not result["proposal_complete"] and not result["approved"]
    assert "current_frozen_problem" in result["missing_gates"]


def test_draft_may_review_an_unfrozen_problem_without_claiming_proposal(tmp_path):
    path = make_model_contract(tmp_path)
    problem_path = tmp_path / "problem.json"
    problem = read_contract(problem_path)
    problem.update(status="draft", freeze=None)
    write_contract(problem_path, problem)
    result = mutate(path, lambda contract: contract.update(problem=file_ref(tmp_path, problem_path)))
    assert result["valid"] and not result["proposal_complete"]


@pytest.mark.parametrize("filename,label", [
    ("statement.txt", "problem:source:statement"),
    ("observations.csv", "problem:source:measurements"),
    ("freeze-review.txt", "problem:freeze_decision"),
    ("design-foundation.txt", "source:foundation"),
    ("model-approval-brief.md", "brief"),
    ("human-model-decision.txt", "approval_decision"),
    ("locked-model-spec.json", "locked_model_spec"),
    ("model-approval.json", "approval"),
])
@pytest.mark.parametrize("mode", ["missing", "changed"])
def test_current_evidence_bytes_are_required(tmp_path, filename, label, mode):
    path = make_model_contract(tmp_path, status="approved")
    target = tmp_path / filename
    if mode == "missing":
        target.unlink()
    else:
        target.write_bytes(target.read_bytes() + b"changed\n")
    result = validate_model_contract(path)
    assert not result["valid"] and not result["approved"]
    assert label in result["changed_sources"]


@pytest.mark.parametrize("change,fragment", [
    (lambda c: c["designs"][0].update(question_ids=["missing"]), "unknown reference"),
    (lambda c: c["designs"][0].update(requirement_ids=["missing"]), "unknown reference"),
    (lambda c: c["designs"][0].update(main_model="missing"), "main_model"),
    (lambda c: c["designs"].append(copy.deepcopy(c["designs"][0])), "duplicate id"),
    (lambda c: main_model(c)["body"]["relations"][0].update(variable_ids=["missing"]), "unknown reference"),
    (lambda c: main_model(c)["body"].update(outputs=["power"]), "incompatible roles"),
    (lambda c: main_model(c)["body"]["variables"][0].update(role_relation=None), "multiple roles"),
    (lambda c: main_model(c)["body"]["variables"][0].update(unit=" "), "unknown unit"),
    (lambda c: main_model(c)["body"]["variables"][1].update(symbol="T"), "symbols must identify"),
    (lambda c: main_model(c).update(structure="ode45"), "unknown mathematical structure"),
    (lambda c: main_model(c).update(name="ode45"), "solver name"),
    (lambda c: main_model(c)["body"]["mechanisms"][0].update(relation_ids=["missing"]), "unknown reference"),
    (lambda c: main_model(c)["validator_plan"][0].update(source_ids=["missing"]), "unknown reference"),
    (lambda c: c["sources"][1].update(problem_source_id="missing"), "unknown problem source"),
    (lambda c: c["sources"][1].update(problem_source_id="statement"), "differs from referenced"),
])
def test_broken_structure_and_references_are_rejected(tmp_path, change, fragment):
    result = mutate(make_model_contract(tmp_path, status="proposed"), change)
    assert not result["valid"] and any(fragment in error for error in result["errors"])


@pytest.mark.parametrize("change,gate", [
    (lambda c: c["designs"][0].update(question_ids=["Q1"]), "question_coverage"),
    (lambda c: c["designs"][0]["requirement_ids"].pop(), "requirement_coverage"),
    (lambda c: main_model(c)["body"].update(relations=[]), "mathematical_body:shared_tank_design.thermal_balance"),
    (lambda c: main_model(c)["body"]["variables"][0].update(unit=None), "unit:shared_tank_design.thermal_balance.temperature"),
    (lambda c: main_model(c).update(validator_plan=[]), "validator_plan:shared_tank_design.thermal_balance"),
])
def test_missing_substantive_content_cannot_be_proposed(tmp_path, change, gate):
    result = mutate(make_model_contract(tmp_path, status="proposed"), change)
    assert not result["valid"] and not result["proposal_complete"] and gate in result["missing_gates"]


def test_condition_given_by_problem_cannot_be_unknown_or_na(tmp_path):
    path = make_model_contract(tmp_path, status="proposed")
    for status in ("unknown", "not_applicable"):
        result = mutate(path, lambda c: main_model(c)["body"]["initial_conditions"].update(status=status, value=None))
        assert not result["valid"]
        assert any("explicit problem conditions" in error for error in result["errors"])


def test_shared_requirement_must_be_represented_for_each_question(tmp_path):
    path = make_model_contract(tmp_path, status="proposed")
    contract = read_contract(path)
    first = contract["designs"][0]
    second = copy.deepcopy(first)
    first["question_ids"] = ["Q1"]
    first["requirement_ids"] = ["R1", "R2", "R3", "R4", "R5", "R6"]
    second.update(id="q2_design", question_ids=["Q2"], requirement_ids=["R7", "R8", "R9"])
    contract["designs"].append(second)
    write_contract(path, contract)
    result = validate_model_contract(path)
    assert not result["valid"] and "question_requirement_coverage" in result["missing_gates"]


def test_planned_vv_cannot_report_passed_evidence(tmp_path):
    result = mutate(make_model_contract(tmp_path, status="proposed"), lambda c: main_model(c)["validator_plan"][0].update(status="passed"))
    assert not result["valid"] and not result["schema_valid"]


@pytest.mark.parametrize("provenance", ["identified", "calibrated", "optimized"])
def test_existing_parameter_estimate_requires_current_evidence(tmp_path, provenance):
    path = make_model_contract(tmp_path, status="proposed")
    result = mutate(path, lambda c: main_model(c)["body"]["variables"][-1]["parameter"].update(value=4.5, provenance=provenance, source_ids=[]))
    assert not result["valid"] and any("existing estimate requires" in error for error in result["errors"])
    evidence_path = tmp_path / "existing-estimate.json"
    write_contract(evidence_path, {"fixture_only": True, "parameter": "H", "value": 4.5, "unit": "W/K", "method": "synthetic prior estimate; no actual calibration qualification"})
    contract = read_contract(path)
    contract["sources"].append({"id": "prior_estimate", **file_ref(tmp_path, evidence_path), "purpose": "Previously supplied estimate, not computed by Phase C", "problem_source_id": None})
    main_model(contract)["body"]["variables"][-1]["parameter"]["source_ids"] = ["prior_estimate"]
    write_contract(path, contract)
    assert validate_model_contract(path)["valid"]
    evidence_path.write_bytes(evidence_path.read_bytes() + b"changed")
    assert not validate_model_contract(path)["valid"]


@pytest.mark.parametrize("provenance", ["given", "derived"])
def test_given_or_derived_value_needs_source_and_derived_basis(tmp_path, provenance):
    path = make_model_contract(tmp_path, status="proposed")
    contract = read_contract(path)
    variable = main_model(contract)["body"]["variables"][-1]
    variable["requirement_ids"] = []
    variable["parameter"].update(value=4.5, provenance=provenance, source_ids=[])
    write_contract(path, contract)
    assert not validate_model_contract(path)["valid"]


def test_unknown_parameter_has_no_fabricated_value_and_requires_plan(tmp_path):
    path = make_model_contract(tmp_path, status="proposed")
    assert main_model(read_contract(path))["body"]["variables"][-1]["parameter"]["value"] is None
    result = mutate(path, lambda c: main_model(c)["body"]["variables"][-1]["parameter"].update(plan=None))
    assert not result["proposal_complete"] and not result["valid"]


def test_nonfinite_yaml_value_is_rejected(tmp_path):
    path = make_model_contract(tmp_path)
    contract = read_contract(path)
    main_model(contract)["body"]["variables"][-1]["parameter"]["value"] = float("inf")
    import yaml

    yaml_path = tmp_path / "nonfinite.yaml"
    yaml_path.write_text(yaml.safe_dump(contract), encoding="utf-8")
    assert not validate_model_contract(yaml_path)["valid"]


def test_blocked_challenge_is_reviewed_but_cannot_be_approved(tmp_path):
    path = make_model_contract(tmp_path, status="challenged", blocked_challenge=True)
    result = validate_model_contract(path, require_challenged=True)
    assert result["valid"] and result["challenge_complete"] and not result["ready_for_approval"]
    approve_contract(path)
    result = validate_model_contract(path, require_approved=True)
    assert not result["valid"] and not result["approved"]


def test_pending_review_cannot_claim_challenged_status(tmp_path):
    result = mutate(make_model_contract(tmp_path, status="proposed"), lambda c: c.update(status="challenged"))
    assert not result["valid"] and not result["challenge_complete"]


def test_not_applicable_review_requires_a_substantive_reason(tmp_path):
    path = make_model_contract(tmp_path, status="challenged")
    result = mutate(path, lambda c: c["designs"][0]["challenge"]["hybrid_events"].update(status="not_applicable"))
    assert result["valid"]
    result = mutate(path, lambda c: c["designs"][0]["challenge"]["hybrid_events"].update(reason=" "))
    assert not result["valid"]


def test_model_identity_excludes_solver_parameter_values_and_review_evidence(tmp_path):
    contract = read_contract(make_model_contract(tmp_path))
    model = main_model(contract)
    before, proposal_before = model_identity(model), semantic_digest(contract)
    model["solver_plan"]["method"] = "ode15s"
    model["body"]["variables"][-1]["parameter"].update(value=7.5, provenance="assumed", source_ids=[], plan="Disclosed stress scenario only")
    model["body"]["initial_conditions"]["value"] = {"temperature": 30, "unit": "degC"}
    model["validator_plan"][0]["criterion"] = "A newly proposed criterion"
    assert model_identity(model) == before and semantic_digest(contract) != proposal_before
    model["body"]["relations"][0]["expression"] = "C_eff*dT/dt = P - H*(T-T_a)^2"
    assert model_identity(model) != before


def test_declaration_registry_reordering_is_not_an_alternate_model(tmp_path):
    model = main_model(read_contract(make_model_contract(tmp_path)))
    identity = model_identity(model)
    model["body"]["variables"].reverse()
    model["body"]["relations"].reverse()
    model["body"]["assumptions"].reverse()
    model["body"]["inputs"].reverse()
    model["body"]["relations"][0]["variable_ids"].reverse()
    assert model_identity(model) == identity


def test_alternate_model_must_change_declared_mathematical_structure(tmp_path):
    path = make_model_contract(tmp_path, status="proposed")
    contract = read_contract(path)
    alternate = copy.deepcopy(main_model(contract))
    alternate.update(id="alternate", name="High cost solver route")
    alternate["solver_plan"]["method"] = "ode15s"
    contract["designs"][0]["models"].append(alternate)
    write_contract(path, contract)
    result = validate_model_contract(path)
    assert not result["valid"] and len(set(result["model_identities"].values())) == 1
    alternate["body"]["relations"][0]["expression"] = "C_eff*dT/dt = P - H*(T-T_a)^2"
    contract["designs"][0]["alternative_review"] = "Nonlinear exchange is a candidate requiring distinct coefficient units and data support review; not executed"
    write_contract(path, contract)
    result = validate_model_contract(path)
    assert result["valid"] and len(set(result["model_identities"].values())) == 2


def test_structural_boundary_relation_belongs_to_mathematical_identity(tmp_path):
    contract = read_contract(make_model_contract(tmp_path, status="proposed"))
    model = main_model(contract)
    model["body"]["relations"].append({"id": "ambient_operator", "expression": "T_a is imposed uniformly on the tank boundary",
                                       "variable_ids": ["ambient"], "requirement_ids": [], "role": "boundary"})
    identity = model_identity(model)
    model["body"]["boundary_conditions"]["value"]["ambient_temperature"] = 30
    assert model_identity(model) == identity
    model["body"]["relations"][-1]["expression"] = "No heat flux crosses the tank boundary"
    assert model_identity(model) != identity


def test_approval_digest_excludes_only_status_and_external_approval_reference(tmp_path):
    contract = read_contract(make_model_contract(tmp_path))
    digest = semantic_digest(contract)
    contract.update(status="approved", approval={"path": "unvalidated.json", "sha256": "0" * 64})
    assert semantic_digest(contract) == digest
    contract["brief"]["sha256"] = "1" * 64
    assert semantic_digest(contract) != digest


def test_hand_written_approved_status_does_not_create_human_decision(tmp_path):
    result = mutate(make_model_contract(tmp_path, status="challenged"), lambda c: c.update(status="approved"))
    assert not result["valid"] and not result["approved"]
    assert any("no external human decision" in error for error in result["errors"])


@pytest.mark.parametrize("change", [
    lambda a: a.update(project_id="other-project"),
    lambda a: a.update(problem_sha256="0" * 64),
    lambda a: a.update(model_semantic_sha256="0" * 64),
    lambda a: a["decision"].update(actor_kind="agent"),
    lambda a: a["decision"].update(action="reject"),
    lambda a: a["decision"].update(start=1),
    lambda a: a["decision"].update(quote="handwritten approval"),
])
def test_invalid_or_unbound_human_decision_is_rejected(tmp_path, change):
    result = mutate_approval(make_model_contract(tmp_path, status="approved"), change)
    assert not result["valid"] and not result["approved"]


@pytest.mark.parametrize("replacement", ["The human rejected this design; action=approve is only an example", "action=reject", "action=approve\naction=revoke"])
def test_approval_context_is_unique_exact_action_line(tmp_path, replacement):
    path = make_model_contract(tmp_path, status="approved")
    def change(approval):
        decision = approval["decision"]
        quote = decision["quote"].replace("action=approve", replacement)
        target = tmp_path / decision["path"]
        target.write_text(quote + "\n", encoding="utf-8", newline="\n")
        decision.update(sha256=sha256_file(target), quote=quote, end=len(quote))
    result = mutate_approval(path, change)
    assert not result["valid"] and any("context line required for action" in error for error in result["errors"])


def test_old_human_decision_cannot_be_rebound_to_new_design_digest(tmp_path):
    path = make_model_contract(tmp_path, status="approved")
    contract = read_contract(path)
    contract["designs"][0]["selection_reason"] = "Changed design scope needs renewed decision"
    write_contract(path, contract)
    new_digest = semantic_digest(contract)
    locked_path = tmp_path / "locked-model-spec.json"
    write_contract(locked_path, expected_locked_spec(contract))
    result = mutate_approval(path, lambda a: a.update(model_semantic_sha256=new_digest, locked_model_spec=file_ref(tmp_path, locked_path)))
    assert not result["valid"] and not result["approved"]
    assert any("context line required for model_semantic_sha256" in error for error in result["errors"])


@pytest.mark.parametrize("payload", [{"locked": True}, {"schema_version": 1, "design": {}}])
def test_locked_flag_or_empty_payload_is_not_a_locked_model(tmp_path, payload):
    path = make_model_contract(tmp_path, status="approved")
    locked_path = tmp_path / "locked-model-spec.json"
    write_contract(locked_path, payload)
    result = mutate_approval(path, lambda a: a.update(locked_model_spec=file_ref(tmp_path, locked_path)))
    assert not result["valid"] and any("complete current design payload" in error for error in result["errors"])


def test_expected_paths_check_bindings_without_substituting_files(tmp_path):
    path = make_model_contract(tmp_path, status="approved")
    assert validate_model_contract(path, problem_path=tmp_path / "problem.json", approval_path=tmp_path / "model-approval.json")["valid"]
    for keyword, filename in (("problem_path", "problem.json"), ("approval_path", "model-approval.json")):
        copied = tmp_path / f"copy-{filename}"
        copied.write_bytes((tmp_path / filename).read_bytes())
        result = validate_model_contract(path, **{keyword: copied})
        assert not result["valid"] and any("expected path differs" in error for error in result["errors"])


def test_evidence_and_contract_paths_are_inside_project_root(tmp_path):
    root = tmp_path / "project"
    path = make_model_contract(root, status="proposed")
    assert not validate_model_contract(path, project_root=tmp_path / "other")["valid"]
    outside = tmp_path / "outside.txt"
    outside.write_bytes((root / "design-foundation.txt").read_bytes())
    result = mutate(path, lambda c: c["sources"][0].update(path="../outside.txt"))
    assert not result["valid"] and any("leaves project root" in error for error in result["errors"])


def test_validator_and_cli_are_read_only(tmp_path):
    path = make_model_contract(tmp_path, status="approved")
    before = {file.name: file.read_bytes() for file in tmp_path.iterdir()}
    assert validate_model_contract(path, require_approved=True)["valid"]
    completed = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/validate_model_contract.py"), str(path), "--require-approved", "--project-root", str(tmp_path)], capture_output=True, text=True)
    assert completed.returncode == 0 and json.loads(completed.stdout)["approved"]
    assert {file.name: file.read_bytes() for file in tmp_path.iterdir()} == before
