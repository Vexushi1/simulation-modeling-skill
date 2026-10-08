"""Recompute operation and solver-specific simulation evidence without running MATLAB."""
from __future__ import annotations

import argparse
import csv
import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime_common import ROOT, canonical_digest, contained_path, emit, host_fingerprint, load_document, sha256_file
from validate_environment import _official_function, _path, _time, _version_info, runtime_identity, utc_text, validate_environment
from validate_implementation_profile import record_array, validate_build_spec
from validate_implementation_receipt import same_runtime

OPERATION = "simulink.core_simulation"


def contract():
    return load_document(ROOT / "core/simulation_assurance_contract.yaml")


def source_identities():
    return {name: sha256_file(ROOT / name) for name in contract()["source_files"]}


def finite(value):
    return (type(value) is int and abs(value) <= 2**53) or (type(value) is float and math.isfinite(value))


def numeric_vector(value, label, *, nonempty=True):
    if not isinstance(value, list) or (nonempty and not value) or not all(finite(item) for item in value):
        raise ValueError(label + ": finite native-representable numeric array required")
    return value


def native_value_equal(actual, expected):
    """JSON transports MATLAB doubles; upstream typed bytes remain separately bound."""
    if finite(expected):
        return finite(actual) and actual == expected
    return type(actual) is type(expected) and actual == expected


def native_records_equal(actual, expected):
    return len(actual) == len(expected) and all(isinstance(left, dict) and set(left) == set(right) and all(native_value_equal(left[key], right[key]) for key in right) for left, right in zip(actual, expected))


