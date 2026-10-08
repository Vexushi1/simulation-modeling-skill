"""Explicitly run a frozen, approved, source-bound primary protocol in a new directory."""
from __future__ import annotations

import argparse
from pathlib import Path

from probe_environment import write_json
from probe_simulation import artifact_manifest, execute_request, file_binding, make_request
from runtime_common import canonical_digest, emit, load_document, sha256_file
from validate_environment import _path, validate_environment
from validate_implementation_receipt import same_runtime
from validate_simulation_profile import contract, finite, observed_runtime, validate_simulation_profile
from validate_simulation_protocol import semantic_digest, validate_simulation_protocol


def make_task_request(protocol_path, executable, directory, protocol_report, environment_profile, simulation_profile, *, project_root, simulation_timeout=60, required_operations=None):
    if not finite(simulation_timeout) or simulation_timeout <= 0:
        raise ValueError("simulation wall-clock timeout must be finite and positive")
    original = Path(protocol_path).read_bytes()
    snapshot = load_document(protocol_path)
    if sha256_file(protocol_path) != protocol_report["contract_sha256"] or semantic_digest(snapshot) != protocol_report["semantic_sha256"]:
        raise ValueError("complete frozen protocol changed after validation")
    if required_operations is not None and (not isinstance(required_operations, (list, tuple)) or not all(isinstance(item, str) for item in required_operations)):
        raise ValueError("explicit required operations must be an array of IDs")
    required = list(dict.fromkeys(protocol_report["required_A_operations"] + list(required_operations or [])))
    mapping = protocol_report["mapping_validation"]
    bindings = {"project_id": protocol_report["project_id"], "project_root": str(Path(project_root).resolve()),
                "protocol_input": file_binding(protocol_path), "protocol_original_text": original.decode("utf-8"), "protocol_snapshot": snapshot,
                "protocol_semantic_sha256": protocol_report["semantic_sha256"], "run_spec_sha256": protocol_report["run_spec_sha256"],
                "design_id": protocol_report["design_id"], "model_id": protocol_report["model_id"], "target_id": protocol_report["target_id"],
                "model_identity": protocol_report["model_identity"], "bound_files": protocol_report["bound_files"],
                "implementation_receipt": file_binding(protocol_report["implementation_receipt_path"]),
                "environment_profile": file_binding(environment_profile), "environment_receipt": file_binding(Path(environment_profile).parent / "receipt.json"),
                "simulation_profile": file_binding(simulation_profile), "simulation_profile_receipt": file_binding(Path(simulation_profile).parent / contract()["evidence"]["profile_receipt"]),
                "required_A_operations": required}
    case = {"case_id": "primary", "expectation": "success", "run_spec": protocol_report["run_spec"], "build_spec": mapping["build_spec"],
            "simulation_timeout": simulation_timeout, "warning_policy": protocol_report["run_spec"]["warning_policy"]}
    return make_request(executable, directory, environment_profile=environment_profile, mode="primary", cases=[case], bindings=bindings)


