"""Read a finite frozen-E catalog; never create protocols, approvals or state."""
from __future__ import annotations

import argparse
import itertools
import math
from pathlib import Path

from runtime_common import canonical_digest, emit, load_contract, load_document, schema_errors, sha256_file
from validate_domain_mapping import finite_scalar, validate_domain_mapping
from validate_parameter_provenance import bind_file, json_value, same_value
from validate_simulation_protocol import CORE_OPERATIONS, selected_value, validate_simulation_protocol

METHODS = ("scenario_matrix", "full_factorial", "monte_carlo_catalog")


def semantic_digest(design):
    return canonical_digest({key: value for key, value in design.items()
                             if key not in {"status", "review_record"}})


def _review(design, root, result):
    errors, missing, changed, bound = (result[key] for key in
                                      ("errors", "missing_gates", "changed_sources", "bound_files"))
    binding = design["review_record"]
    if binding is None:
        missing.append("source_bound_experiment_review")
        if design["status"] == "reviewed":
            errors.append("reviewed status has no independent review record")
        return False
    if design["status"] != "reviewed":
        errors.append("review record requires reviewed status")
    path = bind_file(root, binding, "experiment_review", errors, changed, bound)
    if path is None:
        return False
    record = load_document(path)
    schema = load_contract("core/experiment_design.schema.yaml")
    problems = schema_errors(record, {"$schema": schema["$schema"], "$defs": schema["$defs"],
                                      **schema["$defs"]["review_record"]})
    errors.extend("review: " + error for error in problems)
    if problems:
        return False
    if (type(record["schema_version"]) is not int or record["project_id"] != design["project_id"]
            or record["experiment_semantic_sha256"] != result["semantic_sha256"]):
        errors.append("review: project/version/semantic identity differs")
    decision = record["decision"]
    decision_path = bind_file(root, decision, "experiment_review_decision", errors, changed, bound)
    if decision_path is None:
        return False
    text = decision_path.read_text(encoding="utf-8-sig")
    start, end = decision["start"], decision["end"]
    if start >= end or end > len(text) or text[start:end] != decision["quote"]:
        errors.append("review: Unicode source slice differs")
    lines = decision["quote"].splitlines()
    context = {"project_id": design["project_id"], "experiment_semantic_sha256": result["semantic_sha256"],
               "reviewed_by": decision["reviewed_by"], "action": "review"}
    for key, value in context.items():
        if [line for line in lines if line.startswith(key + "=")] != [key + "=" + value]:
            errors.append("review: exact unique context line required for " + key)
    return not errors


def _public_configuration(protocol, report, factor_ports):
    spec = report["run_spec"]
    # Only the actual supplied factor VALUES can differ; every other run setting
    # and all other inputs remain exact, including waveform time/interpolation.
    inputs = [{key: value for key, value in item.items()
               if key != "values" or item["port"] not in factor_ports}
              for item in spec["inputs"]]
    return {"run_spec": {**spec, "inputs": inputs},
            "conditions": protocol["conditions"], "logging": protocol["logging"],
            "selection": protocol["selection"]}


