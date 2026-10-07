from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from problem_factory import freeze_contract, make_contract, read_contract, review_reference, write_contract
from runtime_common import ROOT, load_document, sha256_file
from validate_problem_contract import semantic_digest, validate_problem_contract


def mutate(path, change):
    contract = read_contract(path)
    change(contract)
    write_contract(path, contract)
    return validate_problem_contract(path)


@pytest.mark.parametrize("status", ["draft", "audited", "frozen"])
def test_complete_current_contract(tmp_path, status):
    path = make_contract(tmp_path, status=status)
    result = validate_problem_contract(path)
    assert result["valid"] and result["schema_valid"] and result["audit_complete"]
    assert result["freeze_ready"] and result["frozen"] == (status == "frozen")
    assert result["project_id"] == "synthetic-tank" and result["question_ids"] == ["Q1", "Q2"]
    assert result["contract_sha256"] == sha256_file(path)


def test_template_remains_incomplete_draft():
    result = validate_problem_contract(ROOT / "templates/contracts/problem_contract.yaml")
    assert result["valid"] and result["schema_valid"]
    assert not result["audit_complete"] and not result["freeze_ready"] and not result["frozen"]
    assert {"statement_sources", "questions", "requirements"} <= set(result["missing_gates"])


@pytest.mark.parametrize("body", ["{}", "[]", '{"schema_version":1,"schema_version":1}', '{"x":NaN}', "bad: ["])
def test_malformed_contract_returns_controlled_result(tmp_path, body):
    path = tmp_path / ("problem.yaml" if body == "bad: [" else "problem.json")
    path.write_text(body, encoding="utf-8")
    assert not validate_problem_contract(path)["valid"]


def test_missing_contract_returns_controlled_result(tmp_path):
    result = validate_problem_contract(tmp_path / "missing.json")
    assert not result["valid"] and result["contract_sha256"] is None


@pytest.mark.parametrize("filename", ["statement.txt", "observations.csv"])
@pytest.mark.parametrize("mode", ["changed", "missing"])
def test_source_bytes_changed_or_missing(tmp_path, filename, mode):
    path = make_contract(tmp_path, status="frozen")
    target = tmp_path / filename
    if mode == "changed":
        target.write_bytes(target.read_bytes() + b"changed\n")
    else:
        target.unlink()
    result = validate_problem_contract(path)
    assert not result["valid"] and not result["frozen"] and result["changed_sources"]


@pytest.mark.parametrize("change,match", [
    (lambda c: c["audit_units"][1].update(start=1), "quote differs"),
    (lambda c: c["audit_units"].pop(0), "uncovered"),
    (lambda c: c["audit_units"].append({**c["audit_units"][0], "id": "duplicate-range"}), "overlapping"),
    (lambda c: c["audit_units"][0].update(disposition="excluded", reason=""), "reason"),
    (lambda c: c["audit_units"][1].update(requirement_ids=[]), "requirement"),
    (lambda c: c["requirements"][0].update(unit_ids=["U0"]), "reverse"),
    (lambda c: c["requirements"][0].update(question_ids=["unknown"]), "unknown"),
    (lambda c: c["questions"][0]["facts"]["time_domain"].update(requirement_ids=["missing"]), "unknown"),
    (lambda c: c["audit_units"][0].update(source_id="measurements"), "known statement"),
    (lambda c: c["requirements"].append(copy.deepcopy(c["requirements"][0])), "duplicate id"),
])
def test_audit_and_reference_failures(tmp_path, change, match):
    result = mutate(make_contract(tmp_path, status="audited"), change)
    assert not result["valid"]
    assert any(match in error for error in result["errors"])


