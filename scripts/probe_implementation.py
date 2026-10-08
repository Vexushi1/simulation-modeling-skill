"""Run the isolated Phase D structure qualification; never run business simulation."""
from __future__ import annotations

import argparse
import copy
import math
from pathlib import Path
import os
import uuid

from probe_environment import _matlab_quote, _run_process, write_json
from runtime_common import ROOT, canonical_digest, emit, host_fingerprint, load_document, sha256_file
from validate_environment import _path
from validate_implementation_profile import (_validate_request, contract, derive_profile, source_identities,
    validate_build_spec, validate_implementation_profile)


def qualification_cases(run_id):
    suffix = uuid.UUID(run_id).hex[:12]
    def block(model, identity, kind, parameters):
        return {"id": identity, "path": model + "/" + identity, "type": kind, "parameters": parameters}
    def line(source, destination, port=1):
        return {"source": {"block_id": source, "port": 1}, "destination": {"block_id": destination, "port": port}}
    static = "native_static_" + suffix
    static_spec = {"schema_version": 1, "model_name": static,
        "parameters": [{"code_name": "gain_k", "value": 2.5, "unit": "1"}, {"code_name": "offset_c", "value": 0.75, "unit": "1"}],
        "blocks": [block(static, "Input", "Inport", {"Port": "1"}), block(static, "Gain", "Gain", {"Gain": "gain_k"}),
                   block(static, "Offset", "Constant", {"Value": "offset_c"}), block(static, "Add", "Sum", {"Inputs": "++"}),
                   block(static, "Output", "Outport", {"Port": "1"})],
        "connections": [line("Input", "Gain"), line("Gain", "Add"), line("Offset", "Add", 2), line("Add", "Output")]}
    feedback = "native_feedback_" + suffix
    feedback_spec = {"schema_version": 1, "model_name": feedback,
        "parameters": [{"code_name": "decay_a", "value": 0.4, "unit": "1/s"}, {"code_name": "forcing_b", "value": 1.7, "unit": "1/s"}],
        "blocks": [block(feedback, "Input", "Inport", {"Port": "1"}), block(feedback, "Forcing", "Gain", {"Gain": "forcing_b"}),
                   block(feedback, "Decay", "Gain", {"Gain": "decay_a"}), block(feedback, "Balance", "Sum", {"Inputs": "+-"}),
                   block(feedback, "State", "Integrator", {"InitialCondition": "0.25"}), block(feedback, "Output", "Outport", {"Port": "1"})],
        "connections": [line("Input", "Forcing"), line("Forcing", "Balance"), line("State", "Decay"), line("Decay", "Balance", 2),
                        line("Balance", "State"), line("State", "Output")]}
    invalid = copy.deepcopy(static_spec)
    invalid["model_name"] = "native_invalid_" + suffix
    for item in invalid["blocks"]:
        item["path"] = invalid["model_name"] + "/" + item["id"]
    invalid["connections"][0]["destination"]["port"] = 99
    return [{"case_id": "static", "expect_failure": False, "build_spec": static_spec},
            {"case_id": "feedback", "expect_failure": False, "build_spec": feedback_spec},
            {"case_id": "invalid_port", "expect_failure": True, "build_spec": invalid}]


def make_request(executable, directory, *, run_id=None, host=None, mode="probe", cases=None, bindings=None):
    identity = run_id or str(uuid.uuid4())
    sources = source_identities()
    request = {"schema_version": 1, "run_id": identity, "mode": mode, "channel": "matlab_batch",
               "host_fingerprint": host or host_fingerprint(), "matlab_executable": str(Path(executable).resolve()),
               "output_directory": str(Path(directory).resolve()), "sources": sources, "source_identity": canonical_digest(sources),
               "supported_blocks": contract()["supported_blocks"], "required_functions": contract()["required_functions"],
               "cases": cases if cases is not None else qualification_cases(identity), "bindings": bindings or {}}
    request["input_identity"] = canonical_digest(request)
    return request


def matlab_command(executable, input_path, log_path):
    # Changing directory affects only this new process; no persistent/global path mutation.
    statement = "cd('{}'); probe_implementation('{}')".format(_matlab_quote(ROOT / "scripts/matlab"), _matlab_quote(input_path))
    return [str(Path(executable).resolve()), *(["-wait"] if os.name == "nt" else []), "-batch", statement, "-logfile", str(Path(log_path).resolve())]


