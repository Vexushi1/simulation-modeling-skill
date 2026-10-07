"""Validate Phase A operation evidence without starting MATLAB or modifying state."""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

from runtime_common import ROOT, canonical_digest, host_fingerprint, load_document, schema_errors, sha256_file

CONTRACT_PATH = "core/runtime_assurance_contract.yaml"
SCHEMA_PATH = "core/capability_profile.schema.yaml"


def _contract():
    contract = load_document(ROOT / CONTRACT_PATH)
    baseline = load_document(ROOT / "core/environment_baseline.yaml")["baseline"]
    if (contract["target"]["matlab_release"] != baseline["matlab_release"] or
            contract["target"]["simulink_version"] != baseline["simulink_version"]):
        raise ValueError("runtime contract disagrees with the declared baseline")
    return contract


def source_identities(contract=None):
    contract = contract or _contract()
    return {name: sha256_file(ROOT / name) for name in contract["evidence_policy"]["source_files"]}


def utc_text(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _time(value):
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("time must be an ISO timestamp or datetime")
    if result.tzinfo is None:
        raise ValueError("time must include a timezone")
    return result.astimezone(timezone.utc)


def _path(value):
    return os.path.normcase(str(Path(value).resolve()))


def _array(value):
    if isinstance(value, list):
        if not all(isinstance(item, dict) for item in value):
            raise ValueError("record array contains a non-object item")
        return value
    if isinstance(value, dict):
        return [value]
    raise ValueError("expected an array of records")


def _mapping(value, label):
    if not isinstance(value, dict):
        raise ValueError(label + " must be an object")
    return value


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _near(value, expected, tolerance):
    return _number(value) and abs(value - expected) <= tolerance


def _vector_near(values, expected, tolerance):
    return isinstance(values, list) and len(values) == len(expected) and all(
        _near(value, target, tolerance) for value, target in zip(values, expected)
    )


def _assert_output(operation_id, output, parameters, runtime_root):
    if not isinstance(output, dict):
        return False
    if operation_id == "matlab.basic_execution":
        return _near(output.get("value"), parameters["expected"], 0)
    if operation_id == "simulink.library_load":
        library_file = output.get("file_name", "")
        official = bool(library_file) and Path(library_file).is_file() and Path(library_file).resolve().is_relative_to(
            Path(runtime_root).resolve() / "toolbox" / "simulink"
        )
        return official and all((
            output.get("library_name") == parameters["library"],
            output.get("loaded") is True,
            output.get("diagram_type") == "library",
            output.get("closed_without_save") is True,
            output.get("simulation_run") is False,
            output.get("model_saved") is False,
        ))
    if operation_id == "statistics.normcdf":
        return _near(output.get("value"), parameters["expected"], parameters["tolerance"])
    if operation_id == "statistics.fitlm":
        tolerance = parameters["tolerance"]
        return all((
            _vector_near(output.get("coefficients"), parameters["expected_coefficients"], tolerance),
            _vector_near(output.get("predictions"), parameters["expected_predictions"], tolerance),
            _near(output.get("rmse"), parameters["expected_rmse"], tolerance),
        ))
    if operation_id == "statistics.lhsdesign":
        sample = output.get("sample")
        n, p = parameters["n"], parameters["p"]
        if not isinstance(sample, list) or len(sample) != n:
            return False
        if not all(isinstance(row, list) and len(row) == p for row in sample):
            return False
        if not all(_number(value) and 0 < value < 1 for row in sample for value in row):
            return False
        return all(sorted(math.floor(row[column] * n) for row in sample) == list(range(n)) for column in range(p))
    return False


def _official_function(path, root):
    if not isinstance(path, str) or not path:
        return False
    builtin = path.startswith("built-in (") and path.endswith(")")
    if builtin:
        path = path[len("built-in ("):-1]
    return (builtin or Path(path).is_file()) and Path(path).resolve().is_relative_to(Path(root).resolve())


def _derive_operations(raw, request, contract):
    records = _array(raw.get("operations", []))
    by_id = {}
    for record in records:
        operation_id = record["operation_id"]
        if operation_id in by_id:
            raise ValueError("duplicate raw operation: " + operation_id)
        by_id[operation_id] = record
    inventory = _array(raw.get("installed_products", []))
    products = {record["Name"]: record for record in inventory}
    if len(products) != len(inventory):
        raise ValueError("duplicate product inventory record")
    root = raw["runtime"]["matlabroot"]
    target = contract["target"]
    runtime_ok = raw["runtime"]["release"] == target["matlab_release"]
    simulink = products.get("Simulink", {})
    runtime_ok = runtime_ok and simulink.get("Version") == target["simulink_version"]
    operations = {}
    for spec in request["operation_specs"]:
        operation_id = spec["operation_id"]
        record = by_id.get(operation_id, {})
        parameters = spec["input"]
        installed = spec["product"] in products
        licensed = type(record.get("license_test")) in (int, float) and record.get("license_test") == 1
        functions = _array(record.get("functions", []))
        resolutions = {item["name"]: item["path"] for item in functions}
        resolvable = all(_official_function(resolutions.get(name), root) for name in spec["functions"])
        same_input = canonical_digest(record.get("parameters")) == canonical_digest(parameters)
        callable_ = record.get("attempted") is True and record.get("call_success") is True
        qualified = installed and licensed and resolvable and callable_ and same_input and runtime_ok
        qualified = qualified and _assert_output(operation_id, record.get("output"), parameters, root)
        operations[operation_id] = {
            "product": spec["product"], "installed": installed, "licensed": licensed,
            "resolvable": resolvable, "callable": callable_, "qualified": bool(qualified),
            "scope": spec["scope"], "input_sha256": canonical_digest(parameters),
        }
    if set(by_id) != set(operations):
        raise ValueError("raw operation set does not match requested operations")
    return operations


def _version_info(root):
    node = ET.parse(Path(root) / "VersionInfo.xml").getroot()
    return node.findtext("release"), node.findtext("version")


def runtime_identity(raw, executable):
    base = dict(raw["runtime"])
    root = Path(base["matlabroot"])
    files = {}
    for operation in _array(raw.get("operations", [])):
        for item in _array(operation.get("functions", [])):
            path = Path(item["path"])
            if path.is_file():
                files[str(path.resolve())] = sha256_file(path)
        output = operation.get("output")
        if operation.get("operation_id") == "simulink.library_load" and isinstance(output, dict):
            library = Path(output.get("file_name", ""))
            if library.is_file():
                files[str(library.resolve())] = sha256_file(library)
    runtime = {
        "release": base["release"], "version": base["version"], "matlabroot": str(root.resolve()),
        "executable": str(Path(executable).resolve()), "platform": base["platform"],
        "inventory_sha256": canonical_digest(raw.get("installed_products", [])),
        "executable_sha256": sha256_file(Path(executable)),
        "version_file_sha256": sha256_file(root / "VersionInfo.xml"),
        "function_files": [{"path": path, "sha256": digest} for path, digest in sorted(files.items())],
    }
    runtime["fingerprint"] = canonical_digest(runtime)
    return runtime


def build_profile(raw, request, process, contract=None):
    """Normalize recorded evidence; qualification remains operation-specific."""
    contract = contract or _contract()
    policy = contract["evidence_policy"]
    captured = raw["finished_at"]
    return {
        "schema_version": 1, "run_id": request["run_id"], "captured_at": captured,
        "valid_until": utc_text(_time(captured) + timedelta(seconds=policy["validity_seconds"])),
        "execution": {
            "channel": policy["execution_channel"], "fallback_reason": request["fallback_reason"],
            "host_fingerprint": request["host_fingerprint"], "started_at": process["started_at"],
            "finished_at": process["finished_at"], "process_state": process["process_state"],
            "exit_code": process["exit_code"],
        },
        "runtime": runtime_identity(raw, request["matlab_executable"]),
        "input_identity": request["input_identity"], "sources": request["sources"],
        "operations": _derive_operations(raw, request, contract),
        "evidence": {
            "receipt_file": policy["receipt_filename"],
            "input_file": policy["artifacts"]["input"], "raw_file": policy["artifacts"]["raw"],
            "log_file": policy["artifacts"]["log"],
        },
    }


def validate_environment(profile_path: Path, *, required_operations=None, expected_root=None, now=None, expected_host=None) -> dict:
    """expected_root is the expected MATLAB installation root; source Authority is ROOT."""
    result = {
        "valid": False, "errors": [], "runtime_assured": False, "profile_current": False,
        "qualified_operations": [], "profile_sha256": None, "receipt_sha256": None,
        "required_operations": [], "status": "failed",
    }
    errors = result["errors"]
    try:
        profile_path = Path(profile_path).resolve()
        contract = _contract()
        policy = contract["evidence_policy"]
        result["required_operations"] = list(contract["core_operations"])
        if required_operations is not None and (
            not isinstance(required_operations, (list, tuple)) or
            not all(isinstance(name, str) for name in required_operations)
        ):
            errors.append("required_operations must be an array of operation IDs")
            return result
        # The two core operations are always required; callers may only add requirements.
        required = list(dict.fromkeys(contract["core_operations"] + list(required_operations or [])))
        result["required_operations"] = required
        result["profile_sha256"] = sha256_file(profile_path)
        receipt_path = profile_path.parent / policy["receipt_filename"]
        if receipt_path.is_file():
            result["receipt_sha256"] = sha256_file(receipt_path)
        profile = load_document(profile_path)
        errors.extend(schema_errors(profile, load_document(ROOT / SCHEMA_PATH)))
        if errors:
            return result
        directory = profile_path.parent
        if profile_path.name != policy["artifacts"]["profile"]:
            errors.append("unexpected profile filename")
        receipt_path = directory / policy["receipt_filename"]
        receipt = load_document(receipt_path)
        result["receipt_sha256"] = sha256_file(receipt_path)
        request = load_document(directory / policy["artifacts"]["input"])
        raw = load_document(directory / policy["artifacts"]["raw"])
        if any(type(document.get("schema_version")) is not int or document.get("schema_version") != 1 for document in (receipt, request, raw)):
            errors.append("evidence schema version mismatch")
        if any(document.get("run_id") != profile["run_id"] for document in (receipt, request, raw)):
            errors.append("run identity mismatch")
        artifacts = _mapping(receipt.get("artifacts", {}), "receipt artifacts")
        expected_artifacts = policy["artifacts"]
        if set(artifacts) != set(expected_artifacts):
            errors.append("receipt artifact set mismatch")
        for kind, filename in expected_artifacts.items():
            if artifacts.get(kind) != {"file": filename, "sha256": sha256_file(directory / filename)}:
                errors.append("artifact digest mismatch: " + kind)
        sources = source_identities(contract)
        if any(document.get("sources") != sources for document in (profile, request, receipt)):
            errors.append("source identity changed")
        if raw.get("source_identity") != canonical_digest(sources):
            errors.append("raw source identity mismatch")
        identity = canonical_digest({key: value for key, value in request.items() if key != "input_identity"})
        if any(document.get("input_identity") != identity for document in (profile, request, receipt, raw)):
            errors.append("input identity mismatch")
        ids = [spec["operation_id"] for spec in _array(request["operation_specs"])]
        if len(ids) != len(set(ids)) or not set(contract["core_operations"]).issubset(ids):
            errors.append("request must include distinct core operations")
        if any(operation_id not in contract["operations"] for operation_id in ids):
            errors.append("unknown requested operation")
        else:
            expected_specs = [{"operation_id": operation_id, **contract["operations"][operation_id]} for operation_id in ids]
            if request["operation_specs"] != expected_specs:
                errors.append("operation inputs or specification changed")
        if _path(request.get("output_directory", "")) != _path(directory):
            errors.append("output directory identity mismatch")
        process = _mapping(receipt.get("process", {}), "process receipt")
        execution = profile["execution"]
        for field in ("started_at", "finished_at", "process_state", "exit_code"):
            if execution[field] != process.get(field):
                errors.append("process receipt mismatch: " + field)
        if process.get("process_state") != "completed" or type(process.get("exit_code")) is not int or process.get("exit_code") != 0:
            errors.append("MATLAB process did not complete successfully")
        if raw.get("status") != "completed":
            errors.append("raw probe is incomplete or failed")
        current_time = _time(now) if now is not None else datetime.now(timezone.utc)
        started, finished = _time(process["started_at"]), _time(process["finished_at"])
        raw_started, raw_finished = _time(raw["started_at"]), _time(raw["finished_at"])
        captured, expiry = _time(profile["captured_at"]), _time(profile["valid_until"])
        if not started <= raw_started <= raw_finished <= finished <= current_time or captured != raw_finished:
            errors.append("future, reversed or inconsistent evidence timestamps")
        if expiry != captured + timedelta(seconds=policy["validity_seconds"]) or current_time > expiry:
            errors.append("profile expired or validity period changed")
        host = expected_host if expected_host is not None else host_fingerprint()
        if any(document.get("host_fingerprint") != host for document in (request, receipt, raw)) or execution["host_fingerprint"] != host:
            errors.append("host identity mismatch")
        if execution["channel"] != "matlab_batch" or receipt.get("channel") != "matlab_batch" or raw.get("channel") != "matlab_batch":
            errors.append("execution channel mismatch")
        if execution["fallback_reason"] != request.get("fallback_reason"):
            errors.append("fallback identity mismatch")
        runtime = runtime_identity(raw, request["matlab_executable"])
        if profile["runtime"] != runtime or receipt.get("runtime_fingerprint") != runtime["fingerprint"]:
            errors.append("runtime identity changed or mismatched")
        root = runtime["matlabroot"]
        if expected_root is not None and _path(root) != _path(expected_root):
            errors.append("unexpected MATLAB installation root")
        if _path(Path(runtime["executable"]).parent.parent) != _path(root) or Path(runtime["executable"]).parent.name.lower() != "bin":
            errors.append("MATLAB executable does not belong to runtime root/bin")
        release, version = _version_info(root)
        if release != runtime["release"] or version != runtime["version"].split(" ")[0]:
            errors.append("installed runtime version changed or mismatched")
        if runtime["release"] != contract["target"]["matlab_release"]:
            errors.append("runtime does not match the R2025b baseline")
        derived = _derive_operations(raw, request, contract)
        expected_inputs = {spec["operation_id"]: spec["input"] for spec in request["operation_specs"]}
        if any(canonical_digest(record.get("parameters")) != canonical_digest(expected_inputs.get(record.get("operation_id"))) for record in _array(raw["operations"])):
            errors.append("raw operation input mismatch")
        if profile["operations"] != derived:
            errors.append("operation qualification does not match raw assertions")
        integrity_errors = list(errors)
        result["profile_current"] = not integrity_errors
        qualified = sorted(name for name, value in derived.items() if value["qualified"])
        result["qualified_operations"] = qualified if result["profile_current"] else []
        result["runtime_assured"] = result["profile_current"] and set(contract["core_operations"]).issubset(qualified)
        for operation_id in required:
            if operation_id not in contract["operations"]:
                errors.append("unknown required operation: " + operation_id)
            elif operation_id not in qualified:
                errors.append("required operation is not qualified: " + operation_id)
        result["valid"] = not errors
        result["status"] = "passed" if result["valid"] else "failed"
    except (OSError, ValueError, TypeError, KeyError, AttributeError, ET.ParseError) as exception:
        errors.append("invalid environment evidence: " + str(exception))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    parser.add_argument("--require-operation", action="append", default=[])
    parser.add_argument("--matlab-root", type=Path)
    args = parser.parse_args()
    result = validate_environment(args.profile, required_operations=args.require_operation, expected_root=args.matlab_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