def test_codepoints_and_crlf_are_not_byte_offsets(tmp_path):
    path = make_contract(tmp_path)
    contract = read_contract(path)
    text = (tmp_path / "statement.txt").read_bytes().decode("utf-8")
    text = "🧪" + text.replace("\n", "\r\n")
    (tmp_path / "statement.txt").write_bytes(text.encode("utf-8"))
    source = contract["sources"][0]
    source["sha256"] = source["text"]["sha256"] = sha256_file(tmp_path / "statement.txt")
    for number, unit in enumerate(contract["audit_units"]):
        shift = number + 1
        unit["start"] += shift
        unit["end"] += shift
    contract["audit_units"][0]["start"] = 0
    contract["audit_units"][0]["quote"] = "🧪" + contract["audit_units"][0]["quote"]
    write_contract(path, contract)
    assert validate_problem_contract(path)["valid"]
    contract["audit_units"][0]["end"] += 3  # Emoji is one codepoint, four UTF-8 bytes.
    write_contract(path, contract)
    assert not validate_problem_contract(path)["valid"]


def extraction_contract(tmp_path):
    path = make_contract(tmp_path)
    contract = read_contract(path)
    source = contract["sources"][0]
    (tmp_path / "statement.pdf").write_bytes(b"Synthetic original PDF fixture bytes; no OCR engine claimed.")
    source["path"], source["sha256"] = "statement.pdf", sha256_file(tmp_path / "statement.pdf")
    source["text"]["verification"] = "reviewed_extraction"
    quote = f"Synthetic extraction checked: raw {source['sha256']} text {source['text']['sha256']}"
    source["text"]["review"] = review_reference(tmp_path, "extraction-review.txt", quote)
    return write_contract(path, contract)


def test_reviewed_extraction_dual_bytes_and_current_review(tmp_path):
    path = extraction_contract(tmp_path)
    assert validate_problem_contract(path)["valid"]
    (tmp_path / "statement.txt").write_bytes(b"different extracted text")
    result = validate_problem_contract(path)
    assert not result["valid"] and "text:statement" in result["changed_sources"]


@pytest.mark.parametrize("change", [
    lambda c: c["sources"][0]["text"].update(review=None),
    lambda c: c["sources"][0]["text"].update(verification="direct_text", review=None),
    lambda c: c["sources"][0]["text"]["review"].update(quote="fabricated review"),
])
def test_extraction_cannot_bypass_review(tmp_path, change):
    assert not mutate(extraction_contract(tmp_path), change)["valid"]


def test_rebound_extraction_requires_new_review_of_new_text(tmp_path):
    path = extraction_contract(tmp_path)
    contract = read_contract(path)
    source = contract["sources"][0]
    (tmp_path / "statement.txt").write_bytes((tmp_path / "statement.txt").read_bytes() + b"\n")
    source["text"]["sha256"] = sha256_file(tmp_path / "statement.txt")
    write_contract(path, contract)
    result = validate_problem_contract(path)
    assert not result["valid"]
    assert any("does not bind" in error for error in result["errors"])


@pytest.mark.parametrize("field", ["initial_conditions", "time_domain", "deliverables"])
def test_explicit_conditions_cannot_be_deferred_or_erased(tmp_path, field):
    path = make_contract(tmp_path)
    result = mutate(path, lambda c: c["questions"][0]["facts"][field].update(status="deferred", value=None))
    assert not result["valid"]
    result = mutate(path, lambda c: c["questions"][0]["facts"][field].update(status="not_specified", requirement_ids=[]))
    assert not result["valid"]


def test_unknown_facts_are_not_fabricated_and_zero_is_specified(tmp_path):
    path = make_contract(tmp_path)
    assert validate_problem_contract(path)["valid"]
    result = mutate(path, lambda c: c["questions"][0]["facts"]["initial_conditions"].update(value=0))
    assert result["valid"]
    result = mutate(path, lambda c: c["questions"][0]["facts"]["events"].update(value="invented event"))
    assert not result["valid"]


def test_state_can_be_observable_with_explained_roles(tmp_path):
    path = make_contract(tmp_path)
    contract = read_contract(path)
    question = contract["questions"][0]
    question["facts"]["state_variables"] = {"status": "specified", "value": "water temperature", "reason": "Reviewed state candidate, no equation locked", "requirement_ids": ["R3"]}
    variable = question["variables"][0]
    variable["roles"] = ["state", "observable"]
    variable["role_relation"] = "The temperature state is directly measured."
    write_contract(path, contract)
    assert validate_problem_contract(path)["valid"]
    variable["role_relation"] = None
    write_contract(path, contract)
    assert not validate_problem_contract(path)["valid"]


