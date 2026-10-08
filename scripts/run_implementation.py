"""Explicitly build a qualified core mapping in a new evidence directory."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import yaml

from probe_environment import write_json
from probe_implementation import artifact_manifest, execute_request, make_request
from runtime_common import emit, load_document, sha256_file
from validate_domain_mapping import semantic_digest, validate_domain_mapping
from validate_environment import _path, validate_environment
from validate_implementation_profile import contract, validate_build_spec, validate_implementation_profile
from validate_implementation_receipt import same_runtime, validate_implementation_receipt


def file_binding(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": sha256_file(path)}


def make_task_request(executable, directory, mapping_report, a_profile, d_profile, *, mapping_path):
    names = contract()["evidence"]
    spec = validate_build_spec(mapping_report["build_spec"])
    original_bytes = Path(mapping_path).read_bytes()
    original_text = original_bytes.decode("utf-8")
    if semantic_digest(yaml.safe_load(original_text)) != mapping_report["semantic_sha256"]:
        raise ValueError("complete mapping input changed after mapping validation")
    bindings = {"project_id": mapping_report["project_id"], "mapping_semantic_sha256": mapping_report["semantic_sha256"],
                "mapping_snapshot": mapping_report["mapping_snapshot"], "bound_files": mapping_report["bound_files"],
                "parameter_provenance_sha256": mapping_report["parameter_provenance_sha256"],
                "build_spec_sha256": mapping_report["build_spec_sha256"],
                "mapping_input": {"path": str(Path(mapping_path).resolve()), "sha256": hashlib.sha256(original_bytes).hexdigest()},
                "mapping_original_text": original_text,
                "environment_profile": file_binding(a_profile), "environment_receipt": file_binding(Path(a_profile).parent / "receipt.json"),
                "implementation_profile": file_binding(d_profile),
                "implementation_profile_receipt": file_binding(Path(d_profile).parent / names["receipt"])}
    return make_request(executable, directory, mode="implementation",
                        cases=[{"case_id": "implementation", "expect_failure": False, "build_spec": spec}], bindings=bindings)


def finish_task_request(request, process, runtime):
    directory, names = Path(request["output_directory"]), contract()["evidence"]
    raw = load_document(directory / names["raw"])
    write_json(directory / "mapping-snapshot.json", request["bindings"]["mapping_snapshot"])
    (directory / "mapping-original.yaml").write_bytes(request["bindings"]["mapping_original_text"].encode("utf-8"))
    artifacts = artifact_manifest(directory, raw)
    artifacts["mapping_snapshot"] = {"file": "mapping-snapshot.json", "sha256": sha256_file(directory / "mapping-snapshot.json")}
    artifacts["mapping_original"] = {"file": "mapping-original.yaml", "sha256": sha256_file(directory / "mapping-original.yaml")}
    receipt = {"schema_version": 1, "run_id": request["run_id"], "project_id": request["bindings"]["project_id"],
               "mapping_semantic_sha256": request["bindings"]["mapping_semantic_sha256"],
               "parameter_provenance_sha256": request["bindings"]["parameter_provenance_sha256"],
               "build_spec_sha256": request["bindings"]["build_spec_sha256"], "sources": request["sources"],
               "process": process, "runtime": runtime, "artifacts": artifacts}
    path = directory / names["structure_receipt"]
    write_json(path, receipt)
    return path


def run_implementation(mapping_path, executable, directory, *, environment_profile, implementation_profile,
                       project_root=None, timeout=240):
    project_root = Path(project_root or Path(mapping_path).resolve().parent).resolve()
    if not Path(directory).resolve().is_relative_to(project_root):
        raise ValueError("task implementation output directory must stay within project root")
    mapping = validate_domain_mapping(mapping_path, project_root=project_root, require_mapped=True)
    if not mapping["valid"] or not mapping["build_ready"]:
        raise ValueError("current mapping is not native build_ready: " + "; ".join(mapping["errors"] + mapping["native_missing_gates"]))
    root = Path(executable).resolve().parent.parent
    a = validate_environment(environment_profile, expected_root=root)
    d = validate_implementation_profile(implementation_profile, expected_root=root)
    if not a["valid"] or not d["valid"]:
        raise ValueError("current independent A and D qualifications required: " + "; ".join(a["errors"] + d["errors"]))
    ar = load_document(environment_profile)["runtime"]
    if not same_runtime(ar, d["runtime"]) or _path(executable) != _path(d["runtime"]["executable"]):
        raise ValueError("A/D qualification and requested executable runtime differ")
    request = make_task_request(executable, directory, mapping, environment_profile, implementation_profile, mapping_path=mapping_path)
    process = execute_request(request, timeout=timeout)
    receipt = finish_task_request(request, process, d["runtime"])
    result = validate_implementation_receipt(receipt, project_root=project_root, mapping_report=mapping)
    result["receipt_path"] = str(receipt)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mapping", type=Path)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--matlab-executable", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--environment-profile", type=Path, required=True)
    parser.add_argument("--implementation-profile", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=240)
    args = parser.parse_args()
    try:
        result = run_implementation(args.mapping, args.matlab_executable, args.output_dir,
            environment_profile=args.environment_profile, implementation_profile=args.implementation_profile,
            project_root=args.project_root, timeout=args.timeout)
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
        result = {"valid": False, "errors": [str(error)], "built": False, "structure_checked": False, "implementation_ready": False}
    emit(result)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