def validate_run_spec(spec):
    fields = {"schema_version", "model_name", "model_path", "model_sha256", "parameters", "inputs", "outputs", "solver", "start_time", "stop_time", "seed", "metrics", "runtime_class", "warning_policy"}
    if not isinstance(spec, dict) or set(spec) != fields or type(spec["schema_version"]) is not int or spec["schema_version"] != 1 or spec["runtime_class"] != "normal_serial" or spec["warning_policy"] not in {"record", "reject"}:
        raise ValueError("run_spec: exact controlled normal_serial fields required")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,62}", spec["model_name"]):
        raise ValueError("run_spec: invalid model name")
    if not isinstance(spec["model_path"], str) or not re.fullmatch(r"[a-f0-9]{64}", spec["model_sha256"]):
        raise ValueError("run_spec: model file identity required")
    if not finite(spec["start_time"]) or not finite(spec["stop_time"]) or not spec["start_time"] < spec["stop_time"]:
        raise ValueError("run_spec: finite increasing start/stop time required")
    if type(spec["seed"]) is not int or not 0 <= spec["seed"] < 2**32:
        raise ValueError("run_spec: explicit twister integer seed required")
    names = set()
    for item in record_array(spec["parameters"], "run_spec.parameters"):
        if set(item) != {"code_name", "value", "unit"} or not isinstance(item["code_name"], str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,62}", item["code_name"]) or item["code_name"] in names or not finite(item["value"]) or item["unit"] is not None and not isinstance(item["unit"], str):
            raise ValueError("run_spec: finite exact model-workspace parameter required")
        names.add(item["code_name"])
    for label in ("inputs", "outputs"):
        ports = set()
        for item in record_array(spec[label], "run_spec." + label):
            required = {"port", "block_path", "variable_id", "unit"} | ({"time", "values", "interpolation"} if label == "inputs" else set())
            if set(item) != required or type(item["port"]) is not int or item["port"] < 1 or item["port"] in ports or not isinstance(item["variable_id"], str) or not item["variable_id"] or not isinstance(item["block_path"], str) or not item["block_path"].startswith(spec["model_name"] + "/") or item["unit"] is not None and not isinstance(item["unit"], str):
                raise ValueError("run_spec: unique exact root-port binding required")
            ports.add(item["port"])
            if label == "inputs":
                time = numeric_vector(item["time"], "input.time")
                values = numeric_vector(item["values"], "input.values")
                if len(time) < 2 or len(time) != len(values) or any(a >= b for a, b in zip(time, time[1:])) or time[0] > spec["start_time"] or time[-1] < spec["stop_time"] or item["interpolation"] not in {"linear", "zoh"}:
                    raise ValueError("run_spec: complete ordered input time/value coverage and interpolation required")
        if ports != set(range(1, len(ports) + 1)):
            raise ValueError("run_spec: root port sequence must be contiguous")
    solver = spec["solver"]
    if not isinstance(solver, dict) or set(solver) != {"name", "type", "max_step", "min_step", "initial_step", "rel_tol", "abs_tol", "fixed_step", "zero_crossing"} or solver["name"] not in contract()["baseline_solvers"] + contract()["candidate_solvers"] or solver["zero_crossing"] not in {"EnableAll", "DisableAll"}:
        raise ValueError("run_spec: controlled solver required")
    if solver["name"] == "ode4":
        if solver["type"] != "fixed-step" or not finite(solver["fixed_step"]) or solver["fixed_step"] <= 0 or any(solver[key] is not None for key in ("max_step", "min_step", "initial_step", "rel_tol", "abs_tol")):
            raise ValueError("run_spec: fixed-step applicability differs")
        ratio = spec["start_time"] / solver["fixed_step"]
        if not math.isfinite(ratio) or abs(ratio - round(ratio)) > 8 * max(math.ulp(ratio), math.ulp(1.0)):
            raise ValueError("run_spec: fixed-step start time must align with the configured step grid")
    else:
        if solver["type"] != "variable-step" or solver["fixed_step"] is not None or any(not finite(solver[key]) or solver[key] <= 0 for key in ("max_step", "min_step", "initial_step", "rel_tol", "abs_tol")) or solver["min_step"] > solver["initial_step"] or solver["initial_step"] > solver["max_step"]:
            raise ValueError("run_spec: variable-step applicability differs")
    outputs = {item["port"]: item for item in spec["outputs"]}
    metric_ids = set()
    for item in record_array(spec["metrics"], "run_spec.metrics"):
        if set(item) != {"id", "output_port", "statistic", "unit", "lower", "upper", "reason"} or not isinstance(item["id"], str) or not item["id"] or item["id"] in metric_ids or type(item["output_port"]) is not int or item["output_port"] not in outputs or item["unit"] != outputs[item["output_port"]]["unit"] or item["statistic"] not in {"final", "minimum", "maximum"} or all(item[key] is None for key in ("lower", "upper")) or any(item[key] is not None and not finite(item[key]) for key in ("lower", "upper")) or item["lower"] is not None and item["upper"] is not None and item["lower"] > item["upper"] or not isinstance(item["reason"], str) or not item["reason"].strip():
            raise ValueError("run_spec: bounded declared metric required")
        metric_ids.add(item["id"])
    return spec


