"""Run an isolated MATLAB batch probe and preserve its complete evidence chain."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
from datetime import datetime, timezone
import uuid
import xml.etree.ElementTree as ET

from runtime_common import ROOT, canonical_digest, host_fingerprint, load_document, sha256_file
from validate_environment import _contract, _version_info, build_profile, source_identities, utc_text, validate_environment


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def make_request(executable, directory, *, include_statistics=False, required_operations=None,
                 fallback_reason="explicit_batch_probe", run_id=None, host=None):
    contract = _contract()
    if required_operations is not None and (
        not isinstance(required_operations, (list, tuple)) or
        not all(isinstance(name, str) for name in required_operations)
    ):
        raise ValueError("required_operations must be an array of operation IDs")
    required = list(dict.fromkeys(contract["core_operations"] + list(required_operations or [])))
    ids = list(contract["core_operations"])
    if include_statistics:
        ids.extend(contract["statistics_operations"])
    ids = list(dict.fromkeys(ids + required))
    if any(operation_id not in contract["operations"] for operation_id in ids):
        raise ValueError("unknown required operation")
    request = {
        "schema_version": 1, "run_id": run_id or str(uuid.uuid4()),
        "host_fingerprint": host if host is not None else host_fingerprint(),
        "matlab_executable": str(Path(executable).resolve()), "output_directory": str(Path(directory).resolve()),
        "fallback_reason": fallback_reason, "required_operations": required,
        "operation_specs": [{"operation_id": operation_id, **contract["operations"][operation_id]} for operation_id in ids],
        "sources": source_identities(contract),
    }
    request["source_identity"] = canonical_digest(request["sources"])
    request["input_identity"] = canonical_digest(request)
    return request


def _matlab_quote(path):
    return str(Path(path).resolve()).replace("\\", "/").replace("'", "''")


def matlab_command(executable, input_path, log_path):
    statement = "addpath('{}'); probe_environment('{}')".format(
        _matlab_quote(ROOT / "scripts/matlab"), _matlab_quote(input_path)
    )
    command = [str(Path(executable).resolve())]
    if os.name == "nt":
        command.append("-wait")
    return command + ["-batch", statement, "-logfile", str(Path(log_path).resolve())]


def _run_process(command, directory, timeout):
    process = {"started_at": utc_text(datetime.now(timezone.utc)), "finished_at": None,
               "process_state": "failed", "exit_code": None, "pid": None, "command": command}
    output = ""
    try:
        child = subprocess.Popen(command, cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding="utf-8", errors="replace",
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                 start_new_session=os.name != "nt")
        process["pid"] = child.pid
        try:
            output, _ = child.communicate(timeout=timeout)
            process["exit_code"] = child.returncode
            process["process_state"] = "completed" if child.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            # Stop only the process tree/group started by this invocation.
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                               capture_output=True, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                os.killpg(child.pid, signal.SIGKILL)
            output, _ = child.communicate()
            process["exit_code"] = child.returncode
            process["process_state"] = "timed_out"
            output += "\nProbe exceeded its process timeout.\n"
    except OSError as exception:
        output = str(exception) + "\n"
    process["finished_at"] = utc_text(datetime.now(timezone.utc))
    return process, output


def _failed_raw(request, process, error):
    root = Path(request["matlab_executable"]).parent.parent
    try:
        release, version = _version_info(root)
    except (OSError, ET.ParseError) as exception:
        release, version = "not_observed", "not_observed"
        error += "; runtime version metadata unavailable: " + str(exception)
    return {
        "schema_version": 1, "run_id": request["run_id"], "status": "failed",
        "channel": "matlab_batch", "host_fingerprint": request["host_fingerprint"],
        "input_identity": request["input_identity"], "source_identity": canonical_digest(request["sources"]),
        "started_at": process["started_at"], "finished_at": process["finished_at"],
        "runtime": {"release": release, "version": version, "matlabroot": str(root), "platform": "not_observed"},
        "installed_products": [], "licenses_inuse": [], "fatal_error": {"message": error},
        "operations": [{"operation_id": spec["operation_id"], "parameters": spec["input"],
                        "attempted": False, "call_success": False, "license_test": None, "functions": [],
                        "output": None, "error": {"message": error}}
                       for spec in request["operation_specs"]],
    }


def run_probe(executable, directory, *, include_statistics=False, required_operations=None,
              timeout=180, fallback_reason="explicit_batch_probe"):
    executable, directory = Path(executable).resolve(), Path(directory).resolve()
    if not executable.is_file():
        raise ValueError("MATLAB executable does not exist")
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    # No existing evidence directory can be reused, even if it appears empty.
    contract = _contract()
    artifacts = contract["evidence_policy"]["artifacts"]
    request = make_request(executable, directory, include_statistics=include_statistics,
                           required_operations=required_operations, fallback_reason=fallback_reason)
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / artifacts["input"], request)
    command = matlab_command(executable, directory / artifacts["input"], directory / artifacts["log"])
    process, console = _run_process(command, directory, timeout)
    log_path = directory / artifacts["log"]
    if not log_path.exists():
        log_path.write_text(console, encoding="utf-8")
    elif console and console.strip() not in log_path.read_text(encoding="utf-8", errors="replace"):
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write("\nRunner console output:\n" + console)
    raw_path = directory / artifacts["raw"]
    if not raw_path.exists():
        write_json(raw_path, _failed_raw(request, process, "MATLAB did not produce a raw report; see process receipt and log"))
    profile_path = directory / artifacts["profile"]
    try:
        raw = load_document(raw_path)
        profile = build_profile(raw, request, process, contract)
        write_json(profile_path, profile)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, ET.ParseError) as exception:
        # Preserve an invalid raw report verbatim; never replace it with success.
        write_json(profile_path, {"schema_version": 1, "run_id": request["run_id"], "normalization_error": str(exception)})
        profile = None
    receipt = {
        "schema_version": 1, "run_id": request["run_id"], "channel": "matlab_batch",
        "host_fingerprint": request["host_fingerprint"], "input_identity": request["input_identity"],
        "sources": request["sources"], "process": process,
        "runtime_fingerprint": profile["runtime"]["fingerprint"] if profile else None,
        "artifacts": {kind: {"file": filename, "sha256": sha256_file(directory / filename)}
                      for kind, filename in artifacts.items()},
    }
    write_json(directory / contract["evidence_policy"]["receipt_filename"], receipt)
    result = validate_environment(profile_path, required_operations=request["required_operations"],
                                  expected_root=executable.parent.parent)
    result["profile_path"] = str(profile_path)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matlab-executable", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--include-statistics", action="store_true")
    parser.add_argument("--require-operation", action="append", default=[])
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--fallback-reason", choices=["mcp_not_available", "explicit_batch_probe"], default="explicit_batch_probe")
    args = parser.parse_args()
    try:
        result = run_probe(args.matlab_executable, args.output_dir, include_statistics=args.include_statistics,
                           required_operations=args.require_operation, timeout=args.timeout, fallback_reason=args.fallback_reason)
    except (OSError, ValueError) as exception:
        result = {"valid": False, "errors": [str(exception)], "runtime_assured": False,
                  "profile_current": False, "status": "failed"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
