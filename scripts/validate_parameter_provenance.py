"""Read-only implementation bindings to a current approved Phase C design."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

from runtime_common import canonical_digest, contained_path, emit, load_contract, load_document, schema_errors, sha256_file
from validate_model_contract import validate_model_contract

MATLAB_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")
MATLAB_KEYWORDS = {"break", "case", "catch", "classdef", "continue", "else", "elseif", "end", "for", "function", "global", "if", "otherwise", "parfor", "persistent", "return", "spmd", "switch", "try", "while", "arguments", "enumeration", "events", "methods", "properties"}


def json_value(value):
    """Preserve JSON types and reject YAML objects, nonfinite values and keys."""
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("non-finite number")
        return
    if type(value) is list:
        for item in value:
            json_value(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            json_value(item)
        return
    raise ValueError("unsupported JSON value or object key type")


def same_value(left, right):
    json_value(left)
    json_value(right)
    return json.dumps(left, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) == json.dumps(right, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def ref_key(reference):
    return tuple(reference[key] for key in ("design_id", "model_id", "variable_id"))


def mathematical_models(contract):
    return {(design["id"], model["id"]): model for design in contract["designs"] for model in design["models"]}


def main_model_keys(contract):
    return {(design["id"], design["main_model"]) for design in contract["designs"]}


def model_variables(contract):
    return {(design_id, model_id, variable["id"]): variable
            for (design_id, model_id), model in mathematical_models(contract).items()
            for variable in model["body"]["variables"]}


def bind_file(root, binding, label, errors, changed, bound_files):
    if binding is None:
        return None
    try:
        path = contained_path(root, binding["path"])
        actual = sha256_file(path)
        if actual != binding["sha256"]:
            errors.append(f"{label}: file SHA differs from binding")
            changed.append(label)
            return None
        bound_files.append({"label": label, "path": str(path), "sha256": actual})
        return path
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors.append(f"{label}: {error}")
        changed.append(label)
        return None


def model_anchors(root, model_path, model, report, errors, changed, bound_files):
    """Expose current C anchors; C's own validator checks their full semantics."""
    result = {"model_path": str(model_path), "model_sha256": sha256_file(model_path),
              "model_semantic_sha256": report.get("semantic_sha256"),
              "model_approval_path": None, "model_approval_sha256": None,
              "locked_model_path": None, "locked_model_sha256": None}
    for label, binding in (("model_approval", model.get("approval")), ("problem", model.get("problem")), ("brief", model.get("brief"))):
        path = bind_file(root, binding, label, errors, changed, bound_files)
        if path and label == "model_approval":
            result.update(model_approval_path=str(path), model_approval_sha256=sha256_file(path))
            approval = load_document(path)
            locked = bind_file(root, approval.get("locked_model_spec"), "locked_model", errors, changed, bound_files)
            if locked:
                result.update(locked_model_path=str(locked), locked_model_sha256=sha256_file(locked))
            bind_file(root, approval.get("decision"), "human_model_decision", errors, changed, bound_files)
    for source in model.get("sources", []):
        bind_file(root, source, f"model_source:{source['id']}", errors, changed, bound_files)
    return result