def _validate_request(request):
    fields = {"schema_version", "run_id", "mode", "channel", "host_fingerprint", "matlab_executable", "output_directory", "sources", "source_identity", "required_functions", "cases", "bindings", "input_identity"}
    if not isinstance(request, dict) or set(request) != fields or type(request["schema_version"]) is not int or request["schema_version"] != 1 or request["mode"] not in {"probe", "primary"} or request["channel"] != "matlab_batch":
        raise ValueError("simulation request exact identity schema differs")
    uuid.UUID(request["run_id"])
    if request["host_fingerprint"] != host_fingerprint() or canonical_digest(request["sources"]) != canonical_digest(source_identities()) or request["source_identity"] != canonical_digest(request["sources"]):
        raise ValueError("simulation source or host identity changed")
    if canonical_digest(request["required_functions"]) != canonical_digest(contract()["required_functions"]) or request["input_identity"] != canonical_digest({key: value for key, value in request.items() if key != "input_identity"}):
        raise ValueError("simulation input identity or native surface differs")
    cases = record_array(request["cases"], "request.cases")
    if not cases or not isinstance(request["bindings"], dict):
        raise ValueError("simulation cases and bindings required")
    for case in cases:
        if set(case) != {"case_id", "expectation", "run_spec", "build_spec", "simulation_timeout", "warning_policy"} or case["expectation"] not in {"success", "error", "early_stop", "no_output"} or case["warning_policy"] not in {"record", "reject"} or not finite(case["simulation_timeout"]) or case["simulation_timeout"] <= 0:
            raise ValueError("simulation case exact schema differs")
        validate_run_spec(case["run_spec"])
        if case["warning_policy"] != case["run_spec"]["warning_policy"]:
            raise ValueError("simulation warning policy differs from protocol")
        validate_build_spec(case["build_spec"])
        if case["run_spec"]["model_name"] != case["build_spec"]["model_name"] or canonical_digest(case["run_spec"]["parameters"]) != canonical_digest(case["build_spec"]["parameters"]):
            raise ValueError("simulation case differs from reviewed model parameters")
    return request


def _read_outputs(directory, actual, spec, run_id):
    """Independently cross-check native MAT numeric fields, JSON and exact CSV exports."""
    import numpy as np
    from scipy.io import loadmat
    from scipy.io.matlab import MatReadError
    data_path = contained_path(directory, actual["data_file"])
    data = load_document(data_path)
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1 or data.get("run_id") != run_id:
        raise ValueError("output JSON identity differs")
    records = record_array(data.get("outputs"), "data.outputs")
    expected = sorted(spec["outputs"], key=lambda item: item["port"])
    if not expected or len(records) != len(expected):
        raise ValueError("required complete output set missing")
    try:
        mat = loadmat(contained_path(directory, actual["mat_file"]), variable_names=["run_id", "output_ports", "output_variables", "output_units", "output_times", "output_values", "saved_time"], squeeze_me=False)
    except (OSError, ValueError, TypeError, IndexError, MatReadError) as error:
        raise ValueError("native MAT numeric output readback failed: " + str(error)) from error
    if not {"run_id", "output_ports", "output_variables", "output_units", "output_times", "output_values", "saved_time"} <= set(mat):
        raise ValueError("native MAT numeric output fields missing")
    if mat["saved_time"].dtype != np.dtype("float64") or mat["saved_time"].reshape(-1).tolist() != actual["saved_time"]:
        raise ValueError("native MAT saved time differs from recorded SimulationOutput.tout")
    text = lambda value: "".join(str(part) for part in value.reshape(-1))
    if text(mat["run_id"]) != run_id or mat["output_ports"].reshape(-1).tolist() != [item["port"] for item in expected]:
        raise ValueError("MAT run or output-port identity differs")
    for key in ("output_variables", "output_units", "output_times", "output_values"):
        if mat[key].shape != (len(expected), 1):
            raise ValueError("MAT output collection shape differs: " + key)
    for index, (item, bound) in enumerate(zip(records, expected)):
        if set(item) != {"port", "block_path", "variable_id", "unit", "observed_unit", "time", "values", "csv_file"} or type(item.get("port")) is not int or any(item[key] != bound[key] for key in ("port", "block_path", "variable_id", "unit")):
            raise ValueError("actual output binding differs")
        time, values = numeric_vector(item["time"], "output.time"), numeric_vector(item["values"], "output.values")
        if len(time) != len(values) or len(time) < 2 or any(a >= b for a, b in zip(time, time[1:])):
            raise ValueError("output time/value shape or order differs")
        if text(mat["output_variables"][index, 0]) != item["variable_id"] or text(mat["output_units"][index, 0]) != (item["unit"] or ""):
            raise ValueError("MAT variable or declared unit differs")
        if mat["output_times"][index, 0].dtype != np.dtype("float64") or mat["output_values"][index, 0].dtype != np.dtype("float64") or mat["output_times"][index, 0].reshape(-1).tolist() != time or mat["output_values"][index, 0].reshape(-1).tolist() != values:
            raise ValueError("MAT numeric values differ from JSON")
        with contained_path(directory, item["csv_file"]).open(newline="", encoding="utf-8-sig") as stream:
            rows = list(csv.reader(stream))
        if len(rows) != len(time) or any(len(row) != 2 for row in rows):
            raise ValueError("CSV exact two-column output shape differs")
        parsed = [[float(value) for value in row] for row in rows]
        if parsed != [list(pair) for pair in zip(time, values)]:
            raise ValueError("CSV numeric values differ from JSON and MAT")
    return records