def verify_primary_bindings(request, *, historical_start=None):
    """Check approved sources plus current or execution-time A/E requirements."""
    from validate_implementation_receipt import _bound_external, validate_implementation_receipt
    bindings = request["bindings"]
    expected = {"project_id", "project_root", "protocol_input", "protocol_original_text", "protocol_snapshot", "protocol_semantic_sha256", "run_spec_sha256", "design_id", "model_id", "target_id", "model_identity", "bound_files", "implementation_receipt", "environment_profile", "environment_receipt", "simulation_profile", "simulation_profile_receipt", "required_A_operations"}
    if set(bindings) != expected or len(request["cases"]) != 1 or request["cases"][0]["case_id"] != "primary" or request["cases"][0]["expectation"] != "success":
        raise ValueError("primary simulation exact input surface differs")
    root = Path(bindings["project_root"]).resolve()
    if not Path(request["output_directory"]).resolve().is_relative_to(root):
        raise ValueError("simulation output directory leaves project root")
    protocol_path = _bound_external(bindings["protocol_input"], root)
    if protocol_path.read_bytes() != bindings["protocol_original_text"].encode("utf-8") or canonical_digest(load_document(protocol_path)) != canonical_digest(bindings["protocol_snapshot"]):
        raise ValueError("full frozen protocol input changed")
    for binding in bindings["bound_files"]:
        _bound_external(binding, root)
    for key in ("environment_profile", "environment_receipt", "simulation_profile", "simulation_profile_receipt"):
        _bound_external(bindings[key])
    d_path = _bound_external(bindings["implementation_receipt"], root)
    report = validate_simulation_protocol(protocol_path, project_root=root, require_frozen=True)
    if not report["valid"] or not report["execution_ready"]:
        raise ValueError("current approved frozen protocol required: " + "; ".join(report["errors"] + report["missing_gates"]))
    for field in ("project_id", "design_id", "model_id", "target_id", "model_identity", "run_spec_sha256"):
        if canonical_digest(report[field]) != canonical_digest(bindings[field]):
            raise ValueError("primary protocol identity changed: " + field)
    if report["semantic_sha256"] != bindings["protocol_semantic_sha256"] or canonical_digest(report["bound_files"]) != canonical_digest(bindings["bound_files"]) or canonical_digest(report["run_spec"]) != canonical_digest(request["cases"][0]["run_spec"]) or _path(report["implementation_receipt_path"]) != _path(d_path):
        raise ValueError("primary protocol semantic, source closure, native model or run_spec changed")
    required = bindings["required_A_operations"]
    if not isinstance(required, list) or not set(report["required_A_operations"]) <= set(required):
        raise ValueError("required protocol A operations were dropped")
    a = validate_environment(bindings["environment_profile"]["path"], required_operations=required, now=historical_start, expected_host=request["host_fingerprint"])
    e = validate_simulation_profile(bindings["simulation_profile"]["path"], now=historical_start, required_solver=report["run_spec"]["solver"]["name"])
    if not a["valid"] or not e["valid"]:
        raise ValueError("required independent A/E operation qualifications failed: " + "; ".join(a["errors"] + e["errors"]))
    ar = load_document(bindings["environment_profile"]["path"])["runtime"]
    if not same_runtime(ar, e["runtime"]) or _path(request["matlab_executable"]) != _path(e["runtime"]["executable"]):
        raise ValueError("primary A/E runtime and requested executable differ")
    d = validate_implementation_receipt(d_path, project_root=root, mapping_report=report["mapping_validation"])
    if not d["valid"]:
        raise ValueError("historical D implementation identity failed: " + "; ".join(d["errors"]))
    if not same_runtime(load_document(d_path)["runtime"], e["runtime"]):
        raise ValueError("approved D implementation and E runtime differ")
    return report, e["runtime"]


def finish_task_request(request, process):
    directory, names = Path(request["output_directory"]), contract()["evidence"]
    raw = load_document(directory / names["raw"])
    (directory / "protocol-original.yaml").write_bytes(request["bindings"]["protocol_original_text"].encode("utf-8"))
    write_json(directory / "protocol-snapshot.json", request["bindings"]["protocol_snapshot"])
    normalization_error = None
    try:
        artifacts = artifact_manifest(directory, raw, include_protocol=True)
        runtime = observed_runtime(raw, request)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        normalization_error = str(error)
        artifacts = artifact_manifest(directory, {"cases": []}, include_protocol=True)
        runtime = None
    receipt = {"schema_version": 1, "run_id": request["run_id"], "project_id": request["bindings"]["project_id"],
               "protocol_semantic_sha256": request["bindings"]["protocol_semantic_sha256"], "run_spec_sha256": request["bindings"]["run_spec_sha256"],
               "sources": request["sources"], "process": process, "runtime": runtime, "artifacts": artifacts}
    if normalization_error:
        receipt["normalization_error"] = normalization_error
    path = directory / names["run_receipt"]
    write_json(path, receipt)
    return path


def run_simulation(protocol_path, executable, directory, *, environment_profile, simulation_profile, project_root=None, timeout=240, simulation_timeout=60, required_operations=None):
    root = Path(project_root or Path(protocol_path).resolve().parent).resolve()
    report = validate_simulation_protocol(protocol_path, project_root=root, require_frozen=True)
    if not report["valid"] or not report["execution_ready"]:
        raise ValueError("current frozen protocol is not execution_ready: " + "; ".join(report["errors"] + report["missing_gates"]))
    request = make_task_request(protocol_path, executable, directory, report, environment_profile, simulation_profile, project_root=root, simulation_timeout=simulation_timeout, required_operations=required_operations)
    verify_primary_bindings(request)
    process = execute_request(request, timeout=timeout)
    receipt = finish_task_request(request, process)
    from validate_simulation_receipt import validate_simulation_receipt
    result = validate_simulation_receipt(receipt, project_root=root, protocol_report=report)
    result.update(receipt_path=str(receipt), raw_path=str(Path(directory) / contract()["evidence"]["raw"]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol", type=Path)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--matlab-executable", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--environment-profile", required=True, type=Path)
    parser.add_argument("--simulation-profile", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument("--simulation-timeout", type=float, default=60)
    parser.add_argument("--require-operation", action="append", default=[])
    args = parser.parse_args()
    try:
        result = run_simulation(args.protocol, args.matlab_executable, args.output_dir, environment_profile=args.environment_profile, simulation_profile=args.simulation_profile, project_root=args.project_root, timeout=args.timeout, simulation_timeout=args.simulation_timeout, required_operations=args.require_operation)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result = {"valid": False, "run_complete": False, "primary_run_complete": False, "criteria_satisfied": False, "errors": [str(error)]}
    emit(result)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
