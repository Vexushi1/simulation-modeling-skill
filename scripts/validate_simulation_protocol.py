"""Read-only Phase E protocol, upstream identity and source-bound freeze checks.

This consumer does not probe MATLAB, freeze a protocol, approve a mathematical
model, simulate, accept evidence or change project state.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from runtime_common import canonical_digest, contained_path, emit, load_contract, load_document, schema_errors, sha256_file
from validate_domain_mapping import finite_scalar, validate_domain_mapping
from validate_parameter_provenance import bind_file, json_value, mathematical_models, same_value
from validate_problem_contract import validate_problem_contract

CORE_OPERATIONS = ("matlab.basic_execution", "simulink.library_load")
SOLVER_FIELDS = ("name", "type", "max_step", "min_step", "initial_step", "rel_tol", "abs_tol", "fixed_step", "zero_crossing")
DEFERRED_CLASSIFICATIONS = ("dae", "events", "algebraic_loop", "multirate", "real_time_codegen")


def semantic_digest(contract):
    """Freeze references and status cannot form a digest cycle."""
    return canonical_digest({key: value for key, value in contract.items() if key not in {"status", "freeze_record"}})


def selected_value(value, selector):
    """Select structured data only; never interpret expressions or field text."""
    for part in selector:
        if isinstance(value, dict) and type(part) is str and part in value:
            value = value[part]
        elif isinstance(value, list) and type(part) is int and 0 <= part < len(value):
            value = value[part]
        else:
            raise ValueError("source selector does not identify a structured value")
    return value


def _collect_bindings(value, root, label, errors, changed, bound):
    """Capture the transitive B/C task files that their consumers already review."""
    if isinstance(value, dict):
        if "path" in value and "sha256" in value:
            bind_file(root, value, label, errors, changed, bound)
        for key, item in value.items():
            _collect_bindings(item, root, f"{label}.{key}", errors, changed, bound)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _collect_bindings(item, root, f"{label}.{index}", errors, changed, bound)


def _check_solver(solver, time, spec, errors, missing):
    if solver is None:
        missing.append("solver_decision")
        return
    fixed = solver["name"] == "ode4"
    if solver["type"] != ("fixed-step" if fixed else "variable-step"):
        errors.append("solver: name and type disagree")
    applicable = ("fixed_step",) if fixed else ("max_step", "min_step", "initial_step", "rel_tol", "abs_tol")
    for key in ("max_step", "min_step", "initial_step", "rel_tol", "abs_tol", "fixed_step"):
        value = solver[key]
        if key not in applicable:
            if value is not None:
                errors.append(f"solver: {key} is not applicable to {solver['type']}")
        elif value is None:
            missing.append(f"solver_value:{key}")
        elif not finite_scalar(value) or value <= 0:
            errors.append(f"solver: {key} must be a supported finite positive scalar")
    if not fixed and all(solver[key] is not None and finite_scalar(solver[key]) for key in ("max_step", "min_step", "initial_step")):
        if not solver["min_step"] <= solver["initial_step"] <= solver["max_step"]:
            errors.append("solver: minimum/initial/maximum step order is invalid")
    if time and time["stop"] > time["start"]:
        span = time["stop"] - time["start"]
        key = "fixed_step" if fixed else "initial_step"
        if solver[key] is not None and finite_scalar(solver[key]) and solver[key] > span:
            errors.append(f"solver: {key} exceeds the run interval")
    if (fixed and time and finite_scalar(time["start"]) and
            finite_scalar(solver["fixed_step"]) and solver["fixed_step"] > 0):
        ratio = time["start"] / solver["fixed_step"]
        if (not math.isfinite(ratio) or
                abs(ratio - round(ratio)) > 8 * max(math.ulp(ratio), math.ulp(1.0))):
            errors.append("solver: fixed-step start time must be an integer multiple of fixed_step within floating representation tolerance")
    classification = solver["classification"]
    missing.extend(f"simulation_classification_deferred:{key}" for key in DEFERRED_CLASSIFICATIONS if classification[key])
    if classification["stiffness"] == "unknown":
        missing.append("solver_stiffness_review")
    if classification["dynamics"] == "discrete":
        missing.append("simulation_classification_deferred:discrete")
    if spec:
        has_states = any(block["type"] == "Integrator" for block in spec["blocks"])
        expected = "continuous" if has_states else "algebraic"
        if classification["dynamics"] != expected:
            errors.append("solver: dynamics classification differs from the controlled D structure")
        if not has_states and classification["stiffness"] != "not_applicable":
            errors.append("solver: stiffness is not applicable to this stateless core target")


def _normal_input(data, time, label, errors, missing):
    if data is None:
        missing.append(f"input_data:{label}")
        return None
    if data["kind"] == "constant":
        if data["time"] or data["values"] or data["interpolation"] != "zoh":
            errors.append(f"{label}: constant input uses value, empty sample arrays and zoh")
        if not finite_scalar(data["value"]):
            missing.append(f"known_constant_input:{label}")
            return None
        return {"time": [time["start"], time["stop"]], "values": [data["value"], data["value"]], "interpolation": "zoh"} if time else None
    times, values = data["time"], data["values"]
    if data["value"] is not None:
        errors.append(f"{label}: sampled input cannot also declare a constant value")
    if len(times) < 2 or len(times) != len(values):
        missing.append(f"complete_sampled_input:{label}")
        return None
    if not all(finite_scalar(item) for item in times + values):
        errors.append(f"{label}: time/value data must be finite supported scalar doubles")
        return None
    if any(left >= right for left, right in zip(times, times[1:])):
        errors.append(f"{label}: sample times must be strictly increasing")
    if time and (times[0] > time["start"] or times[-1] < time["stop"]):
        missing.append(f"input_interval_coverage:{label}")
    return {"time": times, "values": values, "interpolation": data["interpolation"]}


def _known_input_value(value, variable_id, *, single=False):
    if isinstance(value, dict):
        if variable_id in value:
            return value[variable_id]
        for key in ("inputs", "commanded_inputs", "disturbances"):
            if isinstance(value.get(key), dict) and variable_id in value[key]:
                return value[key][variable_id]
    if single and value is not None and type(value) is not str:
        return value
    return None


def _check_known_input(known, data, label, errors, missing):
    if known is None or data is None:
        return
    if finite_scalar(known):
        if data["kind"] == "constant":
            matches = same_value(known, data["value"])
        else:
            matches = all(same_value(known, value) for value in data["values"])
        if not matches:
            errors.append(f"{label}: input differs from its known approved value")
    elif isinstance(known, dict) and "kind" in known:
        if not same_value(known, data):
            errors.append(f"{label}: input differs from its known approved structured data")
    else:
        missing.append(f"known_input_representation_unsupported:{label}")


def _freeze(contract, root, result, errors, missing, changed, bound):
    binding = contract["freeze_record"]
    if binding is None:
        missing.append("source_bound_protocol_freeze")
        if contract["status"] == "frozen":
            errors.append("freeze: frozen status has no source-bound review record")
        return False
    if contract["status"] != "frozen":
        errors.append("freeze: a freeze record requires frozen status")
    path = bind_file(root, binding, "protocol_freeze", errors, changed, bound)
    if path is None:
        return False
    record = load_document(path)
    schema = load_contract("core/simulation_protocol.schema.yaml")
    freeze_schema = {"$schema": schema["$schema"], "$defs": schema["$defs"], **schema["$defs"]["freeze_record"]}
    problems = schema_errors(record, freeze_schema)
    errors.extend(f"freeze: {error}" for error in problems)
    if problems:
        return False
    if type(record["schema_version"]) is not int or record["project_id"] != contract["project_id"] or record["protocol_semantic_sha256"] != result["semantic_sha256"]:
        errors.append("freeze: project, version or protocol semantic identity differs")
    decision = record["decision"]
    decision_path = bind_file(root, decision, "protocol_freeze_decision", errors, changed, bound)
    if decision_path is not None:
        text = decision_path.read_text(encoding="utf-8-sig")
        start, end = decision["start"], decision["end"]
        if start >= end or end > len(text) or text[start:end] != decision["quote"]:
            errors.append("freeze: review quote differs from Unicode codepoint slice")
        lines = decision["quote"].splitlines()
        context = {"project_id": contract["project_id"], "protocol_semantic_sha256": result["semantic_sha256"],
                   "reviewed_by": decision["reviewed_by"], "action": "freeze"}
        for key, value in context.items():
            if [line for line in lines if line.startswith(f"{key}=")] != [f"{key}={value}"]:
                errors.append(f"freeze: exact unique review context line required for {key}")
    return decision_path is not None and not errors


def validate_simulation_protocol(path, *, project_root=None, require_frozen=False):
    result = {"schema_valid": False, "valid": False, "project_id": None, "status": None,
              "contract_path": None, "contract_sha256": None, "semantic_sha256": None,
              "protocol_complete": False, "frozen": False, "execution_ready": False,
              "environment_checked": False, "execution_allowed": False,
              "mapping_path": None, "mapping_sha256": None, "mapping_validation": None,
              "model_path": None, "model_sha256": None, "approval_path": None, "approval_sha256": None,
              "problem_path": None, "problem_sha256": None, "parameters_path": None, "parameters_sha256": None,
              "native_model_path": None, "native_model_sha256": None,
              "implementation_receipt_path": None, "implementation_receipt_sha256": None,
              "model_identity": None, "design_id": None, "model_id": None, "target_id": None,
              "unknown_parameter_units": [],
              "required_A_operations": [], "selected_operation_id": None, "selected_solver": None, "run_spec": None,
              "run_spec_sha256": None, "bound_files": [], "errors": [], "missing_gates": [], "changed_sources": []}
    errors, missing, changed, bound = result["errors"], result["missing_gates"], result["changed_sources"], result["bound_files"]
    try:
        path = Path(path).resolve()
        root = Path(project_root).resolve() if project_root is not None else path.parent
        if not path.is_relative_to(root):
            raise ValueError("protocol path leaves project root")
        contract = load_document(path)
        json_value(contract)
        result.update(contract_path=str(path), contract_sha256=sha256_file(path))
        errors.extend(schema_errors(contract, load_contract("core/simulation_protocol.schema.yaml")))
        if type(contract.get("schema_version")) is not int:
            errors.append("schema_version must be the integer 1")
        if errors:
            return result
        result.update(schema_valid=True, project_id=contract["project_id"], status=contract["status"],
                      semantic_sha256=semantic_digest(contract), required_A_operations=contract["required_A_operations"])
        if not set(CORE_OPERATIONS) <= set(contract["required_A_operations"]):
            missing.append("required_core_operations")
        mapping_path = bind_file(root, contract["mapping"], "mapping", errors, changed, bound)
        mapping, model, problem, spec, target = None, None, None, None, None
        if mapping_path is None:
            missing.append("current_implementation_ready_mapping")
        else:
            mapping = load_document(mapping_path)
            report = validate_domain_mapping(mapping_path, project_root=root)
            result.update(mapping_path=str(mapping_path), mapping_sha256=sha256_file(mapping_path), mapping_validation=report)
            bound.extend(report["bound_files"])
            if not report["valid"]:
                errors.extend(f"mapping: {error}" for error in report["errors"])
                changed.extend(f"mapping:{item}" for item in report["changed_sources"])
            if report["project_id"] != contract["project_id"]:
                errors.append("mapping: project_id differs from protocol")
            if not report["implementation_ready"]:
                missing.append("current_implementation_ready_mapping")
            spec = report["build_spec"]
            parameter_records = spec["parameters"] if spec else report.get("parameter_validation", {}).get("parameters", [])
            result["unknown_parameter_units"] = [item["code_name"] for item in parameter_records if
                item["unit"] is None or not item["unit"].strip()]
            result.update(model_path=report["model_path"], model_sha256=report["model_sha256"],
                          approval_path=report["model_approval_path"], approval_sha256=report["model_approval_sha256"],
                          parameters_path=report["parameters_path"], parameters_sha256=report["parameters_sha256"],
                          native_model_path=report["native_model_path"], native_model_sha256=report["native_model_sha256"],
                          implementation_receipt_path=report["implementation_path"], implementation_receipt_sha256=report["implementation_sha256"])
            if report["model_path"]:
                model = load_document(report["model_path"])
                _collect_bindings(model, root, "C", errors, changed, bound)
                if model.get("problem"):
                    problem_path = bind_file(root, model["problem"], "problem", errors, changed, bound)
                    if problem_path:
                        problem = load_document(problem_path)
                        problem_report = validate_problem_contract(problem_path, project_root=root, require_frozen=True)
                        result.update(problem_path=str(problem_path), problem_sha256=sha256_file(problem_path), problem_validation=problem_report)
                        if not problem_report["valid"]:
                            errors.extend(f"problem: {error}" for error in problem_report["errors"])
                        _collect_bindings(problem, root, "B", errors, changed, bound)
            if report["implementation_path"]:
                receipt_path = Path(report["implementation_path"])
                receipt = load_document(receipt_path)
                bind_file(root, mapping["implementation"], "implementation_receipt", errors, changed, bound)
                for key, binding in receipt.get("artifacts", {}).items():
                    artifact = contained_path(receipt_path.parent, binding["file"])
                    bind_file(root, {"path": str(artifact), "sha256": binding["sha256"]}, f"D_receipt:{key}", errors, changed, bound)
        parameter_path = bind_file(root, contract["parameter_set"], "parameter_set", errors, changed, bound)
        if parameter_path is None:
            missing.append("exact_approved_parameter_set")
        elif str(parameter_path) != result["parameters_path"] or sha256_file(parameter_path) != result["parameters_sha256"]:
            errors.append("parameter_set: file and exact identity must match the D registry")
        selection = contract["selection"]
        if selection is None:
            missing.append("selected_model_target")
        elif mapping and model:
            target = next((item for item in mapping.get("targets", []) if item["id"] == selection["target_id"]), None)
            if target is None or (target["design_id"], target["model_id"]) != (selection["design_id"], selection["model_id"]):
                errors.append("selection: target and mathematical model differ from D")
                target = None
            selected_model = mathematical_models(model).get((selection["design_id"], selection["model_id"]))
            if selected_model is None:
                errors.append("selection: unknown C model")
            else:
                result.update(design_id=selection["design_id"], model_id=selection["model_id"], target_id=selection["target_id"],
                              model_identity=result["mapping_validation"]["model_validation"]["model_identities"].get(f"{selection['design_id']}.{selection['model_id']}"))
                model = {**model, "selected_model": selected_model}
        selected_model = model.get("selected_model") if model else None
        selected_design = next((item for item in model["designs"] if selection and item["id"] == selection["design_id"]), None) if model else None
        variables = {item["id"]: item for item in selected_model["body"]["variables"]} if selected_model else {}
        requirements = {item["id"]: item for item in problem["requirements"]} if problem else {}
        sources = {item["id"]: item for item in contract["sources"]}
        if len(sources) != len(contract["sources"]):
            errors.append("source IDs must be unique")
        source_paths = {}
        for identity, source in sources.items():
            source_paths[identity] = bind_file(root, source, f"protocol_source:{identity}", errors, changed, bound)
            for name, records in (("model_source_id", model.get("sources", []) if model else []), ("problem_source_id", problem["sources"] if problem else [])):
                if source[name] is not None:
                    upstream = next((item for item in records if item["id"] == source[name]), None)
                    if upstream is None or contained_path(root, upstream["path"]) != source_paths[identity] or upstream["sha256"] != source["sha256"]:
                        errors.append(f"protocol_source:{identity}: {name} differs from its current upstream identity")
        def references(refs, allowed, label):
            if set(refs) - set(allowed):
                errors.append(f"{label}: unknown source or requirement reference")
        scenario = contract["scenario"]
        if scenario is None:
            missing.append("reviewed_scenario")
        else:
            references(scenario["source_ids"], sources, "scenario")
            references(scenario["requirement_ids"], requirements, "scenario")
            if selected_design and set(scenario["requirement_ids"]) - set(selected_design["requirement_ids"]):
                errors.append("scenario: requirement basis belongs outside the selected C design")
            if not scenario["source_ids"] or not scenario["requirement_ids"]:
                missing.append("scenario_source_and_requirement_basis")
        conditions = contract["conditions"]
        if conditions is None:
            missing.append("approved_initial_boundary_conditions")
        elif selected_model:
            for key in ("initial_conditions", "boundary_conditions"):
                expected = selected_model["body"][key]
                if not same_value(conditions[key], expected):
                    errors.append(f"conditions: {key} differs from approved C")
                if expected["status"] == "unknown":
                    missing.append(f"known_approved_condition:{key}")
        time = contract["time"]
        if time is None:
            missing.append("explicit_run_interval")
        else:
            references(time["requirement_ids"], requirements, "time")
            if (not finite_scalar(time["start"]) or not finite_scalar(time["stop"]) or
                    time["start"] >= time["stop"] or not finite_scalar(time["stop"] - time["start"])):
                errors.append("time: finite supported start must precede stop with a finite interval")
            for question in problem["questions"] if problem else []:
                fact = question["facts"]["time_domain"]
                if set(fact["requirement_ids"]) & set(time["requirement_ids"]):
                    known = fact["value"]
                    if isinstance(known, dict) and "start" in known and "stop" in known:
                        if not same_value(time["start"], known["start"]) or not same_value(time["stop"], known["stop"]):
                            errors.append("time: differs from known source time domain")
                        if known.get("unit") is not None and known["unit"] != time["unit"]:
                            errors.append("time: unit differs from known source time domain")
                    elif isinstance(known, list) and len(known) == 2 and all(finite_scalar(item) for item in known):
                        if not same_value(time["start"], known[0]) or not same_value(time["stop"], known[1]):
                            errors.append("time: differs from known source time domain")
                    elif isinstance(known, (dict, list)):
                        missing.append("known_time_domain_representation_unsupported")
        _check_solver(contract["solver"], time, spec, errors, missing)
        native_inputs, output_index, input_values = [], {}, {}
        blocks = {item["path"]: item for item in spec["blocks"]} if spec else {}
        traces = target["traces"] if target else []
        for field, kind, trace_kind in (("inputs", "Inport", "input"), ("outputs", "Outport", "output")):
            seen_ports, seen_paths = set(), set()
            expected = {item["path"] for item in blocks.values() if item["type"] == kind}
            for item in contract[field]:
                label = f"{field}:{item['port']}"
                block, variable = blocks.get(item["block_path"]), variables.get(item["variable_id"])
                if item["port"] in seen_ports or item["block_path"] in seen_paths:
                    errors.append(f"{label}: duplicate root port/path")
                seen_ports.add(item["port"])
                seen_paths.add(item["block_path"])
                if block is None or block["type"] != kind or int(block["parameters"]["Port"]) != item["port"]:
                    errors.append(f"{label}: root port/path differs from D")
                if variable is None or not selected_model or item["variable_id"] not in selected_model["body"][field]:
                    errors.append(f"{label}: not a declared C {trace_kind}")
                elif not any(trace["kind"] == trace_kind and trace["subject_id"] == item["variable_id"] and trace["disposition"] == "mapped" and block and block["id"] in trace["block_ids"] for trace in traces):
                    errors.append(f"{label}: variable/root port mapping lacks current D trace")
                if variable and not same_value(item["unit"], variable["unit"]):
                    errors.append(f"{label}: unit differs from C")
                if item["unit"] is None or not item["unit"].strip():
                    missing.append(f"known_interface_unit:{label}")
                if field == "outputs":
                    output_index[item["port"]] = item
                    continue
                references(item["requirement_ids"], requirements, label)
                if selected_design and set(item["requirement_ids"]) - set(selected_design["requirement_ids"]):
                    errors.append(f"{label}: requirement basis belongs outside the selected C design")
                if not item["requirement_ids"]:
                    missing.append(f"input_requirement_basis:{label}")
                data = item["data"]
                normal = _normal_input(data, time, label, errors, missing)
                source_ref = item["source_ref"]
                if source_ref is None:
                    missing.append(f"source_bound_input:{label}")
                elif source_ref["source_id"] not in source_paths:
                    errors.append(f"{label}: unknown input source")
                elif source_paths[source_ref["source_id"]] is not None:
                    source_path = source_paths[source_ref["source_id"]]
                    if source_path.suffix.lower() not in {".json", ".yaml", ".yml"}:
                        errors.append(f"{label}: numerical input source must be structured JSON/YAML")
                    elif not same_value(selected_value(load_document(source_path), source_ref["selector"]), data):
                        errors.append(f"{label}: exact input data differs from source selector")
                    if scenario and source_ref["source_id"] not in scenario["source_ids"]:
                        errors.append(f"{label}: input source is outside the reviewed scenario")
                if selected_model:
                    for key in ("initial_conditions", "boundary_conditions"):
                        _check_known_input(_known_input_value(selected_model["body"][key]["value"], item["variable_id"]), data, label, errors, missing)
                    if variable and variable["parameter"] is not None:
                        _check_known_input(variable["parameter"]["value"], data, label, errors, missing)
                for question in problem["questions"] if problem else []:
                    for key in ("commanded_inputs", "disturbances"):
                        fact = question["facts"][key]
                        if set(fact["requirement_ids"]) & set(item["requirement_ids"]):
                            role = "commanded_input" if key == "commanded_inputs" else "disturbance"
                            candidates = [identity for identity in selected_model["body"]["inputs"] if role in variables[identity]["roles"]] if selected_model else []
                            known = _known_input_value(fact["value"], item["variable_id"], single=candidates == [item["variable_id"]])
                            _check_known_input(known, data, label, errors, missing)
                if normal:
                    variable_id = item["variable_id"]
                    if variable_id in input_values and not same_value(normal, input_values[variable_id]):
                        errors.append(f"{label}: repeated approved input variable has inconsistent root-port values")
                    input_values[variable_id] = normal
                    native_inputs.append({**{key: item[key] for key in ("port", "block_path", "variable_id", "unit")}, **normal})
            if expected != seen_paths:
                missing.append(f"complete_root_{field}")
        if not output_index:
            missing.append("at_least_one_root_output")
        for key in ("logging", "seed", "warning_policy"):
            if contract[key] is None:
                missing.append(f"explicit_{key}")
        metric_ids, metric_ports = set(), set()
        for metric in contract["metrics"]:
            if metric["id"] in metric_ids:
                errors.append("metric IDs must be unique")
            metric_ids.add(metric["id"])
            output = output_index.get(metric["output_port"])
            if output is None or not same_value(output["unit"], metric["unit"]):
                errors.append(f"metric:{metric['id']}: output identity/unit differs")
            metric_ports.add(metric["output_port"])
            limits = [metric[key] for key in ("lower", "upper") if metric[key] is not None]
            if not limits:
                missing.append(f"metric_criterion:{metric['id']}")
            elif not all(finite_scalar(value) for value in limits) or (len(limits) == 2 and metric["lower"] > metric["upper"]):
                errors.append(f"metric:{metric['id']}: invalid finite criterion bounds")
        if set(output_index) - metric_ports:
            missing.append("expected_metrics_for_all_outputs")
        result["protocol_complete"] = not errors and not missing
        if result["protocol_complete"] and spec and time:
            run_spec = {"schema_version": 1, "model_name": spec["model_name"], "model_path": result["native_model_path"],
                        "model_sha256": result["native_model_sha256"], "parameters": spec["parameters"],
                        "inputs": sorted(native_inputs, key=lambda item: item["port"]),
                        "outputs": sorted(contract["outputs"], key=lambda item: item["port"]),
                        "solver": {key: contract["solver"][key] for key in SOLVER_FIELDS},
                        "start_time": time["start"], "stop_time": time["stop"], "seed": contract["seed"]["value"],
                        "metrics": contract["metrics"], "runtime_class": contract["runtime_class"], "warning_policy": contract["warning_policy"]["action"]}
            result.update(run_spec=run_spec, run_spec_sha256=canonical_digest(run_spec),
                          selected_operation_id="simulink.core_simulation", selected_solver=contract["solver"]["name"])
        freeze_valid = _freeze(contract, root, result, errors, missing, changed, bound)
        if contract["status"] == "frozen" and not result["protocol_complete"]:
            errors.append("freeze: frozen protocol requires complete current upstream and execution conditions")
        result["frozen"] = contract["status"] == "frozen" and result["protocol_complete"] and freeze_valid and not errors
        if require_frozen and not result["frozen"]:
            errors.append("required: current source-bound frozen simulation protocol")
        result["valid"] = not errors
        result["execution_ready"] = result["valid"] and result["frozen"] and result["protocol_complete"]
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError) as error:
        errors.append(str(error))
    result["bound_files"] = list({(item["path"], item["sha256"]): item for item in bound}.values())
    result["missing_gates"] = sorted(set(missing))
    result["changed_sources"] = sorted(set(changed))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--require-frozen", action="store_true")
    args = parser.parse_args()
    result = validate_simulation_protocol(args.path, project_root=args.project_root, require_frozen=args.require_frozen)
    emit(result)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