def assert_case(actual, case, directory, run_id):
    if actual.get("case_id") != case["case_id"] or actual.get("attempted") is not True or actual.get("completed") is not True:
        raise ValueError("simulation case identity or completion differs")
    if actual.get("framework_error"):
        record_array(actual["framework_error"].get("stack"), "framework_error.stack")
        raise ValueError("simulation framework error: " + str(actual["framework_error"].get("message", "unknown")))
    for key in ("warnings", "errors", "functions", "before_parameters", "applied_parameters", "after_parameters", "reopened_parameters", "outputs"):
        record_array(actual.get(key), "case." + key)
    if any(actual.get(key) is not True for key in ("source_unchanged", "owned_model_unchanged", "configuration_restored", "parameters_restored", "reopened", "closed_without_save")):
        raise ValueError("actual model persistence or restoration check failed")
    spec = case["run_spec"]
    expected_before = [{**item, "value": item["value"] - 0.25 if case["case_id"] != "primary" else item["value"], "unit": item["unit"] or "", "class": "Simulink.Parameter"} for item in spec["parameters"]]
    expected_applied = [{**item, "unit": item["unit"] or "", "class": "Simulink.Parameter"} for item in spec["parameters"]]
    if any(not native_records_equal(actual[key], expected_before) for key in ("before_parameters", "after_parameters", "reopened_parameters")) or not native_records_equal(actual["applied_parameters"], expected_applied):
        raise ValueError("actual workspace parameter override or restoration differs")
    owned = contained_path(directory, spec["model_name"] + ".slx")
    if _path(actual.get("model_file", "")) != _path(owned) or not owned.is_file():
        raise ValueError("actual model file differs from the owned copy")
    if _path(actual.get("source_model_file", "")) != _path(spec["model_path"]) or sha256_file(owned) != sha256_file(spec["model_path"]):
        raise ValueError("owned model copy or source path differs from exact baseline")
    returned_mat = contained_path(directory, actual.get("raw_mat_file", ""))
    if actual.get("simulation_returned") is not True or not returned_mat.is_file() or returned_mat.stat().st_size == 0:
        raise ValueError("returned native SimulationOutput was not immediately preserved")
    saved_time = numeric_vector(actual.get("saved_time"), "SimulationOutput.tout", nonempty=False)
    if actual.get("time_source") != "SimulationOutput.tout" or actual.get("stop_event_time") != (saved_time[-1] if saved_time else None):
        raise ValueError("actual stop time is not the saved SimulationOutput.tout terminal time")
    if any(a > b for a, b in zip(saved_time, saved_time[1:])):
        raise ValueError("native saved time order differs")
    if case["expectation"] == "error":
        if actual.get("stop_event") != "DiagnosticError" or "phase_e_missing_runtime_variable" not in actual.get("error_message", "") or not any(item.get("identifier") == "Simulink:Parameters:InvParamSetting" for item in actual["errors"]):
            raise ValueError("controlled missing-variable Gain diagnostic was not observed")
        return {"complete": False, "criteria_satisfied": False, "outputs": [], "metrics": []}
    if case["expectation"] == "early_stop":
        if str(actual.get("stop_event", "")).lower() != "timeout" or actual.get("error_message") != "" or actual["errors"] or not finite(actual.get("stop_event_time")) or actual["stop_event_time"] >= spec["stop_time"] or not any(item.get("identifier") == "Simulink:Commands:SimTimeExceededTimeOut" for item in actual["warnings"]):
            raise ValueError("controlled timeout/early-stop diagnostic was not observed")
        return {"complete": False, "criteria_satisfied": False, "outputs": [], "metrics": []}
    if case["expectation"] == "no_output":
        if actual.get("error_message") != "" or actual["errors"] or actual.get("stop_event") != "ReachedStopTime" or type(actual.get("output_count")) is not int or actual["output_count"] != 0 or not actual.get("output_boundary_error"):
            raise ValueError("required-output negative boundary was not observed")
        return {"complete": False, "criteria_satisfied": False, "outputs": [], "metrics": []}
    if actual.get("simulation_returned") is not True or actual.get("error_message") != "" or actual["errors"] or actual.get("stop_event") != "ReachedStopTime" or not finite(actual.get("stop_event_time")) or abs(actual["stop_event_time"] - spec["stop_time"]) > 1e-10 * max(1, abs(spec["stop_time"])):
        raise ValueError("simulation error or incomplete expected stop")
    if case["warning_policy"] == "reject" and (actual["warnings"] or actual.get("last_warning_message") or actual.get("last_warning_identifier")):
        raise ValueError("protocol warning policy rejects observed diagnostics")
    native_solver = actual.get("requested_solver")
    if not isinstance(native_solver, dict) or set(native_solver) != set(spec["solver"]) or any(not native_value_equal(native_solver[key], spec["solver"][key]) for key in spec["solver"]):
        raise ValueError("actual simulation requested solver differs")
    configured = actual.get("configured_parameters")
    effective = actual.get("effective_configuration")
    if not isinstance(configured, dict) or not isinstance(effective, dict) or not isinstance(actual.get("observed_solver_info"), dict):
        raise ValueError("configured parameters and actual public solver metadata required")
    fields = {"name": "Solver", "type": "SolverType", "max_step": "MaxStep", "min_step": "MinStep", "initial_step": "InitialStep", "rel_tol": "RelTol", "abs_tol": "AbsTol", "fixed_step": "FixedStep", "zero_crossing": "ZeroCrossControl"}
    for key, native in fields.items():
        requested = spec["solver"][key]
        if requested is not None:
            observed = configured.get(native)
            if key == "type":
                requested = {"variable-step": "Variable-step", "fixed-step": "Fixed-step"}[requested]
            if isinstance(requested, str) and observed != requested or finite(requested) and (not finite(observed) or observed != requested):
                raise ValueError("configured simulation API setting differs: " + native)
    if not finite(effective.get("StartTime")) or not finite(effective.get("StopTime")) or effective["StartTime"] != spec["start_time"] or effective["StopTime"] != spec["stop_time"] or effective.get("SimulationMode") != "normal":
        raise ValueError("actual public simulation metadata times or mode differ")
    info = actual["observed_solver_info"]
    if not isinstance(info.get("Type"), str) or not isinstance(info.get("Solver"), str) or not info["Solver"]:
        raise ValueError("actual public solver metadata unassessed: Type/Solver missing")
    if info["Type"].lower() != spec["solver"]["type"] or info["Solver"] != actual.get("observed_solver_name") or effective.get("Solver") != info["Solver"]:
        raise ValueError("actual public solver metadata type/name conflicts with recorded method")
    step_key = "FixedStepSize" if spec["solver"]["name"] == "ode4" else "MaxStepSize"
    requested_step = spec["solver"]["fixed_step"] if step_key == "FixedStepSize" else spec["solver"]["max_step"]
    if not finite(info.get(step_key)):
        raise ValueError("actual public solver metadata unassessed: " + step_key + " missing")
    if info[step_key] != requested_step:
        raise ValueError("actual public solver metadata step differs: " + step_key)
    continuous = any(item["type"] == "Integrator" for item in case["build_spec"]["blocks"])
    if continuous and info["Solver"] != spec["solver"]["name"]:
        raise ValueError("actual continuous solver differs from requested qualified method")
    discrete_method = "FixedStepDiscrete" if spec["solver"]["type"] == "fixed-step" else "VariableStepDiscrete"
    if not continuous and info["Solver"] != discrete_method:
        raise ValueError("actual stateless solver is outside the controlled observed method")
    outputs = _read_outputs(directory, actual, spec, run_id)
    if type(actual.get("output_count")) is not int or actual["output_count"] != len(outputs):
        raise ValueError("actual output count differs")
    tolerance = 1e-10 * max(1, abs(spec["stop_time"]))
    for item in outputs:
        if abs(item["time"][0] - spec["start_time"]) > tolerance or abs(item["time"][-1] - spec["stop_time"]) > tolerance:
            raise ValueError("required output time interval incomplete")
        actual_output_step = max(b - a for a, b in zip(item["time"], item["time"][1:]))
        limit = spec["solver"]["fixed_step"] if spec["solver"]["name"] == "ode4" else spec["solver"]["max_step"]
        if actual_output_step > limit + 1e-10 * max(1, limit):
            raise ValueError("actual logged output step exceeds configured step limit")
    by_id = {item["port"]: item for item in outputs}
    metrics = []
    for item in spec["metrics"]:
        values = by_id[item["output_port"]]["values"]
        value = values[-1] if item["statistic"] == "final" else min(values) if item["statistic"] == "minimum" else max(values)
        passed = (item["lower"] is None or item["lower"] <= value) and (item["upper"] is None or value <= item["upper"])
        metrics.append({"id": item["id"], "value": value, "passed": passed, "reason": item["reason"]})
    return {"complete": True, "criteria_satisfied": all(item["passed"] for item in metrics), "outputs": outputs, "metrics": metrics}


