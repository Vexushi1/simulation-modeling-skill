"""Read-only Phase B source, audit and review-evidence validation.

Coverage and bindings establish mechanical completeness. They cannot establish
that a human interpretation, extraction review or independence claim is true.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from runtime_common import canonical_digest, contained_path, emit, load_contract, load_document, schema_errors, sha256_file

FACT_FIELDS = (
    "original_system", "derived_system", "system_boundary", "commanded_inputs",
    "disturbances", "state_variables", "algebraic_variables", "parameters",
    "decision_variables", "outputs", "observables", "initial_conditions",
    "boundary_conditions", "events", "mode_transitions", "time_domain",
    "spatial_domain", "data", "direct_goal", "implicit_goal", "constraints",
    "deliverables", "risks",
)
DEFERABLE = {
    "derived_system", "system_boundary", "state_variables", "algebraic_variables",
    "parameters", "decision_variables", "events", "mode_transitions", "implicit_goal", "risks",
}
ROLE_FACT = {
    "commanded_input": "commanded_inputs", "disturbance": "disturbances",
    "state": "state_variables", "algebraic": "algebraic_variables",
    "parameter": "parameters", "decision": "decision_variables",
    "output": "outputs", "observable": "observables",
}


def semantic_digest(contract: dict) -> str:
    """Bind meaning and evidence identities independently of stage/review record."""
    return canonical_digest({key: value for key, value in contract.items() if key not in {"status", "freeze"}})


def _meaningful(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True  # Zero and false are valid specified values.


def validate_problem_contract(path, *, require_frozen=False, project_root=None) -> dict:
    """Validate current bytes without writing a contract, decision or project state."""
    result = {
        "valid": False, "schema_valid": False, "audit_complete": False,
        "freeze_ready": False, "frozen": False, "semantic_sha256": None,
        "contract_sha256": None, "project_id": None, "question_ids": [],
        "errors": [], "missing_gates": [], "changed_sources": [],
    }
    errors, missing, changed = result["errors"], result["missing_gates"], result["changed_sources"]
    try:
        path = Path(path).resolve()
        root = Path(project_root).resolve() if project_root is not None else path.parent
        if not path.is_relative_to(root):
            raise ValueError("contract path leaves project root")
        result["contract_sha256"] = sha256_file(path)
        contract = load_document(path)
        result["project_id"] = contract.get("project_id")
        errors.extend(schema_errors(contract, load_contract("core/problem_contract.schema.yaml")))
        result["schema_valid"] = not errors
        if errors:
            return result
        result["semantic_sha256"] = semantic_digest(contract)
        taxonomy = load_contract("core/capability_taxonomy.yaml")
    except (OSError, ValueError, TypeError) as error:
        errors.append(f"contract: {error}")
        return result

    def index(items, label):
        indexed = {}
        for item in items:
            identity = item["id"]
            if identity in indexed:
                errors.append(f"{label}: duplicate id {identity}")
            indexed[identity] = item
        return indexed

    def references(ids, indexed, label):
        for identity in ids:
            if identity not in indexed:
                errors.append(f"{label}: unknown reference {identity}")

    def bound_file(relative, expected, label, *, text=False):
        try:
            file_path = contained_path(root, relative)
            if sha256_file(file_path) != expected:
                raise ValueError("SHA256 differs from bound bytes")
            return file_path.read_bytes().decode("utf-8-sig") if text else file_path
        except (OSError, ValueError, UnicodeError) as error:
            errors.append(f"{label}: {error}")
            if label not in changed:
                changed.append(label)
            return None

    def exact_slice(text, reference, label):
        start, end = reference["start"], reference["end"]
        if start >= end or end > len(text) or text[start:end] != reference["quote"]:
            errors.append(f"{label}: quote differs from Unicode codepoint slice")
            return False
        return True

    def decision(reference, label, bindings):
        text = bound_file(reference["path"], reference["sha256"], label, text=True)
        if text is None:
            return False
        good = exact_slice(text, reference, label)
        for binding in bindings:
            if binding not in reference["quote"]:
                errors.append(f"{label}: review quote does not bind {binding}")
                good = False
        return good

    sources = index(contract["sources"], "sources")
    units = index(contract["audit_units"], "audit_units")
    requirements = index(contract["requirements"], "requirements")
    questions = index(contract["questions"], "questions")
    index(contract["data_uses"], "data_uses")
    index(contract["ambiguities"], "ambiguities")
    result["question_ids"] = list(questions)
    texts = {}
    for identity, source in sources.items():
        raw = bound_file(source["path"], source["sha256"], f"source:{identity}")
        text_ref = source["text"]
        if source["kind"] == "data":
            if text_ref is not None:
                errors.append(f"source:{identity}: data uses bytes and scope, not statement audit text")
            continue
        if text_ref is None:
            missing.append(f"statement_text:{identity}")
            continue
        text = bound_file(text_ref["path"], text_ref["sha256"], f"text:{identity}", text=True)
        if text_ref["verification"] == "direct_text":
            try:
                if contained_path(root, text_ref["path"]) != contained_path(root, source["path"]) or text_ref["sha256"] != source["sha256"]:
                    errors.append(f"text:{identity}: direct_text must be the original UTF-8 source")
            except ValueError as error:
                errors.append(f"text:{identity}: {error}")
            if text_ref["review"] is not None:
                errors.append(f"text:{identity}: direct_text review must be null")
        elif text_ref["review"] is None:
            errors.append(f"text:{identity}: extracted text has no current extraction review")
        else:
            decision(text_ref["review"], f"extraction_review:{identity}", [source["sha256"], text_ref["sha256"]])
        if raw is not None and text is not None:
            texts[identity] = text

    by_source = {identity: [] for identity in texts}
    for identity, unit in units.items():
        source_id = unit["source_id"]
        if source_id not in sources or sources[source_id]["kind"] != "statement":
            errors.append(f"audit_unit:{identity}: source is not a known statement")
        elif source_id in texts:
            exact_slice(texts[source_id], unit, f"audit_unit:{identity}")
            by_source[source_id].append(unit)
        references(unit["requirement_ids"], requirements, f"audit_unit:{identity}")
        if unit["disposition"] == "requirement":
            if not unit["requirement_ids"]:
                errors.append(f"audit_unit:{identity}: requirement disposition needs references")
        elif unit["requirement_ids"]:
            errors.append(f"audit_unit:{identity}: context/excluded cannot claim requirements")
        for req_id in unit["requirement_ids"]:
            if req_id in requirements and identity not in requirements[req_id]["unit_ids"]:
                errors.append(f"audit_unit:{identity}: missing reverse requirement reference {req_id}")

    for identity, text in texts.items():
        ordered = sorted(by_source[identity], key=lambda item: (item["start"], item["end"]))
        cursor = 0
        for unit in ordered:
            start, end = unit["start"], unit["end"]
            if start < cursor:
                errors.append(f"source:{identity}: overlapping audit units")
            if any(not character.isspace() for character in text[cursor:start]):
                errors.append(f"source:{identity}: uncovered non-whitespace text")
            cursor = max(cursor, end)
        if any(not character.isspace() for character in text[cursor:]):
            errors.append(f"source:{identity}: uncovered non-whitespace text")

    for identity, requirement in requirements.items():
        references(requirement["unit_ids"], units, f"requirement:{identity}")
        references(requirement["question_ids"], questions, f"requirement:{identity}")
        for unit_id in requirement["unit_ids"]:
            if unit_id in units and identity not in units[unit_id]["requirement_ids"]:
                errors.append(f"requirement:{identity}: missing reverse audit unit reference {unit_id}")

    allowed = {
        "objectives": set(taxonomy["objectives"]),
        "model_structures": {item for group in taxonomy["model_structures"].values() for item in group},
        "capabilities": set(taxonomy["capabilities"]),
    }
    represented = set()
    for identity, question in questions.items():
        for group, values in question["classification"].items():
            for value in values:
                if value not in allowed[group]:
                    errors.append(f"question:{identity}: unknown {group} {value}")
        if not question["classification"]["objectives"] or not question["classification"]["capabilities"]:
            missing.append(f"classification:{identity}")

        def question_refs(refs, label):
            references(refs, requirements, label)
            for req_id in refs:
                if req_id in requirements:
                    if identity not in requirements[req_id]["question_ids"]:
                        errors.append(f"{label}: requirement {req_id} belongs to another question")
                    else:
                        represented.add((identity, req_id))

        for field, fact in question["facts"].items():
            label = f"fact:{identity}.{field}"
            question_refs(fact["requirement_ids"], label)
            if fact["status"] == "specified":
                if not _meaningful(fact["value"]):
                    errors.append(f"{label}: specified value is empty")
                if not fact["requirement_ids"]:
                    errors.append(f"{label}: specified fact has no requirement evidence")
            elif fact["value"] is not None:
                errors.append(f"{label}: unknown/NA/deferred value must be null")
            if fact["status"] == "deferred" and field not in DEFERABLE:
                errors.append(f"{label}: this source condition cannot be deferred to model design")
            for req_id in fact["requirement_ids"]:
                if req_id in requirements and requirements[req_id]["origin"] == "explicit" and fact["status"] != "specified":
                    errors.append(f"{label}: explicit requirement {req_id} cannot be bypassed")
        variables = index(question["variables"], f"variables:{identity}")
        for variable_id, variable in variables.items():
            label = f"variable:{identity}.{variable_id}"
            question_refs(variable["requirement_ids"], label)
            if len(variable["roles"]) > 1 and not _meaningful(variable["role_relation"]):
                errors.append(f"{label}: multiple roles need a relationship explanation")
            if variable["unit"] is not None and not variable["unit"].strip():
                errors.append(f"{label}: unknown unit must be null")
            if variable["status"] == "declared" and not variable["requirement_ids"]:
                errors.append(f"{label}: declared variable has no source requirement")
            for role in variable["roles"]:
                if variable["status"] == "declared" and role in ROLE_FACT:
                    fact = question["facts"][ROLE_FACT[role]]
                    if fact["status"] != "specified":
                        errors.append(f"{label}: declared {role} conflicts with fact status")
        for req_id, requirement in requirements.items():
            if identity not in requirement["question_ids"]:
                continue
            category = requirement["category"]
            if category in question["facts"]:
                fact = question["facts"][category]
                if req_id not in fact["requirement_ids"] or (requirement["origin"] == "explicit" and fact["status"] != "specified"):
                    errors.append(f"requirement:{req_id}: category {category} is not represented by question {identity}")
            if (identity, req_id) not in represented:
                errors.append(f"requirement:{req_id}: no question fact or variable represents it in {identity}")

    graph = {identity: set() for identity in questions}
    edge_keys = set()
    for edge in contract["question_dependencies"]:
        producer, consumer = edge["producer"], edge["consumer"]
        label = f"dependency:{producer}->{consumer}"
        references([producer, consumer], questions, label)
        references(edge["requirement_ids"], requirements, label)
        if producer == consumer:
            errors.append(f"{label}: self dependency")
        key = (producer, consumer, edge["type"], edge["artefact"])
        if key in edge_keys:
            errors.append(f"{label}: duplicate dependency")
        edge_keys.add(key)
        if producer in graph and consumer in graph:
            graph[producer].add(consumer)
        for req_id in edge["requirement_ids"]:
            if req_id in requirements and not {producer, consumer}.intersection(requirements[req_id]["question_ids"]):
                errors.append(f"{label}: requirement {req_id} does not support either question")
    indegree = {identity: 0 for identity in graph}
    for consumers in graph.values():
        for consumer in consumers:
            indegree[consumer] += 1
    ready = [identity for identity, count in indegree.items() if count == 0]
    visited = 0
    while ready:
        producer = ready.pop()
        visited += 1
        for consumer in graph[producer]:
            indegree[consumer] -= 1
            if indegree[consumer] == 0:
                ready.append(consumer)
    if visited != len(graph):
        errors.append("question_dependencies: cycle detected")

    data_groups = {}
    used_sources = set()
    for use in contract["data_uses"]:
        label = f"data_use:{use['id']}"
        references([use["source_id"]], sources, label)
        references([use["question_id"]], questions, label)
        if use["source_id"] in sources and sources[use["source_id"]]["kind"] != "data":
            errors.append(f"{label}: data source must have kind data")
        used_sources.add(use["source_id"])
        # Equal bytes under another source id/path cannot bypass overlap checks.
        if use["source_id"] in sources:
            data_groups.setdefault(sources[use["source_id"]]["sha256"], []).append(use)
        scope = use["scope"]
        if scope["kind"] == "rows" and scope["start"] >= scope["end"]:
            errors.append(f"{label}: row scope must be a nonempty end-exclusive interval")
        if use["independence_declared"] and use["role"] != "validation":
            errors.append(f"{label}: independence declaration belongs to validation role")
        if use["question_id"] in questions and questions[use["question_id"]]["facts"]["data"]["status"] != "specified":
            errors.append(f"{label}: data usage conflicts with question data fact")
    for uses in data_groups.values():
        for calibration in (use for use in uses if use["role"] == "calibration"):
            for validation in (use for use in uses if use["role"] == "validation" and use["independence_declared"]):
                left, right = calibration["scope"], validation["scope"]
                overlap = left["kind"] == "all" or right["kind"] == "all"
                if not overlap:
                    overlap = max(left["start"], right["start"]) < min(left["end"], right["end"])
                if overlap:
                    errors.append("data_uses: overlapping calibration/validation scope cannot declare independence")
    for identity, source in sources.items():
        if source["kind"] == "data" and identity not in used_sources:
            missing.append(f"data_role:{identity}")
    for identity, question in questions.items():
        if question["facts"]["data"]["status"] == "specified" and not any(use["question_id"] == identity for use in contract["data_uses"]):
            missing.append(f"data_usage:{identity}")

    critical = []
    for ambiguity in contract["ambiguities"]:
        identity = ambiguity["id"]
        references(ambiguity["question_ids"], questions, f"ambiguity:{identity}")
        resolution = ambiguity["resolution"]
        if ambiguity["status"] == "unresolved":
            if resolution is not None:
                errors.append(f"ambiguity:{identity}: unresolved ambiguity cannot have a resolution")
            if ambiguity["critical"]:
                critical.append(identity)
        elif resolution is None:
            errors.append(f"ambiguity:{identity}: resolved ambiguity needs a current decision")
        else:
            decision(resolution["decision"], f"ambiguity_decision:{identity}", [identity, resolution["value"]])

    if not texts or not any(text.strip() for text in texts.values()):
        missing.append("statement_sources")
    if not questions:
        missing.append("questions")
    if not requirements:
        missing.append("requirements")
    audit_missing = list(missing)
    result["audit_complete"] = not errors and not audit_missing
    for identity, question in questions.items():
        for field in ("original_system", "direct_goal", "deliverables"):
            if question["facts"][field]["status"] != "specified":
                missing.append(f"freeze_fact:{identity}.{field}")
    missing.extend(f"critical_ambiguity:{identity}" for identity in critical)
    result["freeze_ready"] = result["audit_complete"] and not missing
    freeze = contract["freeze"]
    review_valid = False
    if freeze is not None:
        if contract["status"] != "frozen":
            errors.append("freeze: review record is only valid for frozen status")
        if freeze["semantic_sha256"] != result["semantic_sha256"]:
            errors.append("freeze: semantic digest differs from current contract")
        else:
            review_valid = decision(freeze["decision"], "freeze_decision", [result["semantic_sha256"]])
    if contract["status"] in {"audited", "frozen"} and not result["audit_complete"]:
        errors.append("status: audited/frozen requires complete source, audit and references")
    if contract["status"] == "frozen":
        if not result["freeze_ready"]:
            errors.append("status: frozen requires all freeze gates")
        if freeze is None:
            errors.append("freeze: frozen status has no review record")
    result["frozen"] = contract["status"] == "frozen" and result["freeze_ready"] and review_valid and not errors
    if require_frozen and not result["frozen"]:
        errors.append("required: current frozen problem contract")
    result["valid"] = not errors
    result["missing_gates"] = list(dict.fromkeys(missing))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--require-frozen", action="store_true")
    parser.add_argument("--project-root", type=Path)
    args = parser.parse_args()
    result = validate_problem_contract(args.path, require_frozen=args.require_frozen, project_root=args.project_root)
    emit(result)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
