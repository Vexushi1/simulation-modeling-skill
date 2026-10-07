"""Original synthetic source fixtures; review records here are test evidence only."""
from __future__ import annotations

import json
from pathlib import Path

from runtime_common import ROOT, load_document, sha256_file
from validate_problem_contract import FACT_FIELDS, semantic_digest


def write_contract(path: Path, contract: dict) -> Path:
    Path(path).write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return Path(path)


def read_contract(path: Path) -> dict:
    return load_document(path)


def review_reference(root: Path, name: str, quote: str) -> dict:
    path = root / name
    path.write_text(quote + "\n", encoding="utf-8", newline="\n")
    return {"path": name, "sha256": sha256_file(path), "start": 0,
            "end": len(quote), "quote": quote, "reviewed_by": "synthetic-test-reviewer"}


def freeze_contract(path: Path) -> Path:
    contract = read_contract(path)
    digest = semantic_digest(contract)
    quote = f"Synthetic review only: reviewed project {contract['project_id']} semantic_sha256 {digest}; approve problem freeze, not model approval."
    contract["freeze"] = {"semantic_sha256": digest, "decision": review_reference(path.parent, "freeze-review.txt", quote)}
    contract["status"] = "frozen"
    return write_contract(path, contract)


def make_contract(tmp_path: Path, *, status="draft", critical_ambiguity=False) -> Path:
    """Create a complete two-question audit; optionally freeze or retain ambiguity."""
    root = Path(tmp_path)
    root.mkdir(parents=True, exist_ok=True)
    fixtures = ROOT / "tests/fixtures/problem_audit"
    statement_path, data_path = root / "statement.txt", root / "observations.csv"
    statement_path.write_bytes((fixtures / "statement.txt").read_bytes())
    data_path.write_bytes((fixtures / "observations.csv").read_bytes())
    text = statement_path.read_bytes().decode("utf-8")
    source_sha = sha256_file(statement_path)
    contract = {
        "schema_version": 1, "project_id": "synthetic-tank", "status": "draft",
        "sources": [
            {"id": "statement", "kind": "statement", "path": "statement.txt", "sha256": source_sha,
             "text": {"path": "statement.txt", "sha256": source_sha, "verification": "direct_text", "review": None}},
            {"id": "measurements", "kind": "data", "path": "observations.csv", "sha256": sha256_file(data_path), "text": None},
        ],
        "audit_units": [], "requirements": [], "questions": [],
        "question_dependencies": [{"producer": "Q1", "consumer": "Q2", "type": "result", "artefact": "Q1 temperature response", "requirement_ids": ["R7"]}],
        "data_uses": [
            {"id": "fit", "source_id": "measurements", "question_id": "Q2", "role": "calibration", "scope": {"kind": "rows", "start": 0, "end": 3}, "independence_declared": False},
            {"id": "check", "source_id": "measurements", "question_id": "Q2", "role": "validation", "scope": {"kind": "rows", "start": 3, "end": 6}, "independence_declared": True},
        ],
        "ambiguities": [], "freeze": None,
    }
    # Each line is a precise, complete source unit. Category drives fact closure.
    categories = [None, "original_system", "commanded_inputs", "initial_conditions", "time_domain", "direct_goal", "deliverables", "direct_goal", "data", "deliverables"]
    question_sets = [[], ["Q1", "Q2"], ["Q1", "Q2"], ["Q1", "Q2"], ["Q1", "Q2"], ["Q1"], ["Q1"], ["Q2"], ["Q2"], ["Q2"]]
    cursor = 0
    for number, line in enumerate(text.splitlines(keepends=True)):
        quote = line.rstrip("\r\n")
        category, question_ids = categories[number], question_sets[number]
        req_id, unit_id = f"R{number}", f"U{number}"
        contract["audit_units"].append({
            "id": unit_id, "source_id": "statement", "start": cursor,
            "end": cursor + len(quote), "quote": quote,
            "disposition": "requirement" if category else "context",
            "reason": "Explicit synthetic statement" if category else "Test provenance context",
            "requirement_ids": [req_id] if category else [],
        })
        if category:
            contract["requirements"].append({"id": req_id, "unit_ids": [unit_id], "category": category,
                                             "question_ids": question_ids, "interpretation": quote, "origin": "explicit"})
        cursor += len(line)
    for question_id in ("Q1", "Q2"):
        facts = {field: {"status": "not_specified", "value": None, "reason": "Not specified in the synthetic source", "requirement_ids": []} for field in FACT_FIELDS}
        for requirement in contract["requirements"]:
            if question_id in requirement["question_ids"]:
                field = requirement["category"]
                facts[field] = {"status": "specified", "value": requirement["interpretation"],
                                "reason": "Direct source requirement", "requirement_ids": [requirement["id"]]}
        facts["observables"] = {"status": "specified", "value": "water temperature", "reason": "Temperature is explicitly observed", "requirement_ids": ["R3"]}
        facts["constraints"] = {"status": "specified", "value": "heating power <=100 W", "reason": "Input bound is explicit", "requirement_ids": ["R2"]}
        facts["state_variables"] = {"status": "deferred", "value": None, "reason": "State representation belongs to Phase C", "requirement_ids": []}
        variables = [
            {"id": "temperature", "symbol": "T", "quantity": "water temperature", "roles": ["observable"], "role_relation": None, "unit": "degC", "status": "declared", "requirement_ids": ["R3"]},
            {"id": "heating_power", "symbol": "P", "quantity": "heating power", "roles": ["commanded_input"], "role_relation": None, "unit": "W", "status": "declared", "requirement_ids": ["R2"]},
        ]
        if question_id == "Q2":
            facts["parameters"] = {"status": "specified", "value": "heat-loss parameter; representation and value undetermined", "reason": "Source asks for parameter estimation without prescribing a model", "requirement_ids": ["R7"]}
            variables.append({"id": "heat_loss", "symbol": "theta", "quantity": "heat-loss parameter", "roles": ["parameter"], "role_relation": None, "unit": None, "status": "candidate", "requirement_ids": ["R7"]})
        capabilities = (["problem_audit", "simulation_execution", "scientific_visualization"] if question_id == "Q1"
                        else ["problem_audit", "parameter_identification", "calibration", "validation"])
        contract["questions"].append({
            "id": question_id,
            "classification": {"objectives": ["dynamic_response" if question_id == "Q1" else "parameter_identification"], "model_structures": [], "capabilities": capabilities},
            "facts": facts,
            "variables": variables,
        })
    if critical_ambiguity:
        contract["ambiguities"].append({"id": "A1", "question_ids": ["Q2"], "description": "Unspecified validity criterion needs a task decision", "critical": True, "status": "unresolved", "resolution": None})
    path = write_contract(root / "problem.json", contract)
    if status == "frozen":
        return freeze_contract(path)
    contract["status"] = status
    return write_contract(path, contract)