@pytest.mark.parametrize("change", [
    lambda c: c["questions"][0]["variables"][0].update(roles=["bogus"]),
    lambda c: c["questions"][0]["variables"][0].update(unit=" "),
    lambda c: c["questions"][0]["variables"][0].update(requirement_ids=[]),
    lambda c: c["questions"][0]["classification"]["objectives"].append("bogus"),
    lambda c: c["questions"][0]["classification"]["model_structures"].append("locked_model"),
])
def test_bad_roles_units_or_classification(tmp_path, change):
    assert not mutate(make_contract(tmp_path), change)["valid"]


@pytest.mark.parametrize("scope", [{"kind": "all"}, {"kind": "rows", "start": 2, "end": 5}])
def test_independence_claim_rejects_any_overlap(tmp_path, scope):
    result = mutate(make_contract(tmp_path), lambda c: c["data_uses"][1].update(scope=scope))
    assert not result["valid"] and any("overlapping" in error for error in result["errors"])


def test_overlap_can_be_disclosed_without_claiming_independence(tmp_path):
    result = mutate(make_contract(tmp_path), lambda c: c["data_uses"][1].update(scope={"kind": "all"}, independence_declared=False))
    assert result["valid"]


def test_copied_data_id_cannot_bypass_overlap(tmp_path):
    path = make_contract(tmp_path)
    contract = read_contract(path)
    copied = {**contract["sources"][1], "id": "copy", "path": "copied.csv"}
    (tmp_path / "copied.csv").write_bytes((tmp_path / "observations.csv").read_bytes())
    contract["sources"].append(copied)
    contract["data_uses"][1].update(source_id="copy", scope={"kind": "all"})
    write_contract(path, contract)
    assert not validate_problem_contract(path)["valid"]


@pytest.mark.parametrize("change", [
    lambda c: c["data_uses"][0].update(source_id="unknown"),
    lambda c: c["data_uses"][0].update(source_id="statement"),
    lambda c: c["data_uses"][0].update(scope={"kind": "rows", "start": 2, "end": 2}),
    lambda c: c["data_uses"][0].update(scope="rows 1-3"),
    lambda c: c["data_uses"][0].update(independence_declared=True),
])
def test_data_role_and_scope_errors(tmp_path, change):
    assert not mutate(make_contract(tmp_path), change)["valid"]


@pytest.mark.parametrize("change,match", [
    (lambda c: c["question_dependencies"][0].update(consumer="unknown"), "unknown"),
    (lambda c: c["question_dependencies"][0].update(consumer="Q1"), "self dependency"),
    (lambda c: c["question_dependencies"].append(copy.deepcopy(c["question_dependencies"][0])), "duplicate dependency"),
    (lambda c: c["question_dependencies"].append({**c["question_dependencies"][0], "producer": "Q2", "consumer": "Q1"}), "cycle"),
])
def test_question_dag_errors(tmp_path, change, match):
    result = mutate(make_contract(tmp_path), change)
    assert not result["valid"] and any(match in error for error in result["errors"])


def test_critical_unknown_is_valid_audit_but_blocks_freeze(tmp_path):
    path = make_contract(tmp_path, status="audited", critical_ambiguity=True)
    result = validate_problem_contract(path)
    assert result["valid"] and result["audit_complete"] and not result["freeze_ready"]
    assert "critical_ambiguity:A1" in result["missing_gates"]
    assert not validate_problem_contract(path, require_frozen=True)["valid"]
    freeze_contract(path)
    assert not validate_problem_contract(path)["frozen"]