def observed_runtime(raw, request):
    functions = record_array(raw.get("functions"), "raw.functions")
    names = {item["name"]: item["path"] for item in functions}
    if len(names) != len(functions) or set(names) != set(contract()["required_functions"]) or not all(_official_function(value, raw["runtime"]["matlabroot"]) for value in names.values()):
        raise ValueError("simulation function resolution differs from controlled official surface")
    return runtime_identity({**raw, "operations": [{"operation_id": OPERATION, "functions": functions}]}, request["matlab_executable"])


def derive_profile(raw, request, process):
    _validate_request(request)
    runtime = observed_runtime(raw, request)
    policy = contract()
    records = record_array(raw.get("cases"), "raw.cases")
    if len(records) != len(request["cases"]):
        raise ValueError("simulation raw case count differs")
    results = []
    for case, actual in zip(request["cases"], records):
        errors = []
        try:
            report = assert_case(actual, case, Path(request["output_directory"]), request["run_id"])
            if case["expectation"] == "success" and not report["criteria_satisfied"]:
                raise ValueError("qualification metric criterion failed")
            if case["case_id"].startswith("feedback_"):
                params = {item["code_name"]: item["value"] for item in case["run_spec"]["parameters"]}
                a, b = params["decay_a"], params["forcing_b"]
                signal = report["outputs"][0]
                errors_values = [abs(value - (b/a + (0.25-b/a) * math.exp(-a * time))) for time, value in zip(signal["time"], signal["values"])]
                if max(errors_values) > 2e-5:
                    raise ValueError("qualified feedback trajectory differs from analytic solution")
        except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
            errors.append(str(error))
        results.append({"case_id": case["case_id"], "passed": not errors, "errors": errors})
    by_id = {item["case_id"]: item for item in results}
    common = all(by_id.get(name, {}).get("passed") is True for name in policy["common_cases"])
    solvers = {name: {"qualified": common and by_id.get("feedback_" + name, {}).get("passed") is True, "case_id": "feedback_" + name, "errors": by_id.get("feedback_" + name, {}).get("errors", ["solver case missing"])} for name in policy["baseline_solvers"] + policy["candidate_solvers"]}
    inventory = record_array(raw.get("installed_products"), "raw.installed_products")
    products = {item["Name"]: item for item in inventory}
    target_ok = raw["runtime"]["release"] == policy["target"]["matlab_release"] and products.get("Simulink", {}).get("Version") == policy["target"]["simulink_version"] and set(products) >= {"MATLAB", "Simulink"} and len(products) == len(inventory)
    qualified = target_ok and common and any(item["qualified"] for item in solvers.values()) and raw.get("status") == "completed" and type(raw.get("license_test")) in (int, float) and raw["license_test"] == 1 and process.get("process_state") == "completed" and type(process.get("exit_code")) is int and process["exit_code"] == 0
    return {"schema_version": 1, "run_id": request["run_id"], "captured_at": raw["finished_at"], "valid_until": utc_text(_time(raw["finished_at"]) + timedelta(seconds=policy["validity_seconds"])), "execution": {"channel": "matlab_batch", "host_fingerprint": request["host_fingerprint"], **process}, "runtime": runtime, "sources": request["sources"], "input_identity": request["input_identity"], "operation": {"operation_id": OPERATION, "qualified": bool(qualified), "common_io_qualified": common, "scope": policy["scope"], "solvers": solvers, "case_results": results}}


