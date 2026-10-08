"""Read-only current-source review and candidate-study checks; never approve C or run MATLAB."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from runtime_common import canonical_digest, emit, load_contract, load_document, schema_errors, sha256_file
from validate_model_contract import validate_model_contract
from validate_parameter_provenance import bind_file, json_value, mathematical_models, model_anchors, same_value

METHODS = {
    "identification.arx_111": "identified",
    "calibration.simulink_gain": "calibrated",
    "optimization.quadratic_sqp": "optimized",
}
CORE_OPERATIONS = ["matlab.basic_execution", "simulink.library_load"]
CRITERIA_FIELDS = ("max_train_rmse", "max_holdout_rmse", "max_condition_number", "feasibility_tolerance")


def semantic_digest(contract):
    return canonical_digest({key: value for key, value in contract.items() if key not in {"status", "review_record"}})


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and (type(value) is float or abs(value) <= 2**53)


def _collect(value, root, label, errors, changed, bound):
    if isinstance(value, dict):
        if "path" in value and "sha256" in value:
            bind_file(root, value, label, errors, changed, bound)
        for key, child in value.items():
            _collect(child, root, f"{label}.{key}", errors, changed, bound)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _collect(child, root, f"{label}.{index}", errors, changed, bound)


def _numeric_basis(reference, expected, sources, source_paths, errors, label):
    if reference is None:
        errors.append(f"{label}: explicit numerical source reference required")
        return
    identity = reference["source_id"]
    if identity not in sources or identity not in source_paths or source_paths[identity] is None:
        errors.append(f"{label}: numerical source is not current")
        return
    try:
        value = load_document(source_paths[identity])
        for part in reference["selector"]:
            if isinstance(value, dict) and type(part) is str and part in value:
                value = value[part]
            elif isinstance(value, list) and type(part) is int and 0 <= part < len(value):
                value = value[part]
            else:
                raise ValueError("selector does not identify a structured value")
        if not isinstance(value, dict) or any(key not in value or not same_value(value[key], actual) for key, actual in expected.items()):
            errors.append(f"{label}: numbers or units differ from their exact source values")
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors.append(f"{label}: {error}")


def _review(contract, root, result, errors, missing, changed, bound):
    binding = contract["review_record"]
    if binding is None:
        missing.append("source_bound_study_review")
        return False
    if contract["status"] != "reviewed":
        errors.append("review: a record requires reviewed status")
    path = bind_file(root, binding, "study_review", errors, changed, bound)
    if path is None:
        return False
    record = load_document(path)
    schema = load_contract("core/parameter_study.schema.yaml")
    problems = schema_errors(record, {"$schema": schema["$schema"], "$defs": schema["$defs"], **schema["$defs"]["review_record"]})
    errors.extend(f"review: {error}" for error in problems)
    if problems:
        return False
    if type(record["schema_version"]) is not int or record["project_id"] != contract["project_id"] or record["study_semantic_sha256"] != result["semantic_sha256"]:
        errors.append("review: project, version or complete study digest differs")
    decision = record["decision"]
    decision_path = bind_file(root, decision, "study_review_decision", errors, changed, bound)
    if decision_path:
        text = decision_path.read_text(encoding="utf-8-sig")
        start, end = decision["start"], decision["end"]
        if start >= end or end > len(text) or text[start:end] != decision["quote"]:
            errors.append("review: exact Unicode review quote differs")
        context = {"project_id": contract["project_id"], "study_semantic_sha256": result["semantic_sha256"],
                   "reviewed_by": decision["reviewed_by"], "action": "review"}
        lines = decision["quote"].splitlines()
        for key, value in context.items():
            if [line for line in lines if line.startswith(f"{key}=")] != [f"{key}={value}"]:
                errors.append(f"review: unique exact context required for {key}")
    return decision_path is not None and not errors


def _data(contract, problem, variables, selection, question_ids, sources, paths, errors, missing):
    method, step = contract["method"], contract["sample_time"]
    if method == "optimization.quadratic_sqp":
        if contract["data"] or step is not None:
            errors.append("optimization: data and sample_time must remain unused")
        return None, None
    if step is None:
        missing.append("explicit_sample_time")
        return None, None
    if not finite(step) or step <= 0:
        errors.append("data: sample_time must be finite and positive")
        return None, None
    selections = contract["data"]
    if sorted(item["role"] for item in selections) != ["holdout", "train"]:
        missing.append("separate_train_and_holdout_data")
        return None, None
    if len({item["id"] for item in selections}) != len(selections):
        errors.append("data: duplicate selection identity")
    input_variable = variables.get(selection["input_variable_id"])
    output_variable = variables.get(selection["output_variable_id"])
    if not input_variable or not output_variable:
        errors.append("data: missing actual C input/output variables")
        return None, None
    uses = {item["id"]: item for item in problem.get("data_uses", [])}
    parsed, ranges = {}, []
    for item in selections:
        identity, label = item["source_id"], f"data:{item['id']}"
        source, path = sources.get(identity), paths.get(identity)
        if source is None or path is None or not source["problem_source_id"]:
            errors.append(f"{label}: current B/C registered data source required")
            continue
        use = uses.get(item["problem_data_use_id"])
        expected_role = "calibration" if item["role"] == "train" else "validation"
        if use is None or use["source_id"] != source["problem_source_id"] or use["role"] != expected_role or use["question_id"] not in question_ids:
            errors.append(f"{label}: role or source differs from the B data use")
            continue
        start, end = item["start"], item["end"]
        if type(start) is not int or type(end) is not int or not 0 <= start < end:
            errors.append(f"{label}: ordered half-open original row range required")
            continue
        scope = use["scope"]
        if scope["kind"] == "rows" and not scope["start"] <= start < end <= scope["end"]:
            errors.append(f"{label}: selection and lag rows leave the approved B range")
        if not same_value(item["units"]["input"], input_variable["unit"]) or not same_value(item["units"]["output"], output_variable["unit"]):
            errors.append(f"{label}: observed units differ from current C")
        if any(value is None or not value.strip() for value in (input_variable["unit"], output_variable["unit"])):
            missing.append("known_observation_units")
        if len(item["weights"]) != end - start or any(not finite(weight) or weight <= 0 for weight in item["weights"]):
            errors.append(f"{label}: positive finite weights for every selected row required")
        if method == "identification.arx_111" and any(weight != 1 for weight in item["weights"]):
            errors.append(f"{label}: ARX [1 1 1] currently supports explicit unit weights only")
        try:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.reader(handle, strict=True))
            if not rows or not rows[0] or len(set(rows[0])) != len(rows[0]):
                raise ValueError("CSV requires unique header names")
            columns = item["columns"]
            if len(set(columns.values())) != 3 or any(name not in rows[0] for name in columns.values()):
                raise ValueError("three distinct declared numeric CSV columns required")
            rows, header = rows[1:], rows[0]
            minimum = 3 if method == "identification.arx_111" else 2
            if end > len(rows) or end - start < minimum:
                raise ValueError("selected original rows are absent or insufficient")
            indexes = {key: header.index(name) for key, name in columns.items()}
            data = {key: [] for key in columns}
            for row in rows[start:end]:
                if len(row) != len(header):
                    raise ValueError("CSV selected row width differs from its header")
                for key, index in indexes.items():
                    value = float(row[index])
                    if not finite(value):
                        raise ValueError("CSV selected cells must be finite real numbers")
                    data[key].append(value)
            times = data["time"]
            for previous, current in zip(times, times[1:]):
                tolerance = 8 * max(math.ulp(previous), math.ulp(current), math.ulp(step))
                if current <= previous or abs(current - previous - step) > tolerance:
                    raise ValueError("declared sample_time differs from the uniform original time grid")
            if method == "calibration.simulink_gain":
                if times[0] < 0 or abs(times[0] - round(times[0] / step) * step) > 8 * max(math.ulp(times[0]), math.ulp(step)):
                    raise ValueError("gain fixed-step start must be nonnegative and aligned with its original grid")
            data["weights"] = item["weights"]
            parsed[item["role"]] = data
            ranges.append((source["sha256"], start, end))
        except (OSError, ValueError, csv.Error, OverflowError) as error:
            errors.append(f"{label}: {error}")
    if len(ranges) == 2 and ranges[0][0] == ranges[1][0] and max(ranges[0][1], ranges[1][1]) < min(ranges[0][2], ranges[1][2]):
        errors.append("data: training and holdout share original rows, including ARX lag rows")
    train, holdout = parsed.get("train"), parsed.get("holdout")
    if train is not None:
        if method == "identification.arx_111":
            import numpy as np
            matrix = np.column_stack((train["output"][:-1], train["input"][:-1]))
            condition = float(np.linalg.cond(matrix))
            if np.linalg.matrix_rank(matrix) != 2 or not math.isfinite(condition):
                errors.append("identifiability: actual ARX lag regressor is rank deficient")
            elif contract["criteria"] and contract["criteria"]["max_condition_number"] is not None and condition > contract["criteria"]["max_condition_number"]:
                errors.append("identifiability: actual ARX lag condition number exceeds its prior criterion")
        elif not any(value != 0 for value in train["input"]):
            errors.append("identifiability: actual gain training input has no excitation")
    return train, holdout


def _kernel(contract, model, problem, question_ids, sources, source_paths, errors, missing):
    method, selection = contract["method"], contract["selection"]
    for field in ("initial_conditions", "boundary_conditions"):
        if model["body"][field]["status"] != "not_applicable":
            missing.append(f"C_condition_not_applicable:{field}")
    variables = {item["id"]: item for item in model["body"]["variables"]}
    relations = {item["id"]: item for item in model["body"]["relations"]}
    relation = relations.get(selection["relation_id"])
    parameters = contract["parameters"]
    expected_count = 2 if method == "identification.arx_111" else 1
    if method == "optimization.quadratic_sqp":
        expected_count = len(parameters)
        if expected_count not in (1, 2):
            missing.append("one_or_two_design_parameters")
    if len(parameters) != expected_count:
        missing.append("complete_ordered_method_parameters")
    parameter_ids = [item["variable_id"] for item in parameters]
    if len(set(parameter_ids)) != len(parameter_ids):
        errors.append("parameters: duplicate C variable reference")
    for parameter in parameters:
        variable = variables.get(parameter["variable_id"])
        label = f"parameter:{parameter['variable_id']}"
        if variable is None or "parameter" not in variable["roles"] or variable["parameter"] is None:
            errors.append(f"{label}: a current C parameter reference is required")
            continue
        original = variable["parameter"]
        if original["provenance"] not in {METHODS[method], "assumed"} or not original["plan"]:
            errors.append(f"{label}: C does not authorize this provenance research role")
        if parameter["role"] != METHODS[method] or parameter["symbol"] != variable["symbol"] or not same_value(parameter["unit"], variable["unit"]):
            errors.append(f"{label}: symbol, unit or method provenance differs from C")
        if parameter["unit"] is None or not parameter["unit"].strip():
            missing.append(f"known_parameter_unit:{parameter['variable_id']}")
        if not parameter["source_ids"] or not set(parameter["source_ids"]) <= set(sources):
            errors.append(f"{label}: explicit current research basis sources required")
        if method == "identification.arx_111":
            if any(parameter[field] is not None for field in ("initial", "lower", "upper", "numerical_basis")):
                errors.append(f"{label}: ARX initial values and bounds are unsupported and must remain null")
        else:
            if any(parameter[field] is None for field in ("initial", "lower", "upper", "numerical_basis")):
                missing.append(f"reviewed_finite_initial_and_bounds:{parameter['variable_id']}")
            elif not all(finite(parameter[field]) for field in ("initial", "lower", "upper")) or not parameter["lower"] < parameter["upper"] or not parameter["lower"] <= parameter["initial"] <= parameter["upper"]:
                errors.append(f"{label}: finite ordered bounds and feasible initialization required")
            else:
                _numeric_basis(parameter["numerical_basis"], {field: parameter[field] for field in ("initial", "lower", "upper", "unit")}, sources, source_paths, errors, label)
    output = variables.get(selection["output_variable_id"])
    input_variable = variables.get(selection["input_variable_id"])
    if relation is None or output is None:
        errors.append("selection: current C relation and output references required")
        return None
    symbols = [item["symbol"] for item in parameters]
    compact = lambda text: "".join(text.split())
    number = lambda value: json.dumps(value, allow_nan=False)
    objective = contract["objective"]
    objective_spec = None
    if method in {"identification.arx_111", "calibration.simulink_gain"}:
        if input_variable is None or len(symbols) != expected_count:
            missing.append("complete_input_parameter_formula")
            return None
        if model["body"]["inputs"] != [input_variable["id"]] or model["body"]["outputs"] != [output["id"]]:
            errors.append("selection: method requires the exact single C input and output")
        y, u = output["symbol"], input_variable["symbol"]
        formula = (f"{y}[k]={symbols[0]}*{y}[k-1]+{symbols[1]}*{u}[k-1]" if method == "identification.arx_111" else f"{y}={symbols[0]}*{u}")
        if compact(relation["expression"]) != formula or relation["role"] not in {"governing", "output"} or set(relation["variable_ids"]) != set(parameter_ids + [input_variable["id"], output["id"]]):
            errors.append("selection: actual C relation differs from the restricted method formula")
        if any(item["id"] != relation["id"] and item["role"] in {"governing", "output", "event", "constraint", "constitutive"} for item in relations.values()):
            errors.append("selection: additional C governing behavior is outside this fixed kernel")
        if objective is not None or selection["constraint_relation_ids"]:
            errors.append("fit: optimization objective and constraint selection must remain unused")
    else:
        if selection["input_variable_id"] is not None or model["body"]["inputs"]:
            errors.append("optimization: a data-free design objective has no input selection")
        if "output" not in output["roles"] or output["unit"] != "1":
            errors.append("optimization: normalized-square objective requires a dimensionless C output")
        if objective is None:
            missing.append("explicit_current_quadratic_objective")
        else:
            terms, constraints = objective["terms"], objective["constraints"]
            if [item["variable_id"] for item in terms] != parameter_ids:
                errors.append("objective: one explicit ordered term per C design parameter required")
            formula_terms = []
            for term, parameter in zip(terms, parameters):
                if not all(finite(term[field]) for field in ("center", "weight", "scale")) or term["weight"] <= 0 or term["scale"] <= 0:
                    errors.append("objective: finite center and positive weight/scale required")
                if not same_value(term["unit"], parameter["unit"]):
                    errors.append("objective: center and scale units differ from the selected parameter")
                _numeric_basis(term["source_ref"], {field: term[field] for field in ("center", "weight", "scale", "unit")}, sources, source_paths, errors, "objective_term")
                formula_terms.append(f"{number(term['weight'])}*(({parameter['symbol']}-({number(term['center'])}))/({number(term['scale'])}))^2")
            if compact(relation["expression"]) != f"{output['symbol']}=" + "+".join(formula_terms) or set(relation["variable_ids"]) != set(parameter_ids + [output["id"]]) or relation["role"] not in {"governing", "output"}:
                errors.append("objective: explicit restricted formula differs from current approved C")
            if [item["relation_id"] for item in constraints] != selection["constraint_relation_ids"]:
                errors.append("constraints: current C selection and linear constraint order differ")
            for constraint in constraints:
                coefficients, rhs = constraint["coefficients"], constraint["rhs"]
                actual = relations.get(constraint["relation_id"])
                if len(coefficients) != len(parameters) or not all(finite(value) for value in coefficients + [rhs]):
                    errors.append("constraints: finite coefficient rows must match parameter dimension")
                    continue
                formula = "+".join(f"{number(value)}*({symbol})" for value, symbol in zip(coefficients, symbols)) + "<=" + number(rhs)
                if actual is None or actual["role"] != "constraint" or compact(actual["expression"]) != formula or set(actual["variable_ids"]) != set(parameter_ids):
                    errors.append("constraints: finite linear formula differs from actual approved C")
                _numeric_basis(constraint["source_ref"], {"coefficients": coefficients, "rhs": rhs}, sources, source_paths, errors, "linear_constraint")
            allowed_relations = {relation["id"]} | set(selection["constraint_relation_ids"])
            if any(item["id"] not in allowed_relations and item["role"] in {"governing", "output", "constraint", "event", "constitutive"} for item in relations.values()):
                errors.append("optimization: additional C relations are outside this quadratic kernel")
            objective_spec = {"centers": [item["center"] for item in terms], "weights": [item["weight"] for item in terms], "scales": [item["scale"] for item in terms], "A": [item["coefficients"] for item in constraints], "b": [item["rhs"] for item in constraints]}
    train, holdout = _data(contract, problem, variables, selection, question_ids, sources, source_paths, errors, missing)
    return {"method": method, "parameter_ids": parameter_ids,
            **{field: None if method == "identification.arx_111" else [item[field] for item in parameters] for field in ("initial", "lower", "upper")},
            "train": train, "holdout": holdout, "sample_time": contract["sample_time"], "objective": objective_spec,
            "budget": contract["budget"], "criteria": {field: contract["criteria"][field] for field in CRITERIA_FIELDS} if contract["criteria"] else None,
            "warning_policy": contract["warning_policy"]}


def validate_parameter_study(path, *, project_root=None, require_reviewed=False):
    result = {"valid": False, "schema_valid": False, "study_ready": False, "reviewed": False,
              "trial_execution_ready": False, "environment_checked": False, "execution_allowed": False,
              "project_id": None, "study_path": None, "study_sha256": None, "semantic_sha256": None,
              "model_path": None, "model_sha256": None, "model_validation": None, "problem_path": None,
              "problem_sha256": None, "approval_path": None, "approval_sha256": None,
              "method": None, "operation_id": None, "native_spec": None, "required_A_operations": [],
              "bound_files": [], "errors": [], "missing_gates": [], "changed_sources": []}
    errors, missing, changed, bound = (result[key] for key in ("errors", "missing_gates", "changed_sources", "bound_files"))
    try:
        path = Path(path).resolve()
        root = Path(project_root).resolve() if project_root is not None else path.parent
        if not path.is_relative_to(root):
            raise ValueError("study path leaves project root")
        contract = load_document(path)
        json_value(contract)
        result.update(study_path=str(path), study_sha256=sha256_file(path))
        errors.extend(schema_errors(contract, load_contract("core/parameter_study.schema.yaml")))
        if type(contract.get("schema_version")) is not int:
            errors.append("schema_version must be the integer 1")
        if errors:
            return result
        method = contract["method"]
        result.update(schema_valid=True, project_id=contract["project_id"], semantic_sha256=semantic_digest(contract),
                      method=method, operation_id=method, required_A_operations=contract["required_A_operations"])
        if not set(CORE_OPERATIONS) <= set(contract["required_A_operations"]):
            missing.append("required_core_A_operations")
        model_path = bind_file(root, contract["model"], "model", errors, changed, bound)
        model_contract, problem, selected_model = None, {}, None
        if model_path:
            model_contract = load_document(model_path)
            report = validate_model_contract(model_path, project_root=root)
            result.update(model_path=str(model_path), model_sha256=sha256_file(model_path), model_validation=report)
            if not report["valid"]:
                errors.extend(f"model: {error}" for error in report["errors"])
            if not report["approved"]:
                missing.append("current_human_model_approval")
            if report["project_id"] != contract["project_id"]:
                errors.append("model: project identity differs from study")
            if report["schema_valid"]:
                anchors = model_anchors(root, model_path, model_contract, report, errors, changed, bound)
                result.update(approval_path=anchors["model_approval_path"], approval_sha256=anchors["model_approval_sha256"])
                problem_path = bind_file(root, model_contract["problem"], "problem", errors, changed, bound)
                if problem_path:
                    result.update(problem_path=str(problem_path), problem_sha256=sha256_file(problem_path))
                    problem = load_document(problem_path)
                    _collect(problem, root, "B", errors, changed, bound)
                _collect(model_contract, root, "C", errors, changed, bound)
        else:
            missing.append("current_human_model_approval")
        selection = contract["selection"]
        if method is None:
            missing.append("selected_supported_method")
        if selection is None or model_contract is None:
            missing.append("selected_current_C_model")
        elif result["model_validation"]["schema_valid"]:
            selected_model = mathematical_models(model_contract).get((selection["design_id"], selection["model_id"]))
            design = next((item for item in model_contract["designs"] if item["id"] == selection["design_id"]), None)
            if selected_model is None or design["main_model"] != selection["model_id"]:
                errors.append("selection: current selected C main model required")
        sources, source_paths = {}, {}
        for source in contract["sources"]:
            if source["id"] in sources:
                errors.append("sources: duplicate identity")
            sources[source["id"]] = source
            source_paths[source["id"]] = bind_file(root, source, f"study_source:{source['id']}", errors, changed, bound)
            for field, records in (("model_source_id", model_contract.get("sources", []) if model_contract else []), ("problem_source_id", problem.get("sources", []))):
                if source[field] is not None:
                    actual = next((item for item in records if item["id"] == source[field]), None)
                    if actual is None or actual["sha256"] != source["sha256"] or source_paths[source["id"]] is None or bind_file(root, actual, f"upstream:{source['id']}:{field}", errors, changed, bound) != source_paths[source["id"]]:
                        errors.append(f"source:{source['id']}: current {field} identity differs")
            if source["model_source_id"] is None:
                errors.append(f"source:{source['id']}: current C source registration required")
        if not sources:
            missing.append("current_study_sources")
        for label in ("budget", "criteria", "warning_policy"):
            if contract[label] is None:
                missing.append(f"explicit_{label}")
        budget, criteria = contract["budget"], contract["criteria"]
        if budget:
            if type(budget["max_iterations"]) is not int or type(budget["max_evaluations"]) is not int or not finite(budget["process_timeout"]):
                errors.append("budget: finite numerical limits and integer iteration/evaluation counts required")
            timeout = budget["simulation_timeout"]
            if method == "calibration.simulink_gain":
                if timeout is None:
                    missing.append("explicit_simulation_timeout")
                elif not finite(timeout) or not 0 < timeout < budget["process_timeout"]:
                    errors.append("budget: per-simulation timeout must be positive and below process timeout")
            elif timeout is not None:
                errors.append("budget: unused simulation_timeout must remain null")
        if criteria:
            used = ({"max_train_rmse", "max_holdout_rmse", "max_condition_number"} if method == "identification.arx_111" else
                    {"max_train_rmse", "max_holdout_rmse", "feasibility_tolerance"} if method == "calibration.simulink_gain" else {"feasibility_tolerance"})
            for field in CRITERIA_FIELDS:
                value = criteria[field]
                if field in used and value is None:
                    missing.append(f"prior_criterion:{field}")
                elif value is not None and (field not in used or not finite(value)):
                    errors.append(f"criteria: unused or nonfinite {field}")
            if not criteria["source_ids"] or not set(criteria["source_ids"]) <= set(sources):
                errors.append("criteria: explicit current threshold basis sources required")
        identifiability = contract["identifiability"]
        if method in {"identification.arx_111", "calibration.simulink_gain"} and identifiability is None:
            missing.append("identifiability_basis_and_limits")
        if identifiability and (not identifiability["source_ids"] or not set(identifiability["source_ids"]) <= set(sources)):
            errors.append("identifiability: explicit current basis sources required")
        spec = _kernel(contract, selected_model, problem, design["question_ids"], sources, source_paths, errors, missing) if method and selected_model else None
        result["study_ready"] = not errors and not missing and spec is not None
        reviewed = _review(contract, root, result, errors, missing, changed, bound)
        if contract["status"] == "reviewed" and (not result["study_ready"] or not reviewed):
            errors.append("status: reviewed requires complete current study and source-bound review")
        if require_reviewed and (contract["status"] != "reviewed" or not reviewed or not result["study_ready"]):
            errors.append("required reviewed gate is not satisfied")
        result.update(valid=not errors, reviewed=reviewed and contract["status"] == "reviewed" and result["study_ready"] and not errors,
                      native_spec=spec if result["study_ready"] and not errors else None)
        result["trial_execution_ready"] = result["valid"] and result["study_ready"] and result["reviewed"]
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        errors.append(str(error))
    result["missing_gates"] = sorted(set(missing))
    result["changed_sources"] = sorted(set(changed))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--require-reviewed", action="store_true")
    args = parser.parse_args()
    report = validate_parameter_study(args.path, project_root=args.project_root, require_reviewed=args.require_reviewed)
    emit(report)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
