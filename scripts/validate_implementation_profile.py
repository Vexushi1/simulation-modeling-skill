"""Read-only validation of independently bound Phase D native operation evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from runtime_common import ROOT, canonical_digest, contained_path, emit, host_fingerprint, load_document, sha256_file
from validate_environment import _array, _official_function, _path, _time, _version_info, runtime_identity, utc_text

CONTRACT_PATH = "core/implementation_assurance_contract.yaml"
OPERATION = "simulink.core_build_structure"
IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")
NUMERIC = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def contract():
    return load_document(ROOT / CONTRACT_PATH)


def source_identities():
    return {name: sha256_file(ROOT / name) for name in contract()["source_files"]}


def validate_build_spec(spec):
    """Reject executable expressions and every surface outside the native baseline."""
    if not isinstance(spec, dict) or set(spec) != {"schema_version", "model_name", "blocks", "connections", "parameters"}:
        raise ValueError("build_spec: exact core specification fields required")
    from validate_parameter_provenance import MATLAB_KEYWORDS
    if (type(spec["schema_version"]) is not int or spec["schema_version"] != 1 or
            not isinstance(spec["model_name"], str) or not IDENTIFIER.fullmatch(spec["model_name"]) or spec["model_name"] in MATLAB_KEYWORDS):
        raise ValueError("build_spec: invalid version or model name")
    policy = contract()["supported_blocks"]
    if not isinstance(spec["parameters"], list):
        raise ValueError("build_spec: parameters must be an array")
    names = set()
    for parameter in spec["parameters"]:
        if not isinstance(parameter, dict) or set(parameter) != {"code_name", "value", "unit"}:
            raise ValueError("build_spec: exact parameter fields required")
        name = parameter["code_name"]
        if not isinstance(name, str) or not IDENTIFIER.fullmatch(name) or name in MATLAB_KEYWORDS or name in names or name == spec["model_name"]:
            raise ValueError("build_spec: invalid or duplicate parameter name")
        names.add(name)
        value = parameter["value"]
        if not ((type(value) is int and abs(value) <= 2**53) or (type(value) is float and math.isfinite(value))):
            raise ValueError("build_spec: a finite scalar parameter is required")
        unit = parameter["unit"]
        if unit is not None and (not isinstance(unit, str) or not unit.strip() or len(unit) > 128):
            raise ValueError("build_spec: invalid unit")
    blocks = {}
    if not isinstance(spec["blocks"], list) or not spec["blocks"]:
        raise ValueError("build_spec: nonempty blocks array required")
    for block in spec["blocks"]:
        if not isinstance(block, dict) or set(block) != {"id", "path", "type", "parameters"}:
            raise ValueError("build_spec: exact block fields required")
        identity, kind = block["id"], block["type"]
        if (not isinstance(identity, str) or not IDENTIFIER.fullmatch(identity) or identity in MATLAB_KEYWORDS or identity in blocks or
                block["path"] != spec["model_name"] + "/" + identity or kind not in policy):
            raise ValueError("build_spec: unsupported block type, name, or flat path")
        fields = block["parameters"]
        if not isinstance(fields, dict) or set(fields) != set(policy[kind]["parameters"]):
            raise ValueError("build_spec: block parameters differ from the supported core API")
        for key, value in fields.items():
            if not isinstance(value, str):
                raise ValueError("build_spec: block values must be validated strings")
            if key in {"Gain", "Value"} and value not in names:
                raise ValueError("build_spec: gains and constants require a registered parameter reference")
            if key == "InitialCondition":
                if (not NUMERIC.fullmatch(value) or not math.isfinite(float(value)) or
                        (re.fullmatch(r"[+-]?\d+", value) and abs(int(value)) > 2**53)):
                    raise ValueError("build_spec: initial condition must be a finite native-representable approved scalar literal")
            if key == "Inputs" and value not in {"++", "+-", "-+", "--"}:
                raise ValueError("build_spec: unsupported sum signs")
            if key == "Port" and (not re.fullmatch(r"[1-9]\d*", value) or int(value) > 1024):
                raise ValueError("build_spec: invalid port setting")
        blocks[identity] = kind
    if not isinstance(spec["connections"], list):
        raise ValueError("build_spec: connections must be an array")
    destinations = set()
    for line in spec["connections"]:
        if not isinstance(line, dict) or set(line) != {"source", "destination"}:
            raise ValueError("build_spec: exact connection fields required")
        for side in ("source", "destination"):
            port = line[side]
            if (not isinstance(port, dict) or set(port) != {"block_id", "port"} or port["block_id"] not in blocks or
                    type(port["port"]) is not int or not 1 <= port["port"] <= 1024):
                raise ValueError("build_spec: invalid connection endpoint")
        destination = (line["destination"]["block_id"], line["destination"]["port"])
        if destination in destinations:
            raise ValueError("build_spec: an input cannot be connected twice")
        destinations.add(destination)
    return spec


def _block_reference(kind):
    return contract()["supported_blocks"][kind]["source"]


def assert_structure(structure, spec, directory, runtime_root):
    """Derive assertions from actual readback rather than a producer success flag."""
    validate_build_spec(spec)
    if not isinstance(structure, dict) or type(structure.get("schema_version")) is not int or structure["schema_version"] != 1:
        raise ValueError("structure: object required")
    for flag in ("updated_before_save", "saved", "closed_before_reload", "reopened", "updated_after_reload"):
        if structure.get(flag) is not True:
            raise ValueError("structure: missing actual " + flag)
    if structure.get("simulation_run") is not False or structure.get("diagram_type") != "model":
        raise ValueError("structure: native operation must be a model structure check without simulation")
    if structure.get("model_name") != spec["model_name"] or structure.get("model_workspace_source") != "Model File":
        raise ValueError("structure: model identity or workspace source differs")
    expected_file = (Path(directory) / (spec["model_name"] + ".slx")).resolve()
    if _path(structure.get("model_file", "")) != _path(expected_file) or not expected_file.is_file() or expected_file.stat().st_size == 0:
        raise ValueError("structure: actual saved model is absent, empty, or outside its evidence directory")
    library = Path(structure.get("library_file", "")).resolve()
    if not library.is_file() or not library.is_relative_to(Path(runtime_root).resolve() / "toolbox" / "simulink"):
        raise ValueError("structure: source library is not an observed official Simulink file")
    callbacks = structure.get("callbacks")
    if not isinstance(callbacks, dict) or set(callbacks) != {"PreLoadFcn", "PostLoadFcn", "InitFcn", "StartFcn", "StopFcn", "PreSaveFcn", "PostSaveFcn", "CloseFcn"} or any(type(value) is not str or value for value in callbacks.values()):
        raise ValueError("structure: custom callbacks are outside the native baseline")
    observed = _array(structure.get("blocks", []))
    by_id = {block["id"]: block for block in observed}
    if len(by_id) != len(observed) or set(by_id) != {block["id"] for block in spec["blocks"]}:
        raise ValueError("structure: actual block set differs from build specification")
    counts = {"Inport": (0, 1), "Outport": (1, 0), "Constant": (0, 1), "Gain": (1, 1), "Sum": (2, 1), "Integrator": (1, 1)}
    for expected in spec["blocks"]:
        actual = by_id[expected["id"]]
        if (actual.get("path") != expected["path"] or actual.get("type") != expected["type"] or
                actual.get("source") != _block_reference(expected["type"]) or canonical_digest(actual.get("parameters")) != canonical_digest(expected["parameters"])):
            raise ValueError("structure: block parameter/path/type/source mismatch: " + expected["id"])
        ports = actual.get("ports", {})
        if (any(type(ports.get(key)) is not int for key in ("inport_count", "outport_count")) or
                (ports.get("inport_count"), ports.get("outport_count")) != counts[expected["type"]]):
            raise ValueError("structure: actual port count mismatch: " + expected["id"])
        if actual.get("mask") != "off" or actual.get("reference_model", ""):
            raise ValueError("structure: custom mask or reference is outside the core scope")
    def endpoints(line):
        if any(type(line[side]["port"]) is not int for side in ("source", "destination")):
            raise ValueError("structure: actual port indices must be integers")
        return (line["source"]["block_id"], line["source"]["port"], line["destination"]["block_id"], line["destination"]["port"])
    lines = _array(structure.get("connections", []))
    if sorted(map(endpoints, lines)) != sorted(map(endpoints, spec["connections"])):
        raise ValueError("structure: actual connection endpoints differ")
    parameters = _array(structure.get("parameters", []))
    if len(parameters) != len(spec["parameters"]):
        raise ValueError("structure: actual workspace parameter set differs")
    actual_params = {item["code_name"]: item for item in parameters}
    if len(actual_params) != len(parameters):
        raise ValueError("structure: duplicate actual parameter")
    for expected in spec["parameters"]:
        actual = actual_params.get(expected["code_name"], {})
        if (type(actual.get("value")) not in (int, float) or actual["value"] != expected["value"] or
                actual.get("unit") != (expected["unit"] or "") or actual.get("class") != "Simulink.Parameter"):
            raise ValueError("structure: actual parameter value/unit/class differs")
    return True


def _validate_request(request):
    import uuid
    fields = {"schema_version", "run_id", "mode", "channel", "host_fingerprint", "matlab_executable", "output_directory",
              "sources", "source_identity", "supported_blocks", "required_functions", "cases", "bindings", "input_identity"}
    if (not isinstance(request, dict) or set(request) != fields or type(request["schema_version"]) is not int or request["schema_version"] != 1 or
            not isinstance(request["run_id"], str) or not isinstance(request["host_fingerprint"], str) or not request["host_fingerprint"]):
        raise ValueError("native request schema or identity fields differ")
    uuid.UUID(request["run_id"])
    if (request["mode"] not in {"probe", "implementation"} or request["channel"] != "matlab_batch" or
            canonical_digest(request["supported_blocks"]) != canonical_digest(contract()["supported_blocks"]) or
            canonical_digest(request["required_functions"]) != canonical_digest(contract()["required_functions"])):
        raise ValueError("native request execution surface differs")
    if not isinstance(request["cases"], list) or not request["cases"] or not isinstance(request["bindings"], dict):
        raise ValueError("native request cases or bindings differ")
    for case in request["cases"]:
        if not isinstance(case, dict) or set(case) != {"case_id", "expect_failure", "build_spec"} or type(case["expect_failure"]) is not bool:
            raise ValueError("native request case schema differs")
        validate_build_spec(case["build_spec"])
    identity = request.get("input_identity")
    payload = {key: value for key, value in request.items() if key != "input_identity"}
    if identity != canonical_digest(payload) or request.get("source_identity") != canonical_digest(request.get("sources")):
        raise ValueError("input or source identity differs")
    if canonical_digest(request.get("sources")) != canonical_digest(source_identities()):
        raise ValueError("native source files changed")
    return identity


def derive_profile(raw, request, process):
    policy = contract()
    _validate_request(request)
    if type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
        raise ValueError("native raw schema version differs")
    runtime_raw = raw["runtime"]
    root = runtime_raw["matlabroot"]
    inventory = _array(raw.get("installed_products", []))
    products = {item["Name"]: item for item in inventory}
    functions = _array(raw.get("functions", []))
    resolutions = {item["name"]: item["path"] for item in functions}
    library_record = next((item for item in _array(raw.get("cases", [])) if item.get("call_success") is True), None)
    library_file = ""
    if library_record:
        structure = load_document(contained_path(Path(request["output_directory"]), library_record["structure_file"]))
        library_file = structure.get("library_file", "")
    runtime = runtime_identity({**raw, "operations": [{"functions": functions, "operation_id": "simulink.library_load", "output": {"file_name": library_file}}]}, request["matlab_executable"])
    structures = _array(raw.get("cases", []))
    expected = request["cases"]
    if len(structures) != len(expected):
        raise ValueError("raw case count differs")
    passed, failures = [], []
    for case, actual in zip(expected, structures):
        if actual.get("case_id") != case["case_id"] or actual.get("attempted") is not True:
            failures.append("case identity or attempt differs")
            continue
        if case["expect_failure"]:
            if actual.get("call_success") is False and actual.get("error", {}).get("identifier") == "PhaseD:InvalidPort":
                passed.append(case["case_id"])
            else:
                failures.append("expected bad port rejection was not observed")
            continue
        if actual.get("call_success") is not True:
            failures.append("native call failed: " + case["case_id"])
            continue
        try:
            structure_path = contained_path(Path(request["output_directory"]), actual["structure_file"])
            structure = load_document(structure_path)
            assert_structure(structure, case["build_spec"], request["output_directory"], root)
            passed.append(case["case_id"])
        except (OSError, ValueError, KeyError, TypeError) as error:
            failures.append(str(error))
    if len(products) != len(inventory) or set(resolutions) != set(policy["required_functions"]) or len(resolutions) != len(functions):
        raise ValueError("native inventory or function records differ from the exact required set")
    installed = set(products) >= {"MATLAB", "Simulink"}
    licensed = type(raw.get("license_test")) in (int, float) and raw["license_test"] == 1
    resolvable = len(resolutions) == len(functions) and all(_official_function(resolutions.get(name), root) for name in policy["required_functions"])
    runtime_ok = (runtime_raw["release"] == policy["target"]["matlab_release"] and
                  products.get("Simulink", {}).get("Version") == policy["target"]["simulink_version"])
    callable_ = all(item.get("call_success") is True for item, case in zip(structures, expected) if not case["expect_failure"])
    qualified = installed and licensed and resolvable and runtime_ok and callable_ and not failures
    qualified = qualified and raw.get("status") == "completed" and raw.get("simulation_run") is False
    profile = {"schema_version": 1, "run_id": request["run_id"], "captured_at": raw["finished_at"],
               "valid_until": utc_text(_time(raw["finished_at"]) + timedelta(seconds=policy["validity_seconds"])),
               "execution": {"channel": "matlab_batch", "host_fingerprint": request["host_fingerprint"], **process},
               "runtime": runtime, "sources": request["sources"], "input_identity": request["input_identity"],
               "operation": {"operation_id": OPERATION, "installed": installed, "licensed": licensed,
                             "resolvable": resolvable, "callable": callable_, "qualified": bool(qualified),
                             "scope": policy["scope"], "passed_cases": passed, "assertion_errors": failures}}
    return profile


def validate_implementation_profile(profile_path, *, expected_root=None, expected_host=None, now=None, require_current=True):
    result = {"valid": False, "profile_current": False, "implementation_assured": False, "qualified_operations": [],
              "profile_sha256": None, "receipt_sha256": None, "runtime": None, "errors": []}
    try:
        path = Path(profile_path).resolve()
        policy = contract()
        names = policy["evidence"]
        profile, receipt = load_document(path), load_document(path.parent / names["receipt"])
        request, raw = load_document(path.parent / names["input"]), load_document(path.parent / names["raw"])
        if path.name != names["profile"] or request.get("mode") != "probe":
            raise ValueError("only the independent native probe can qualify a profile")
        _validate_request(request)
        if request["bindings"]:
            raise ValueError("qualification probe must not consume project bindings")
        if [item["case_id"] for item in request["cases"]] != policy["qualification_cases"]:
            raise ValueError("qualification cases differ from contract")
        from probe_implementation import qualification_cases
        if canonical_digest(request["cases"]) != canonical_digest(qualification_cases(request["run_id"])):
            raise ValueError("native qualification inputs differ from controlled contract cases")
        if _path(request["output_directory"]) != _path(path.parent):
            raise ValueError("native evidence directory differs")
        for key in ("run_id", "channel", "host_fingerprint", "input_identity", "source_identity"):
            expected = request.get(key) if key != "channel" else "matlab_batch"
            if raw.get(key) != expected:
                raise ValueError("native raw identity differs: " + key)
        process = receipt["process"]
        if process.get("process_state") != "completed" or type(process.get("exit_code")) is not int or process["exit_code"] != 0:
            raise ValueError("native process did not complete with exit 0")
        times = [_time(process["started_at"]), _time(raw["started_at"]), _time(raw["finished_at"]), _time(process["finished_at"])]
        if not times[0] <= times[1] <= times[2] <= times[3] or times[0] == times[3]:
            raise ValueError("native evidence times are reversed or incomplete")
        clock = _time(now) if now is not None else datetime.now(timezone.utc)
        if times[-1] > clock:
            raise ValueError("native evidence is future dated")
        if require_current and clock > _time(profile["valid_until"]):
            raise ValueError("native operation profile expired; re-probe for new execution")
        if request["host_fingerprint"] != (expected_host or host_fingerprint()):
            raise ValueError("native host identity differs")
        if expected_root is not None and _path(raw["runtime"]["matlabroot"]) != _path(expected_root):
            raise ValueError("native runtime root differs")
        release, version = _version_info(raw["runtime"]["matlabroot"])
        if release != policy["target"]["matlab_release"] or not str(raw["runtime"]["version"]).startswith(version):
            raise ValueError("native runtime version metadata changed")
        expected_profile = derive_profile(raw, request, process)
        if canonical_digest(profile) != canonical_digest(expected_profile) or profile["operation"]["qualified"] is not True:
            raise ValueError("native profile does not match recomputed qualified assertions")
        if type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 1 or receipt.get("run_id") != request["run_id"] or canonical_digest(receipt.get("sources")) != canonical_digest(request["sources"]) or receipt.get("runtime_fingerprint") != profile["runtime"]["fingerprint"]:
            raise ValueError("native receipt identity differs")
        for binding in receipt["artifacts"].values():
            artifact = contained_path(path.parent, binding["file"])
            if not artifact.is_file() or sha256_file(artifact) != binding["sha256"]:
                raise ValueError("native artifact digest mismatch: " + binding["file"])
        required = {"input": names["input"], "raw": names["raw"], "log": names["log"], "profile": names["profile"]}
        for key, name in required.items():
            if receipt["artifacts"].get(key, {}).get("file") != name:
                raise ValueError("native receipt omits required artifact: " + key)
        for case, actual in zip(request["cases"], _array(raw["cases"])):
            if not case["expect_failure"]:
                for kind, filename in (("model", case["build_spec"]["model_name"] + ".slx"), ("structure", actual["structure_file"])):
                    binding = receipt["artifacts"].get(case["case_id"] + "_" + kind, {})
                    if binding.get("file") != filename:
                        raise ValueError("native receipt omits case artifact")
        result.update(valid=True, profile_current=clock <= _time(profile["valid_until"]), implementation_assured=True,
                      qualified_operations=[OPERATION], profile_sha256=sha256_file(path),
                      receipt_sha256=sha256_file(path.parent / names["receipt"]), runtime=profile["runtime"])
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, ET.ParseError) as error:
        result["errors"].append(str(error))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--expected-root", type=Path)
    args = parser.parse_args()
    result = validate_implementation_profile(args.path, expected_root=args.expected_root)
    emit(result)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