def execute_request(request, *, timeout=240):
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    _validate_request(request)
    if (request.get("mode") not in {"probe", "implementation"} or request.get("channel") != "matlab_batch" or
            canonical_digest(request.get("supported_blocks")) != canonical_digest(contract()["supported_blocks"]) or
            canonical_digest(request.get("required_functions")) != canonical_digest(contract()["required_functions"])):
        raise ValueError("request execution surface differs from controlled native contract")
    cases = request.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("native request cases required")
    if request["mode"] == "probe" and canonical_digest(cases) != canonical_digest(qualification_cases(request["run_id"])):
        raise ValueError("probe inputs differ from controlled qualification cases")
    if request["mode"] == "implementation" and (len(cases) != 1 or cases[0].get("case_id") != "implementation" or cases[0].get("expect_failure") is not False):
        raise ValueError("one task implementation case required")
    for case in cases:
        validate_build_spec(case["build_spec"])
    if request["mode"] == "implementation":
        from validate_implementation_receipt import _bound_external, same_runtime
        from validate_environment import validate_environment
        bindings = request["bindings"]
        original = _bound_external(bindings["mapping_input"])
        if original.read_bytes() != bindings["mapping_original_text"].encode("utf-8"):
            raise ValueError("complete mapping input changed before native execution")
        for binding in bindings["bound_files"]:
            _bound_external(binding)
        a_path = _bound_external(bindings["environment_profile"])
        d_path = _bound_external(bindings["implementation_profile"])
        _bound_external(bindings["environment_receipt"])
        _bound_external(bindings["implementation_profile_receipt"])
        a = validate_environment(a_path)
        d = validate_implementation_profile(d_path)
        if not a["valid"] or not d["valid"] or not same_runtime(load_document(a_path)["runtime"], d["runtime"]):
            raise ValueError("current independent A and D operation qualifications required before execution")
        if request["host_fingerprint"] != host_fingerprint():
            raise ValueError("native request host differs from current execution host")
        if _path(request["matlab_executable"]) != _path(d["runtime"]["executable"]):
            raise ValueError("native request executable differs from qualification")
    executable, directory = Path(request["matlab_executable"]), Path(request["output_directory"])
    if not executable.is_file():
        raise ValueError("MATLAB executable does not exist")
    names = contract()["evidence"]
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / names["input"], request)
    process, console = _run_process(matlab_command(executable, directory / names["input"], directory / names["log"]), directory, timeout)
    log = directory / names["log"]
    if not log.exists():
        log.write_text(console, encoding="utf-8")
    elif console:
        with log.open("a", encoding="utf-8") as stream:
            stream.write("\nRunner console output:\n" + console)
    raw = directory / names["raw"]
    if not raw.exists():
        write_json(raw, {"schema_version": 1, "run_id": request["run_id"], "status": "failed",
                         "error": "MATLAB did not produce a report; see preserved process/log evidence"})
    return process


def artifact_manifest(directory, raw, *, include_profile=False):
    names = contract()["evidence"]
    result = {key: {"file": names[key], "sha256": sha256_file(Path(directory) / names[key])}
              for key in ("input", "raw", "log", *(("profile",) if include_profile else ())) }
    for actual in raw.get("cases", []):
        if actual.get("call_success") is True:
            for kind, filename in (("structure", actual["structure_file"]), ("model", actual["model_file"])):
                path = Path(directory) / filename
                if path.is_file():
                    result[actual["case_id"] + "_" + kind] = {"file": filename, "sha256": sha256_file(path)}
    return result


def run_probe(executable, directory, *, timeout=240):
    request = make_request(executable, directory)
    process = execute_request(request, timeout=timeout)
    directory = Path(request["output_directory"])
    names = contract()["evidence"]
    raw = load_document(directory / names["raw"])
    try:
        profile = derive_profile(raw, request, process)
        write_json(directory / names["profile"], profile)
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as error:
        profile = None
        write_json(directory / names["profile"], {"schema_version": 1, "run_id": request["run_id"], "normalization_error": str(error)})
    receipt = {"schema_version": 1, "run_id": request["run_id"], "sources": request["sources"], "process": process,
               "runtime_fingerprint": profile["runtime"]["fingerprint"] if profile else None,
               "artifacts": artifact_manifest(directory, raw, include_profile=True)}
    write_json(directory / names["receipt"], receipt)
    result = validate_implementation_profile(directory / names["profile"], expected_root=Path(executable).resolve().parent.parent)
    result["profile_path"] = str(directory / names["profile"])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matlab-executable", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=240)
    args = parser.parse_args()
    try:
        result = run_probe(args.matlab_executable, args.output_dir, timeout=args.timeout)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result = {"valid": False, "errors": [str(error)], "implementation_assured": False}
    emit(result)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
