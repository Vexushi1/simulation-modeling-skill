"""Qualify actual solver-specific normal-mode simulations in a new evidence directory."""
from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
import uuid

from probe_environment import _matlab_quote, _run_process, write_json
from runtime_common import ROOT, canonical_digest, contained_path, emit, host_fingerprint, load_document, sha256_file
from validate_environment import _path, validate_environment
from validate_implementation_receipt import same_runtime
from validate_simulation_profile import (_validate_request, contract, derive_profile, finite, record_array, source_identities, validate_simulation_profile)


def file_binding(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": sha256_file(path)}


def qualification_cases(run_id, directory):
    suffix = uuid.UUID(run_id).hex[:12]
    directory = Path(directory).resolve()
    def block(model, name, kind, parameters):
        return {"id": name, "path": model + "/" + name, "type": kind, "parameters": parameters}
    def line(source, destination, port=1):
        return {"source": {"block_id": source, "port": 1}, "destination": {"block_id": destination, "port": port}}
    def solver(name):
        fixed = name == "ode4"
        return {"name": name, "type": "fixed-step" if fixed else "variable-step", "max_step": None if fixed else 0.02,
                "min_step": None if fixed else 1e-12, "initial_step": None if fixed else 0.001, "rel_tol": None if fixed else 1e-8,
                "abs_tol": None if fixed else 1e-10, "fixed_step": 0.01 if fixed else None, "zero_crossing": "DisableAll"}
    cases = []
    for identity in contract()["qualification_cases"]:
        model = "q_" + identity + "_" + suffix
        parameters, blocks, connections, inputs, outputs = [], [], [], [], []
        name = identity.removeprefix("feedback_") if identity.startswith("feedback_") else "ode45"
        feedback = identity.startswith("feedback_") or identity in {"invalid_override", "early_stop"}
        if feedback:
            a = 800.0 if name == "ode15s" else 0.4
            parameters = [{"code_name": "decay_a", "value": a, "unit": "1/s"}, {"code_name": "forcing_b", "value": 1.7, "unit": "1/s"}]
            blocks = [block(model, "Input", "Inport", {"Port": "1"}), block(model, "Forcing", "Gain", {"Gain": "forcing_b"}),
                      block(model, "Decay", "Gain", {"Gain": "decay_a"}), block(model, "Balance", "Sum", {"Inputs": "+-"}),
                      block(model, "State", "Integrator", {"InitialCondition": "0.25"}), block(model, "Output", "Outport", {"Port": "1"})]
            connections = [line("Input", "Forcing"), line("Forcing", "Balance"), line("State", "Decay"), line("Decay", "Balance", 2), line("Balance", "State"), line("State", "Output")]
            inputs = [{"port": 1, "block_path": model + "/Input", "variable_id": "u", "unit": "1", "time": [0.0, 2.0], "values": [1.0, 1.0], "interpolation": "zoh"}]
            outputs = [{"port": 1, "block_path": model + "/Output", "variable_id": "x", "unit": "1"}]
        elif identity == "passthrough":
            blocks = [block(model, "Input", "Inport", {"Port": "1"}), block(model, "Output", "Outport", {"Port": "1"})]
            connections = [line("Input", "Output")]
            inputs = [{"port": 1, "block_path": model + "/Input", "variable_id": "u", "unit": None, "time": [0.0, 1.0, 2.0], "values": [0.0, 1.0, 2.0], "interpolation": "linear"}]
            outputs = [{"port": 1, "block_path": model + "/Output", "variable_id": "y", "unit": None}]
        else:
            parameters = [{"code_name": "constant_k", "value": 2.0, "unit": "1"}]
            blocks = [block(model, "Constant", "Constant", {"Value": "constant_k"})]
            if identity != "no_output":
                blocks.append(block(model, "Output", "Outport", {"Port": "1"}))
                connections.append(line("Constant", "Output"))
                outputs.append({"port": 1, "block_path": model + "/Output", "variable_id": "y", "unit": "1"})
            if identity == "multiple_outputs":
                blocks.extend([block(model, "Input", "Inport", {"Port": "1"}), block(model, "InputTwo", "Inport", {"Port": "2"}),
                               block(model, "Gain", "Gain", {"Gain": "constant_k"}), block(model, "OutputTwo", "Outport", {"Port": "2"}),
                               block(model, "OutputThree", "Outport", {"Port": "3"})])
                connections.extend([line("Input", "Gain"), line("Gain", "OutputTwo"), line("InputTwo", "OutputThree")])
                inputs = [{"port": 1, "block_path": model + "/Input", "variable_id": "u", "unit": "1", "time": [0.0, 2.0], "values": [3.0, 3.0], "interpolation": "zoh"},
                          {"port": 2, "block_path": model + "/InputTwo", "variable_id": "v", "unit": "1", "time": [0.0, 2.0], "values": [7.0, 7.0], "interpolation": "zoh"}]
                outputs.extend([{"port": 2, "block_path": model + "/OutputTwo", "variable_id": "z", "unit": "1"}, {"port": 3, "block_path": model + "/OutputThree", "variable_id": "w", "unit": "1"}])
        spec = {"schema_version": 1, "model_name": model, "model_path": str(directory / "qualification-baselines" / (model + ".slx")), "model_sha256": "0" * 64,
                "parameters": parameters, "inputs": inputs, "outputs": outputs, "solver": solver(name), "start_time": 0.0, "stop_time": 2.0,
                "seed": 123, "metrics": [], "runtime_class": "normal_serial", "warning_policy": "record"}
        if identity == "early_stop":
            spec["solver"] = solver("ode4")
            spec["solver"]["fixed_step"] = 1e-9
        for output in outputs:
            output["sample_time"] = 0
            target = (1.7 / parameters[0]["value"] + (0.25 - 1.7 / parameters[0]["value"]) * __import__("math").exp(-parameters[0]["value"] * 2.0)) if feedback else 2.0 if identity in {"constant_no_input", "passthrough"} or output["port"] == 1 else 6.0 if output["port"] == 2 else 7.0
            spec["metrics"].append({"id": "final_" + str(output["port"]), "output_port": output["port"], "statistic": "final", "unit": output["unit"], "lower": target - 2e-5, "upper": target + 2e-5, "reason": "Synthetic infrastructure qualification only; no real-model validity claim."})
        expectation = "error" if identity == "invalid_override" else "early_stop" if identity == "early_stop" else "no_output" if identity == "no_output" else "success"
        build = {"schema_version": 1, "model_name": model, "parameters": parameters, "blocks": blocks, "connections": connections}
        cases.append({"case_id": identity, "expectation": expectation, "run_spec": spec, "build_spec": build, "simulation_timeout": 0.001 if identity == "early_stop" else 30.0, "warning_policy": "record"})
    return cases


def make_request(executable, directory, *, environment_profile, mode="probe", cases=None, bindings=None, run_id=None):
    identity = run_id or str(uuid.uuid4())
    sources = source_identities()
    request = {"schema_version": 1, "run_id": identity, "mode": mode, "channel": "matlab_batch", "host_fingerprint": host_fingerprint(),
               "matlab_executable": str(Path(executable).resolve()), "output_directory": str(Path(directory).resolve()), "sources": sources,
               "source_identity": canonical_digest(sources), "required_functions": contract()["required_functions"],
               "cases": cases if cases is not None else qualification_cases(identity, directory),
               "bindings": bindings if bindings is not None else {"environment_profile": file_binding(environment_profile), "environment_receipt": file_binding(Path(environment_profile).parent / "receipt.json")}}
    request["input_identity"] = canonical_digest(request)
    return request


def execute_request(request, *, timeout=240):
    if not finite(timeout) or timeout <= 0 or any(case["simulation_timeout"] >= timeout for case in request["cases"]):
        raise ValueError("process timeout must exceed every positive simulation wall-clock timeout")
    _validate_request(request)
    if request["mode"] == "probe" and canonical_digest(request["cases"]) != canonical_digest(qualification_cases(request["run_id"], request["output_directory"])):
        raise ValueError("simulation probe must use exact controlled independent cases")
    bindings = request["bindings"]
    for key in ("environment_profile", "environment_receipt"):
        if sha256_file(bindings[key]["path"]) != bindings[key]["sha256"]:
            raise ValueError("current A evidence binding changed")
    required = bindings.get("required_A_operations", [])
    a = validate_environment(bindings["environment_profile"]["path"], required_operations=required)
    ar = load_document(bindings["environment_profile"]["path"])["runtime"]
    if not a["valid"] or _path(request["matlab_executable"]) != _path(ar["executable"]):
        raise ValueError("current independent required A operation evidence and executable required: " + "; ".join(a["errors"]))
    if request["mode"] == "primary":
        from run_simulation import verify_primary_bindings
        verify_primary_bindings(request)
    directory = Path(request["output_directory"])
    directory.mkdir(parents=True, exist_ok=False)
    names = contract()["evidence"]
    write_json(directory / names["input"], request)
    statement = "cd('{}'); run_simulation('{}')".format(_matlab_quote(ROOT / "scripts/matlab"), _matlab_quote(directory / names["input"]))
    command = [request["matlab_executable"], *(["-wait"] if os.name == "nt" else []), "-batch", statement, "-logfile", str(directory / names["log"])]
    process, console = _run_process(command, directory, timeout)
    write_json(directory / names["process"], process)
    if not (directory / names["log"]).exists():
        (directory / names["log"]).write_text(console or "MATLAB produced no logfile; preserved process evidence.\n", encoding="utf-8")
    elif console:
        with (directory / names["log"]).open("a", encoding="utf-8") as stream:
            stream.write("\nRunner console:\n" + console)
    if not (directory / names["raw"]).exists():
        write_json(directory / names["raw"], {"schema_version": 1, "run_id": request["run_id"], "status": "failed", "cases": [], "error": "MATLAB raw report absent; process/log preserved"})
    return process


def artifact_manifest(directory, raw, *, include_profile=False, include_protocol=False):
    directory, names = Path(directory), contract()["evidence"]
    result = {key: {"file": names[key], "sha256": sha256_file(directory / names[key])} for key in ("input", "raw", "process", "log")}
    if include_profile:
        result["profile"] = {"file": names["profile"], "sha256": sha256_file(directory / names["profile"])}
    if include_protocol:
        for key, file in (("protocol_original", "protocol-original.yaml"), ("protocol_snapshot", "protocol-snapshot.json")):
            result[key] = {"file": file, "sha256": sha256_file(directory / file)}
    for actual in record_array(raw.get("cases"), "raw.cases"):
        case_id = actual["case_id"]
        for key in ("model_file", "source_model_file", "raw_mat_file", "mat_file", "data_file"):
            path = actual.get(key)
            if path:
                resolved = Path(path).resolve() if key.endswith("model_file") else contained_path(directory, path)
                if key == "source_model_file" and not resolved.is_relative_to(directory.resolve()):
                    continue  # Project sources are exact external bindings, not run artefacts.
                relative = str(resolved.relative_to(directory.resolve())).replace("\\", "/")
                artifact_key = ({"data_file": "data", "mat_file": "mat", "model_file": "model"}.get(key, key) if case_id == "primary" else case_id + "_" + key)
                result[artifact_key] = {"file": relative, "sha256": sha256_file(resolved)}
        for output in record_array(actual.get("outputs", []), "case.outputs"):
            path = contained_path(directory, output["csv_file"])
            artifact_key = ("csv_" if case_id == "primary" else case_id + "_csv_") + str(output["port"])
            result[artifact_key] = {"file": output["csv_file"], "sha256": sha256_file(path)}
    return result


def probe_simulation(executable, directory, *, environment_profile, timeout=240):
    request = make_request(executable, directory, environment_profile=environment_profile)
    process = execute_request(request, timeout=timeout)
    names, directory = contract()["evidence"], Path(directory)
    raw = load_document(directory / names["raw"])
    try:
        profile = derive_profile(raw, request, process)
        write_json(directory / names["profile"], profile)
        receipt = {"schema_version": 1, "run_id": request["run_id"], "sources": request["sources"], "process": process,
                   "runtime_fingerprint": profile["runtime"]["fingerprint"], "artifacts": artifact_manifest(directory, raw, include_profile=True)}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        write_json(directory / names["profile"], {"schema_version": 1, "run_id": request["run_id"], "qualified": False, "error": str(error)})
        receipt = {"schema_version": 1, "run_id": request["run_id"], "sources": request["sources"], "process": process,
                   "normalization_error": str(error), "artifacts": artifact_manifest(directory, {"cases": []}, include_profile=True)}
    write_json(directory / names["profile_receipt"], receipt)
    result = validate_simulation_profile(directory / names["profile"])
    result["profile_path"] = str((directory / names["profile"]).resolve())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matlab-executable", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--environment-profile", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=240)
    args = parser.parse_args()
    try:
        result = probe_simulation(args.matlab_executable, args.output_dir, environment_profile=args.environment_profile, timeout=args.timeout)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result = {"valid": False, "simulation_assured": False, "qualified_solvers": [], "errors": [str(error)]}
    emit(result)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