def validate_evidence_chain(path, *, expected_root=None, now=None):
    directory, policy = Path(path).resolve().parent, contract()
    names = policy["evidence"]
    request, raw, receipt = (load_document(directory / names[key]) for key in ("input", "raw", "profile_receipt" if Path(path).name == names["profile"] else "run_receipt"))
    _validate_request(request)
    if _path(request["output_directory"]) != _path(directory):
        raise ValueError("simulation evidence directory differs")
    for key in ("run_id", "channel", "host_fingerprint", "input_identity", "source_identity"):
        if raw.get(key) != request[key]:
            raise ValueError("simulation raw identity differs: " + key)
    if type(raw.get("schema_version")) is not int or raw["schema_version"] != 1 or raw.get("status") != "completed":
        raise ValueError("simulation raw report did not complete")
    record_array(raw.get("installed_products"), "raw.installed_products")
    record_array(raw.get("licenses_inuse"), "raw.licenses_inuse")
    process = receipt["process"]
    if process.get("process_state") != "completed" or type(process.get("exit_code")) is not int or process["exit_code"] != 0:
        raise ValueError("simulation process did not complete with exit 0")
    if canonical_digest(load_document(directory / names["process"])) != canonical_digest(process):
        raise ValueError("persisted actual process metadata differs")
    times = [_time(process["started_at"]), _time(raw["started_at"]), _time(raw["finished_at"]), _time(process["finished_at"])]
    clock = _time(now) if now is not None else datetime.now(timezone.utc)
    if not times[0] <= times[1] <= times[2] <= times[3] <= clock or times[0] == times[3]:
        raise ValueError("simulation process/raw time order invalid")
    if type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 1 or receipt.get("run_id") != request["run_id"] or canonical_digest(receipt.get("sources")) != canonical_digest(request["sources"]):
        raise ValueError("simulation receipt source or run identity differs")
    if receipt.get("normalization_error"):
        raise ValueError("simulation normalization failed: " + receipt["normalization_error"])
    root = raw["runtime"]["matlabroot"]
    if expected_root is not None and _path(root) != _path(expected_root):
        raise ValueError("simulation runtime root differs")
    release, version = _version_info(root)
    if release != policy["target"]["matlab_release"] or not str(raw["runtime"]["version"]).startswith(version):
        raise ValueError("simulation runtime version identity changed")
    for binding in receipt["artifacts"].values():
        artifact = contained_path(directory, binding["file"])
        if not artifact.is_file() or not artifact.stat().st_size or sha256_file(artifact) != binding["sha256"]:
            raise ValueError("simulation artifact digest differs: " + binding["file"])
    return request, raw, receipt, times