def validate_experiment_design(path, *, project_root=None, require_reviewed=False):
    result = {"valid": False, "schema_valid": False, "design_ready": False, "reviewed": False,
              "campaign_execution_ready": False, "environment_checked": False, "execution_allowed": False,
              "contract_path": None, "design_sha256": None, "semantic_sha256": None,
              "project_root": None, "project_id": None, "method": None, "sampling_spec": None,
              "catalog": [], "metric": None, "event": None, "budget": None,
              "mapping_path": None, "mapping_sha256": None, "model_path": None, "model_sha256": None,
              "approval_path": None, "approval_sha256": None, "problem_path": None, "problem_sha256": None,
              "model_identity": None, "bound_files": [], "required_A_operations": [],
              "errors": [], "missing_gates": [], "changed_sources": []}
    errors, missing, changed, bound = (result[key] for key in
                                      ("errors", "missing_gates", "changed_sources", "bound_files"))
    try:
        path = Path(path).resolve()
        root = Path(project_root).resolve() if project_root is not None else path.parent
        if not path.is_relative_to(root):
            raise ValueError("experiment path leaves project root")
        design = load_document(path)
        json_value(design)
        result.update(contract_path=str(path), project_root=str(root), design_sha256=sha256_file(path))
        errors.extend(schema_errors(design, load_contract("core/experiment_design.schema.yaml")))
        if type(design.get("schema_version")) is not int:
            errors.append("schema_version must be integer 1")
        if errors:
            return result
        method = design["method"]
        result.update(schema_valid=True, project_id=design["project_id"], method=method,
                      semantic_sha256=semantic_digest(design), event=design["event"], budget=design["budget"],
                      required_A_operations=list(design["required_A_operations"]))
        if not set(CORE_OPERATIONS) <= set(design["required_A_operations"]):
            missing.append("required_core_operations")
        if method is None:
            missing.append("explicit_catalog_method")
        mapping_path = bind_file(root, design["mapping"], "experiment_mapping", errors, changed, bound)
        mapping_report = None
        if mapping_path is None:
            missing.append("current_implementation_ready_mapping")
        else:
            mapping_report = validate_domain_mapping(mapping_path, project_root=root)
            result.update(mapping_path=str(mapping_path), mapping_sha256=sha256_file(mapping_path))
            bound.extend(mapping_report["bound_files"])
            errors.extend("mapping: " + error for error in mapping_report["errors"])
            changed.extend("mapping:" + value for value in mapping_report["changed_sources"])
            if mapping_report["project_id"] != design["project_id"]:
                errors.append("mapping project differs")
            if not mapping_report["implementation_ready"]:
                missing.append("current_implementation_ready_mapping")
        if design["selection"] is None:
            missing.append("explicit_design_model_target")
        sources = {}
        for source in design["sources"]:
            if source["id"] in sources:
                errors.append("duplicate experiment source id")
            source_path = bind_file(root, source, "experiment_source:" + source["id"], errors, changed, bound)
            sources[source["id"]] = (source, source_path)

        def source_value(reference, role, label, expected):
            if reference is None:
                missing.append("source_bound_" + label)
                return
            entry = sources.get(reference["source_id"])
            if entry is None:
                errors.append(label + ": unknown source id")
                return
            source, source_path = entry
            if source["role"] != role:
                errors.append(label + ": source role differs")
            if source_path is None:
                return
            if source_path.suffix.lower() not in {".json", ".yaml", ".yml"}:
                errors.append(label + ": source must be structured JSON/YAML")
                return
            if not same_value(selected_value(load_document(source_path), reference["selector"]), expected):
                errors.append(label + ": exact source selector differs")

        settings = {key: design[key] for key in ("method", "sample_count", "seed", "metric_id", "event",
                    "budget", "required_A_operations", "claim_limit")}
        source_value(design["settings_source_ref"], "settings", "experiment_settings", settings)
        factors = design["factors"]
        if not 1 <= len(factors) <= 2:
            missing.append("one_or_two_external_input_factors")
        factor_ids, ports, variables = set(), set(), set()
        levels_ready = True
        for factor in factors:
            if factor["id"] in factor_ids:
                errors.append("duplicate factor id")
            factor_ids.add(factor["id"])
            for field, seen in (("input_port", ports), ("variable_id", variables)):
                value = factor[field]
                if value is None:
                    missing.append("known_factor_" + field + ":" + factor["id"])
                elif value in seen:
                    errors.append("duplicate factor " + field)
                seen.add(value)
            if factor["unit"] is None:
                missing.append("known_factor_unit:" + factor["id"])
            levels = factor["levels"]
            if not 2 <= len(levels) <= 4 or any(value is None for value in levels):
                missing.append("complete_factor_levels:" + factor["id"])
                levels_ready = False
            elif not all(finite_scalar(value) for value in levels) or len(set(levels)) != len(levels):
                errors.append("factor levels must be finite distinct scalars")
                levels_ready = False
            source_value(factor["source_ref"], "input_levels", "factor_levels:" + factor["id"],
                         {key: factor[key] for key in ("variable_id", "unit", "levels")})
        rows, ids, protocol_paths, configurations = [], set(), set(), []
        if not design["catalog"]:
            missing.append("finite_frozen_E_catalog")
        for member in design["catalog"]:
            identity = member["id"]
            if identity in ids:
                errors.append("duplicate catalog id")
            ids.add(identity)
            supplied = member["factor_values"]
            if [value["factor_id"] for value in supplied] != [factor["id"] for factor in factors]:
                errors.append(identity + ": factor row identity/order differs")
            values = [value["value"] for value in supplied]
            if any(value is None for value in values):
                missing.append("known_catalog_factor_values:" + identity)
            elif not all(finite_scalar(value) for value in values):
                errors.append(identity + ": factor row must be finite scalars")
            for factor, value in zip(factors, values):
                if value is not None and value not in factor["levels"]:
                    errors.append(identity + ": value not in source-bound factor levels")
            rows.append(tuple(values))
            protocol_path = bind_file(root, member["protocol"], "catalog_protocol:" + identity,
                                      errors, changed, bound)
            item = {"id": identity, "protocol_path": str(protocol_path) if protocol_path else None,
                    "protocol_sha256": sha256_file(protocol_path) if protocol_path else None,
                    "protocol_semantic_sha256": None, "run_spec_sha256": None, "protocol_report": None}
            result["catalog"].append(item)
            if protocol_path is None:
                missing.append("frozen_catalog_protocol:" + identity)
                continue
            if str(protocol_path) in protocol_paths:
                errors.append("duplicate catalog protocol path")
            protocol_paths.add(str(protocol_path))
            report = validate_simulation_protocol(protocol_path, project_root=root)
            item.update(protocol_report=report, protocol_semantic_sha256=report["semantic_sha256"],
                        run_spec_sha256=report["run_spec_sha256"])
            bound.extend(report["bound_files"])
            errors.extend(identity + ": " + error for error in report["errors"])
            changed.extend(identity + ":" + value for value in report["changed_sources"])
            if not report["execution_ready"]:
                missing.append("current_frozen_E_member:" + identity)
            if report["project_id"] != design["project_id"]:
                errors.append(identity + ": protocol project differs")
            if mapping_path and report["mapping_path"] != str(mapping_path):
                errors.append(identity + ": protocol mapping differs")
            selection = design["selection"]
            if selection is not None and any(report[key] != selection[key] for key in selection):
                errors.append(identity + ": protocol design/model/target differs")
            for key in ("model_path", "model_sha256", "approval_path", "approval_sha256",
                        "problem_path", "problem_sha256", "model_identity"):
                if result[key] is None:
                    result[key] = report[key]
                elif not same_value(result[key], report[key]):
                    errors.append(identity + ": upstream binding differs: " + key)
            result["required_A_operations"] = list(dict.fromkeys(result["required_A_operations"]
                                                               + report["required_A_operations"]))
            spec = report["run_spec"]
            if spec is None:
                continue
            protocol = load_document(protocol_path)
            configurations.append(_public_configuration(protocol, report, ports))
            if (spec["solver"]["name"] != "ode4" or spec["solver"]["type"] != "fixed-step"
                    or spec["stop_time"] - spec["start_time"] > 30
                    or (spec["stop_time"] - spec["start_time"]) / spec["solver"]["fixed_step"] > 3000
                    or len(spec["outputs"]) > 2):
                errors.append(identity + ": beyond the bounded fixed-ode4 campaign")
            inputs = {value["port"]: value for value in spec["inputs"]}
            if (any(len(value["time"]) > 301 for value in spec["inputs"])
                    or sum(len(value["time"]) for value in spec["inputs"]) > 602):
                errors.append(identity + ": input samples exceed the bounded catalog surface")
            for factor, value in zip(factors, values):
                inp = inputs.get(factor["input_port"])
                if inp is None:
                    errors.append(identity + ": factor is not an E root input")
                elif (inp["variable_id"] != factor["variable_id"] or not same_value(inp["unit"], factor["unit"])):
                    errors.append(identity + ": factor variable/unit differs from approved input")
                elif value is not None and any(not same_value(observed, value) for observed in inp["values"]):
                    errors.append(identity + ": actual E input is not the declared constant factor level")
            metrics = {value["id"]: value for value in spec["metrics"]}
            metric = metrics.get(design["metric_id"])
            if metric is None:
                missing.append("shared_summary_metric:" + identity)
            elif result["metric"] is None:
                result["metric"] = metric
            elif not same_value(result["metric"], metric):
                errors.append(identity + ": metric definition/limits differ")
        if configurations and any(not same_value(configurations[0], value) for value in configurations[1:]):
            errors.append("catalog public run settings or non-factor inputs differ")
        if levels_ready and factors and all(all(value is not None for value in row) for row in rows):
            expected = list(itertools.product(*(factor["levels"] for factor in factors)))
            if len(set(rows)) != len(rows):
                errors.append("duplicate catalog factor combination")
            if method == "full_factorial" and rows != expected:
                errors.append("full_factorial catalog must equal the ordered complete Cartesian product")
        count = design["sample_count"]
        if count is None:
            missing.append("fixed_sample_count")
        elif type(count) is not int:
            errors.append("sample_count must be an integer")
        elif method in ("scenario_matrix", "full_factorial") and count != len(design["catalog"]):
            errors.append("deterministic sample_count must equal catalog length")
        probabilities, seed = None, None
        if method == "monte_carlo_catalog":
            declaration = design["probabilities"]
            if declaration is None:
                missing.append("source_bound_categorical_probabilities")
            else:
                probabilities = declaration["values"]
                source_value(declaration["source_ref"], "probabilities", "categorical_probabilities",
                             {"catalog_ids": [member["id"] for member in design["catalog"]],
                              **{key: declaration[key] for key in ("values", "role", "reason")}})
                if any(value is None for value in probabilities):
                    missing.append("known_categorical_probabilities")
                elif (len(probabilities) != len(design["catalog"]) or not all(finite_scalar(value)
                      and value >= 0 for value in probabilities) or math.fsum(probabilities) != 1.0):
                    errors.append("catalog probabilities must be finite nonnegative and fsum exactly 1")
            if design["seed"] is None or design["seed"]["value"] is None:
                missing.append("explicit_local_mt19937ar_seed")
            else:
                seed = design["seed"]["value"]
                if type(seed) is not int:
                    errors.append("seed must be an integer")
            if design["event"] is None:
                missing.append("predeclared_MC_event_and_nominal_Wilson")
        elif method in ("scenario_matrix", "full_factorial") and (design["probabilities"] is not None or design["seed"] is not None):
            errors.append("deterministic catalog design has no probabilities or RNG seed")
        event, metric = design["event"], result["metric"]
        if method in ("scenario_matrix", "full_factorial") and event is not None:
            errors.append("deterministic catalog designs require null Monte Carlo event/interval")
        if design["metric_id"] is None:
            missing.append("explicit_summary_metric")
        if event is not None:
            if event["threshold"] is None or event["unit"] is None:
                missing.append("known_event_threshold_and_unit")
            elif not finite_scalar(event["threshold"]):
                errors.append("event threshold must be finite")
            elif metric is not None and not same_value(event["unit"], metric["unit"]):
                errors.append("event unit differs from summary metric")
        budget = design["budget"]
        if budget is None or any(value is None for value in budget.values()):
            missing.append("complete_finite_execution_budget")
        elif (not all(finite_scalar(value) and value > 0 for value in budget.values())
              or type(budget["max_cases"]) is not int or type(budget["max_artifact_bytes"]) is not int
              or (count is not None and budget["max_cases"] < count)
              or budget["member_simulation_timeout"] > budget["member_process_timeout"]):
            errors.append("invalid finite budget or planned cases exceed reviewed limit")
        result["design_ready"] = not errors and not missing
        if result["design_ready"]:
            result["sampling_spec"] = {"method": method, "catalog_ids": [member["id"] for member in design["catalog"]],
                                       "draws": count, "probabilities": probabilities, "seed": seed}
        ready_before_review = result["design_ready"]
        result["reviewed"] = _review(design, root, result)
        if design["status"] == "reviewed" and not ready_before_review:
            errors.append("reviewed experiment requires a complete current catalog design")
        result["campaign_execution_ready"] = ready_before_review and result["reviewed"] and not errors
        if require_reviewed and not result["campaign_execution_ready"]:
            errors.append("complete independent experiment review is required")
        result["valid"] = not errors
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        errors.append(str(error))
    result["missing_gates"] = list(dict.fromkeys(missing))
    unique = {(item["path"], item["sha256"]): item for item in bound}
    result["bound_files"] = list(unique.values())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--require-reviewed", action="store_true")
    args = parser.parse_args()
    result = validate_experiment_design(args.path, project_root=args.project_root, require_reviewed=args.require_reviewed)
    emit(result)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
