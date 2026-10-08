"""Read-only Phase C design, source, challenge and human-decision checks.

These checks establish declared structure and current evidence bindings, not
mathematical correctness or the authenticity of a recorded human decision.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from runtime_common import canonical_digest, contained_path, emit, load_contract, load_document, schema_errors, sha256_file
from validate_problem_contract import validate_problem_contract

CHALLENGE_FIELDS = (
    "key_mechanisms", "identifiability", "data_support", "dimensionality",
    "implementation_bias", "simpler_equivalent", "hybrid_events", "simscape_need", "executable_vv",
)
STRUCTURE_FIELDS = ("units", "conservation", "causality", "initial_boundary")
STAGES = {"draft": 0, "proposed": 1, "challenged": 2, "approved": 3}
SOLVER_NAMES = {"ode45", "ode15s", "ode23", "ode23s", "ode113", "fmincon", "ga", "lsqnonlin", "fixed-step", "variable-step"}


def semantic_digest(contract: dict) -> str:
    """The approval reference and stage cannot make an approval-digest cycle."""
    return canonical_digest({key: value for key, value in contract.items() if key not in {"status", "approval"}})


def model_identity(model: dict) -> str:
    """Hash declared mathematical structure, without proving equivalence."""
    body = model["body"]
    variables = [{key: item[key] for key in ("id", "symbol", "quantity", "roles", "role_relation", "unit")}
                 for item in body["variables"]]
    for variable in variables:
        variable["roles"] = sorted(variable["roles"])
    relations = [{key: item[key] for key in ("id", "expression", "variable_ids", "role")}
                 for item in body["relations"]]
    assumptions = [{key: item[key] for key in ("id", "meaning", "mathematical_role")}
                   for item in body["assumptions"]]
    for relation in relations:
        relation["variable_ids"] = sorted(relation["variable_ids"])
    mechanisms = [{**item, "relation_ids": sorted(item["relation_ids"])} for item in body["mechanisms"]]
    variables, relations, assumptions, mechanisms = (
        sorted(items, key=lambda item: item["id"]) for items in (variables, relations, assumptions, mechanisms))
    return canonical_digest({"structure": model["structure"], "object": body["object"],
                             "boundary": body["boundary"], "variables": variables,
                             "relations": relations, "inputs": sorted(body["inputs"]), "outputs": sorted(body["outputs"]),
                             "mechanisms": mechanisms, "assumptions": assumptions})


def _identities(contract: dict) -> dict:
    identities = {}
    for design in contract["designs"]:
        for model in design["models"]:
            key = f"{design['id']}.{model['id']}"
            if key in identities:
                raise ValueError(f"duplicate identity key collision: {key}")
            identities[key] = model_identity(model)
    return identities


def expected_locked_spec(contract: dict) -> dict:
    """Return the payload a caller may write only after actual human approval."""
    return {"schema_version": 1, "project_id": contract["project_id"],
            "problem_sha256": contract["problem"]["sha256"],
            "model_semantic_sha256": semantic_digest(contract),
            "model_identities": _identities(contract),
            "design": {key: value for key, value in contract.items() if key not in {"status", "approval"}}}


def _meaningful(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _finite(value) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(_finite(item) for item in value.values())
    if isinstance(value, list):
        return all(_finite(item) for item in value)
    return True


def validate_model_contract(path: Path, *, require_proposed=False, require_challenged=False,
                            require_approved=False, project_root=None, problem_path=None,
                            approval_path=None) -> dict:
    errors, missing, changed = [], [], []
    result = {"schema_valid": False, "valid": False, "proposal_complete": False,
              "challenge_complete": False, "ready_for_approval": False, "approved": False,
              "model_identities": {}, "semantic_sha256": None, "contract_sha256": None,
              "project_id": None, "question_ids": [], "status": None, "problem_path": None,
              "problem_sha256": None, "approval_path": None, "approval_sha256": None,
              "errors": errors, "missing_gates": missing, "changed_sources": changed}
    try:
        path = Path(path).resolve()
        root = Path(project_root).resolve() if project_root is not None else path.parent
        contained_path(root, str(path))
        result["contract_sha256"] = sha256_file(path)
        contract = load_document(path)
        errors.extend(schema_errors(contract, load_contract("core/model_contract.schema.yaml")))
        if not _finite(contract):
            errors.append("contract: non-finite number")
        result["schema_valid"] = not errors
        if errors:
            return result
        result.update(project_id=contract["project_id"], status=contract["status"],
                      semantic_sha256=semantic_digest(contract), model_identities=_identities(contract))
        taxonomy = load_contract("core/capability_taxonomy.yaml")
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError) as error:
        errors.append(f"contract: {error}")
        return result

    def index(items, label):
        indexed = {}
        for item in items:
            if item["id"] in indexed:
                errors.append(f"{label}: duplicate id {item['id']}")
            indexed[item["id"]] = item
        return indexed

    def refs(identities, indexed, label):
        for identity in identities:
            if identity not in indexed:
                errors.append(f"{label}: unknown reference {identity}")

    def bound_file(reference, label, *, document=False, text=False):
        try:
            target = contained_path(root, reference["path"])
            if sha256_file(target) != reference["sha256"]:
                raise ValueError("SHA256 differs from bound bytes")
            if document:
                return target, load_document(target)
            if text:
                return target, target.read_bytes().decode("utf-8-sig")
            return target, None
        except (OSError, ValueError, TypeError, UnicodeError) as error:
            errors.append(f"{label}: {error}")
            if label not in changed:
                changed.append(label)
            return None, None

    problem, problem_report = None, None
    if contract["problem"] is None:
        missing.append("current_frozen_problem")
        if problem_path is not None:
            errors.append("problem: expected path cannot replace a missing contract binding")
    else:
        target, problem = bound_file(contract["problem"], "problem", document=True)
        result["problem_path"] = str(target) if target else None
        result["problem_sha256"] = contract["problem"]["sha256"]
        if target is not None:
            if problem_path is not None and Path(problem_path).resolve() != target:
                errors.append("problem: expected path differs from model binding")
            problem_report = validate_problem_contract(target, project_root=root)
            result["problem_validation"] = problem_report
            if not problem_report["valid"]:
                errors.extend(f"problem: {error}" for error in problem_report["errors"])
                changed.extend(f"problem:{item}" for item in problem_report["changed_sources"])
                problem = None
            elif problem_report["project_id"] != contract["project_id"]:
                errors.append("problem: project_id differs from model contract")
            if not problem_report["frozen"]:
                missing.append("current_frozen_problem")

    sources = index(contract["sources"], "sources")
    problem_sources = {item["id"]: item for item in problem["sources"]} if problem else {}
    questions = {item["id"]: item for item in problem["questions"]} if problem else {}
    requirements = {item["id"]: item for item in problem["requirements"]} if problem else {}
    for identity, source in sources.items():
        target, _ = bound_file(source, f"source:{identity}")
        upstream = source["problem_source_id"]
        if upstream is not None:
            if upstream not in problem_sources:
                errors.append(f"source:{identity}: unknown problem source {upstream}")
            else:
                original = problem_sources[upstream]
                try:
                    if (source["sha256"] != original["sha256"] or
                            target != contained_path(root, original["path"])):
                        errors.append(f"source:{identity}: differs from referenced problem source")
                except ValueError as error:
                    errors.append(f"source:{identity}: {error}")

    if contract["brief"] is None:
        missing.append("approval_brief")
    else:
        _, brief = bound_file(contract["brief"], "brief", text=True)
        if brief is not None and not brief.strip():
            missing.append("approval_brief_content")

    designs = index(contract["designs"], "designs")
    structures = {item for group in taxonomy["model_structures"].values() for item in group}
    covered_questions, covered_requirements, covered_pairs = set(), set(), set()
    all_reviews = []
    for identity, design in designs.items():
        label = f"design:{identity}"
        refs(design["question_ids"], questions, label)
        refs(design["requirement_ids"], requirements, label)
        covered_questions.update(design["question_ids"])
        covered_requirements.update(design["requirement_ids"])
        covered_pairs.update((question, requirement) for question in design["question_ids"]
                             for requirement in design["requirement_ids"])
        for req_id in design["requirement_ids"]:
            if req_id in requirements and not set(requirements[req_id]["question_ids"]) & set(design["question_ids"]):
                errors.append(f"{label}: requirement {req_id} belongs to other questions")
        models = index(design["models"], f"{label}.models")
        identities = [model_identity(model) for model in models.values()]
        if len(set(identities)) != len(identities):
            errors.append(f"{label}: duplicate mathematical identity is not an alternate model")
        main = models.get(design["main_model"])
        if main is None:
            errors.append(f"{label}: main_model is not a candidate model")
        for model_id, model in models.items():
            model_label = f"{label}.{model_id}"
            body = model["body"]
            if model["structure"] not in structures:
                errors.append(f"{model_label}: unknown mathematical structure {model['structure']}")
            if model["name"].strip().casefold() in SOLVER_NAMES:
                errors.append(f"{model_label}: solver name cannot identify a model")
            refs(model["source_ids"], sources, model_label)
            variables = index(body["variables"], f"{model_label}.variables")
            symbols = [variable["symbol"].strip() for variable in variables.values()]
            if len(set(symbols)) != len(symbols):
                errors.append(f"{model_label}: variable symbols must identify distinct declared quantities")
            relations = index(body["relations"], f"{model_label}.relations")
            index(body["mechanisms"], f"{model_label}.mechanisms")
            index(body["assumptions"], f"{model_label}.assumptions")
            index(model["validator_plan"], f"{model_label}.validator_plan")
            used_variables = set()
            for variable_id, variable in variables.items():
                var_label = f"{model_label}.variable:{variable_id}"
                refs(variable["requirement_ids"], requirements, var_label)
                if len(variable["roles"]) > 1 and not _meaningful(variable["role_relation"]):
                    errors.append(f"{var_label}: multiple roles need a relationship explanation")
                if variable["unit"] is not None and not _meaningful(variable["unit"]):
                    errors.append(f"{var_label}: unknown unit must be null")
                if variable["unit"] is None and model is main:
                    missing.append(f"unit:{identity}.{model_id}.{variable_id}")
                parameter = variable["parameter"]
                if "parameter" in variable["roles"]:
                    if parameter is None:
                        errors.append(f"{var_label}: parameter role requires provenance and value/plan")
                    else:
                        refs(parameter["source_ids"], sources, var_label)
                        if parameter["value"] is None and not _meaningful(parameter["plan"]):
                            missing.append(f"parameter_plan:{identity}.{model_id}.{variable_id}")
                        if parameter["value"] is not None and parameter["provenance"] in {"given", "derived"} and not (parameter["source_ids"] or variable["requirement_ids"]):
                            errors.append(f"{var_label}: given/derived parameter value has no source reference")
                        if parameter["value"] is not None and parameter["provenance"] in {"identified", "calibrated", "optimized"} and not parameter["source_ids"]:
                            errors.append(f"{var_label}: an existing estimate requires a current evidence source, not only a future plan")
                        if parameter["provenance"] != "given" and not _meaningful(parameter["plan"]):
                            missing.append(f"parameter_basis:{identity}.{model_id}.{variable_id}")
                elif parameter is not None:
                    errors.append(f"{var_label}: parameter record requires parameter role")
            for relation_id, relation in relations.items():
                refs(relation["variable_ids"], variables, f"{model_label}.relation:{relation_id}")
                refs(relation["requirement_ids"], requirements, f"{model_label}.relation:{relation_id}")
                used_variables.update(relation["variable_ids"])
            for group in ("inputs", "outputs"):
                refs(body[group], variables, f"{model_label}.{group}")
                for variable_id in body[group]:
                    if variable_id in variables:
                        roles = set(variables[variable_id]["roles"])
                        expected = {"commanded_input", "disturbance", "reference"} if group == "inputs" else {"output", "observable", "residual"}
                        if not roles & expected:
                            errors.append(f"{model_label}.{group}: {variable_id} has incompatible roles")
            for item in body["mechanisms"] + body["assumptions"]:
                refs(item["relation_ids"], relations, f"{model_label}.{item['id']}")
            for field in ("initial_conditions", "boundary_conditions"):
                condition = body[field]
                refs(condition["requirement_ids"], requirements, f"{model_label}.{field}")
                if condition["status"] == "specified" and not _meaningful(condition["value"]):
                    errors.append(f"{model_label}.{field}: specified condition is empty")
                if condition["status"] != "specified" and condition["value"] is not None:
                    errors.append(f"{model_label}.{field}: unknown/not-applicable value must be null")
                applicable = {req_id for req_id in design["requirement_ids"] if req_id in requirements and requirements[req_id]["category"] == field and requirements[req_id]["origin"] == "explicit"}
                if model is main and applicable and (condition["status"] != "specified" or not applicable <= set(condition["requirement_ids"])):
                    errors.append(f"{model_label}.{field}: explicit problem conditions must be represented")
            for review_field, review in model["structure_review"].items():
                refs(review["source_ids"], sources, f"{model_label}.structure_review:{review_field}")
                if model is main:
                    all_reviews.append((f"{identity}.{model_id}.{review_field}", review))
            for plan in model["validator_plan"]:
                refs(plan["source_ids"], sources, f"{model_label}.validator_plan:{plan['id']}")
            if model is main:
                if not variables or not relations or not body["outputs"]:
                    missing.append(f"mathematical_body:{identity}.{model_id}")
                if not any(relation["role"] in {"governing", "constitutive"} for relation in relations.values()):
                    missing.append(f"governing_relation:{identity}.{model_id}")
                if set(variables) - used_variables:
                    missing.append(f"variable_closure:{identity}.{model_id}")
                if not model["validator_plan"]:
                    missing.append(f"validator_plan:{identity}.{model_id}")
        for field, review in design["challenge"].items():
            refs(review["source_ids"], sources, f"{label}.challenge:{field}")
            all_reviews.append((f"{identity}.{field}", review))

    result["question_ids"] = sorted(covered_questions)
    if not designs:
        missing.append("model_designs")
    if questions.keys() - covered_questions:
        missing.append("question_coverage")
    if requirements.keys() - covered_requirements:
        missing.append("requirement_coverage")
    if any((question, req_id) not in covered_pairs for req_id, requirement in requirements.items()
           for question in requirement["question_ids"]):
        missing.append("question_requirement_coverage")
    result["proposal_complete"] = not errors and not missing
    pending = [label for label, review in all_reviews if review["status"] == "pending"]
    blocked = [label for label, review in all_reviews if review["status"] == "blocked"]
    result["challenge_complete"] = result["proposal_complete"] and not pending
    result["ready_for_approval"] = result["challenge_complete"] and not blocked
    missing.extend(f"challenge_pending:{label}" for label in pending)
    missing.extend(f"challenge_blocked:{label}" for label in blocked)

    approval_valid = False
    binding = contract["approval"]
    if binding is None:
        if approval_path is not None:
            errors.append("approval: expected path cannot replace a missing contract binding")
    else:
        target, approval = bound_file(binding, "approval", document=True)
        result["approval_path"] = str(target) if target else None
        result["approval_sha256"] = binding["sha256"]
        if contract["status"] != "approved":
            errors.append("approval: a current approval binding requires approved status")
        if target is not None:
            if approval_path is not None and Path(approval_path).resolve() != target:
                errors.append("approval: expected path differs from model binding")
            approval_errors = schema_errors(approval, load_contract("core/model_approval_contract.yaml"))
            errors.extend(f"approval: {error}" for error in approval_errors)
            if not approval_errors:
                expected = {"project_id": contract["project_id"],
                            "problem_sha256": result["problem_sha256"],
                            "model_semantic_sha256": result["semantic_sha256"]}
                for field, value in expected.items():
                    if approval[field] != value:
                        errors.append(f"approval: {field} differs from current design")
                decision = approval["decision"]
                _, text = bound_file(decision, "approval_decision", text=True)
                if text is not None:
                    start, end = decision["start"], decision["end"]
                    if start >= end or end > len(text) or text[start:end] != decision["quote"]:
                        errors.append("approval_decision: quote differs from Unicode codepoint slice")
                    # Whole contextual lines prevent a rejection sentence mentioning
                    # the string action=approve from passing a substring test.
                    lines = decision["quote"].splitlines()
                    for field, value in {**expected, "actor": decision["actor"], "action": "approve"}.items():
                        contextual = [line for line in lines if line.startswith(f"{field}=")]
                        if contextual != [f"{field}={value}"]:
                            errors.append(f"approval_decision: exact unique context line required for {field}")
                _, locked = bound_file(approval["locked_model_spec"], "locked_model_spec", document=True)
                if locked is not None:
                    try:
                        if (contract["problem"] is None or
                                canonical_digest(locked) != canonical_digest(expected_locked_spec(contract))):
                            errors.append("locked_model_spec: differs from complete current design payload")
                    except (TypeError, ValueError, RecursionError) as error:
                        errors.append(f"locked_model_spec: invalid canonical payload: {error}")
                approval_valid = not errors

    status = contract["status"]
    if STAGES[status] >= 1 and not result["proposal_complete"]:
        errors.append("status: proposed/challenged/approved requires a complete current proposal")
    if STAGES[status] >= 2 and not result["challenge_complete"]:
        errors.append("status: challenged/approved requires all design reviews without pending items")
    if status == "approved" and not result["ready_for_approval"]:
        errors.append("status: approved requires no blocked material challenge")
    if status == "approved" and binding is None:
        errors.append("approval: approved status has no external human decision binding")
    result["approved"] = status == "approved" and result["ready_for_approval"] and approval_valid and not errors
    for required, minimum, label in ((require_proposed, 1, "proposed"), (require_challenged, 2, "challenged"), (require_approved, 3, "approved")):
        gate = result[{1: "proposal_complete", 2: "challenge_complete", 3: "approved"}[minimum]]
        if required and (STAGES[status] < minimum or not gate):
            errors.append(f"required: current {label} model contract")
    if not result["approved"]:
        missing.append("human_model_approval")
    result["valid"] = not errors
    result["missing_gates"] = list(dict.fromkeys(missing))
    result["changed_sources"] = list(dict.fromkeys(changed))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--problem", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--require-proposed", action="store_true")
    parser.add_argument("--require-challenged", action="store_true")
    parser.add_argument("--require-approved", action="store_true")
    args = parser.parse_args()
    result = validate_model_contract(args.path, project_root=args.project_root, problem_path=args.problem,
                                     approval_path=args.approval, require_proposed=args.require_proposed,
                                     require_challenged=args.require_challenged, require_approved=args.require_approved)
    emit(result)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