def validate_parameter_provenance(path, *, project_root=None, require_bound=False):
    result = {"schema_valid": False, "valid": False, "binding_complete": False,
              "parameters_complete": False, "current_model_approved": False,
              "project_id": None, "status": None, "contract_sha256": None, "semantic_sha256": None,
              "model_path": None, "model_sha256": None, "model_semantic_sha256": None,
              "model_approval_path": None, "model_approval_sha256": None,
              "locked_model_path": None, "locked_model_sha256": None,
              "parameters": [], "bound_files": [], "errors": [], "missing_gates": [], "changed_sources": []}
    errors, missing, changed = result["errors"], result["missing_gates"], result["changed_sources"]
    try:
        path = Path(path).resolve()
        root = Path(project_root).resolve() if project_root is not None else path.parent
        if not path.is_relative_to(root):
            raise ValueError("contract path leaves project root")
        contract = load_document(path)
        result["contract_sha256"] = sha256_file(path)
        json_value(contract)
        errors.extend(schema_errors(contract, load_contract("core/parameter_provenance.schema.yaml")))
        if errors:
            return result
        result.update(schema_valid=True, project_id=contract["project_id"], status=contract["status"],
                      semantic_sha256=canonical_digest({key: value for key, value in contract.items() if key != "status"}))
        model = None
        model_path = bind_file(root, contract["model"], "model", errors, changed, result["bound_files"])
        if model_path:
            model = load_document(model_path)
            report = validate_model_contract(model_path, project_root=root)
            result["model_validation"] = report
            if not report["valid"]:
                errors.extend(f"model: {error}" for error in report["errors"])
                changed.extend(f"model:{item}" for item in report["changed_sources"])
            if report["schema_valid"]:
                result.update(model_anchors(root, model_path, model, report, errors, changed, result["bound_files"]))
                if report["project_id"] != contract["project_id"]:
                    errors.append("model: project_id differs from parameter contract")
                result["current_model_approved"] = report["approved"] and report["valid"]
            else:
                model = None
        if not result["current_model_approved"]:
            missing.append("current_human_model_approval")

        variables = model_variables(model) if model else {}
        main_keys = main_model_keys(model) if model else set()
        required = {key for key, variable in variables.items() if key[:2] in main_keys and "parameter" in variable["roles"]}
        registered, names = set(), set()
        for index, parameter in enumerate(contract["parameters"]):
            label = f"parameter:{index}"
            key = ref_key(parameter["reference"])
            if key in registered:
                errors.append(f"{label}: duplicate mathematical parameter reference")
            registered.add(key)
            name = (parameter["scope"]["owner"], parameter["code_name"])
            if name in names:
                errors.append(f"{label}: duplicate code_name in model workspace scope")
            names.add(name)
            if parameter["code_name"] in MATLAB_KEYWORDS or parameter["scope"]["owner"] in MATLAB_KEYWORDS:
                errors.append(f"{label}: MATLAB keyword is not an implementation name")
            uncertainty = parameter["uncertainty"]
            if uncertainty["status"] != "specified" and uncertainty["value"] is not None:
                errors.append(f"{label}: unknown/not-applicable uncertainty must be null")
            if uncertainty["status"] == "specified" and uncertainty["value"] is None:
                errors.append(f"{label}: specified uncertainty needs an actual value")
            variable = variables.get(key)
            if variable is None or "parameter" not in variable["roles"]:
                errors.append(f"{label}: unknown C parameter reference")
                continue
            expected = variable["parameter"]
            for field, value in (("symbol", variable["symbol"]), ("unit", variable["unit"]),
                                 ("value", expected["value"]), ("provenance", expected["provenance"]),
                                 ("source_ids", expected["source_ids"])):
                if not same_value(parameter[field], value):
                    errors.append(f"{label}: {field} differs from current approved C parameter")
        if required - registered:
            missing.append("main_model_parameter_coverage")
        result["parameters"] = contract["parameters"]
        result["binding_complete"] = bool(model) and result["current_model_approved"] and not errors and not missing
        result["parameters_complete"] = result["binding_complete"]
        if contract["status"] == "bound" and not result["binding_complete"]:
            errors.append("status: bound requires complete current approved parameter bindings")
        if require_bound and (contract["status"] != "bound" or not result["binding_complete"]):
            errors.append("required bound gate is not satisfied")
        result["valid"] = not errors
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors.append(str(error))
    result["changed_sources"] = sorted(set(changed))
    result["missing_gates"] = sorted(set(missing))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--require-bound", action="store_true")
    args = parser.parse_args()
    report = validate_parameter_provenance(args.path, project_root=args.project_root, require_bound=args.require_bound)
    emit(report)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