def validate_simulation_profile(profile_path, *, expected_root=None, now=None, require_current=True, required_solver=None):
    result = {"valid": False, "profile_current": False, "simulation_assured": False, "qualified_operations": [], "qualified_solvers": [], "unqualified_solvers": [], "case_results": [], "runtime": None, "profile_sha256": None, "receipt_sha256": None, "errors": []}
    try:
        path = Path(profile_path).resolve()
        names = contract()["evidence"]
        if path.name != names["profile"]:
            raise ValueError("unexpected simulation profile filename")
        request, raw, receipt, times = validate_evidence_chain(path, expected_root=expected_root, now=now)
        if request["mode"] != "probe":
            raise ValueError("only independent simulation probe can qualify profile")
        from probe_simulation import artifact_manifest, qualification_cases
        if canonical_digest(request["cases"]) != canonical_digest(qualification_cases(request["run_id"], Path(request["output_directory"]))) or set(request["bindings"]) != {"environment_profile", "environment_receipt"}:
            raise ValueError("simulation qualification inputs or independent bindings differ")
        binding = request["bindings"]["environment_profile"]
        for item in request["bindings"].values():
            if sha256_file(item["path"]) != item["sha256"]:
                raise ValueError("simulation qualification A binding changed")
        a = validate_environment(binding["path"], expected_root=raw["runtime"]["matlabroot"], now=times[0], expected_host=request["host_fingerprint"])
        if not a["valid"]:
            raise ValueError("simulation qualification did not have current A evidence: " + "; ".join(a["errors"]))
        profile = load_document(path)
        derived = derive_profile(raw, request, receipt["process"])
        qualified = [name for name, item in derived["operation"]["solvers"].items() if item["qualified"]]
        result.update(qualified_solvers=qualified, unqualified_solvers=[name for name in derived["operation"]["solvers"] if name not in qualified], case_results=derived["operation"]["case_results"])
        if canonical_digest(profile) != canonical_digest(derived):
            raise ValueError("declared simulation profile differs from recomputed operation qualification")
        if derived["operation"]["qualified"] is not True:
            failed = [item["case_id"] + ": " + "; ".join(item["errors"]) for item in derived["operation"]["case_results"] if not item["passed"]]
            raise ValueError("simulation operation qualification failed" + (": " + " | ".join(failed) if failed else ": target, license or process gate failed"))
        if not same_runtime(load_document(binding["path"])["runtime"], derived["runtime"]):
            raise ValueError("simulation profile actual runtime differs from its required A qualification")
        if canonical_digest(receipt["artifacts"]) != canonical_digest(artifact_manifest(path.parent, raw, include_profile=True)) or receipt.get("runtime_fingerprint") != derived["runtime"]["fingerprint"]:
            raise ValueError("simulation profile artifact set or runtime identity differs")
        clock = _time(now) if now is not None else datetime.now(timezone.utc)
        current = clock <= _time(profile["valid_until"])
        result.update(qualified_solvers=qualified, unqualified_solvers=[name for name in profile["operation"]["solvers"] if name not in qualified], case_results=profile["operation"]["case_results"], profile_current=current)
        if require_current and not current:
            raise ValueError("simulation profile expired; re-probe before new execution")
        if required_solver is not None and required_solver not in qualified:
            raise ValueError("requested solver has no actual independent qualification: " + required_solver)
        result.update(valid=True, simulation_assured=True, qualified_operations=[OPERATION] + ["simulink.normal_serial." + name for name in qualified], runtime=derived["runtime"], profile_sha256=sha256_file(path), receipt_sha256=sha256_file(path.parent / names["profile_receipt"]))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result["errors"].append(str(error))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--expected-root", type=Path)
    parser.add_argument("--require-solver")
    args = parser.parse_args()
    result = validate_simulation_profile(args.path, expected_root=args.expected_root, required_solver=args.require_solver)
    emit(result)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