def test_noncritical_unknown_can_remain_at_freeze(tmp_path):
    path = make_contract(tmp_path, critical_ambiguity=True)
    mutate(path, lambda c: c["ambiguities"][0].update(critical=False))
    freeze_contract(path)
    assert validate_problem_contract(path, require_frozen=True)["valid"]


def test_resolved_ambiguity_requires_current_independent_decision(tmp_path):
    path = make_contract(tmp_path, critical_ambiguity=True)
    contract = read_contract(path)
    ambiguity = contract["ambiguities"][0]
    ambiguity["status"] = "resolved"
    value = "Validation error must be reported without asserting real-system validity."
    ambiguity["resolution"] = {"value": value, "decision": review_reference(tmp_path, "ambiguity-review.txt", f"Reviewed A1: {value}")}
    write_contract(path, contract)
    freeze_contract(path)
    assert validate_problem_contract(path, require_frozen=True)["valid"]
    (tmp_path / "ambiguity-review.txt").write_text("changed decision", encoding="utf-8")
    result = validate_problem_contract(path)
    assert not result["valid"] and "ambiguity_decision:A1" in result["changed_sources"]


def test_semantic_digest_excludes_only_stage_and_freeze(tmp_path):
    path = make_contract(tmp_path)
    contract = read_contract(path)
    before = semantic_digest(contract)
    contract["status"] = "frozen"
    contract["freeze"] = {"arbitrary": "not part of meaning"}
    assert semantic_digest(contract) == before
    contract["questions"][0]["facts"]["direct_goal"]["value"] = "changed meaning"
    assert semantic_digest(contract) != before


@pytest.mark.parametrize("status,change", [
    ("draft", lambda c: c.update(status="frozen")),
    ("frozen", lambda c: c["freeze"].update(semantic_sha256="0" * 64)),
    ("frozen", lambda c: c["freeze"]["decision"].update(quote="handwritten approval")),
    ("frozen", lambda c: c["questions"][0]["facts"]["direct_goal"].update(value="changed goal")),
])
def test_manual_frozen_or_changed_contract_cannot_pass(tmp_path, status, change):
    path = make_contract(tmp_path, status=status)
    assert not mutate(path, change)["valid"]


def test_replacing_digest_cannot_reuse_old_review(tmp_path):
    path = make_contract(tmp_path, status="frozen")
    contract = read_contract(path)
    contract["questions"][0]["facts"]["direct_goal"]["value"] = "new meaning"
    contract["freeze"]["semantic_sha256"] = semantic_digest(contract)
    write_contract(path, contract)
    result = validate_problem_contract(path)
    assert not result["valid"] and any("review quote does not bind" in error for error in result["errors"])


def test_freeze_review_file_changes_or_missing(tmp_path):
    path = make_contract(tmp_path, status="frozen")
    (tmp_path / "freeze-review.txt").unlink()
    result = validate_problem_contract(path)
    assert not result["valid"] and "freeze_decision" in result["changed_sources"]


def test_contract_and_evidence_cannot_escape_project_root(tmp_path):
    root = tmp_path / "project"
    path = make_contract(root)
    assert not validate_problem_contract(path, project_root=tmp_path / "other")["valid"]
    outside = tmp_path / "outside.txt"
    outside.write_bytes((root / "statement.txt").read_bytes())
    result = mutate(path, lambda c: c["sources"][0].update(path="../outside.txt"))
    assert not result["valid"] and any("leaves project root" in error for error in result["errors"])


def test_validator_and_cli_are_read_only(tmp_path):
    path = make_contract(tmp_path, status="frozen")
    before = {file.name: file.read_bytes() for file in tmp_path.iterdir()}
    assert validate_problem_contract(str(path), require_frozen=True)["valid"]
    completed = subprocess.run([sys.executable, str(ROOT / "scripts/validate_problem_contract.py"), str(path), "--require-frozen", "--project-root", str(tmp_path)], capture_output=True, text=True, check=False)
    assert completed.returncode == 0 and json.loads(completed.stdout)["frozen"]
    assert {file.name: file.read_bytes() for file in tmp_path.iterdir()} == before
