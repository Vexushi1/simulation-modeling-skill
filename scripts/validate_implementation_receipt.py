"""Read historical native structure evidence without executing or advancing state."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from runtime_common import canonical_digest, contained_path, emit, load_document, sha256_file
from validate_environment import _official_function, _path, _time, runtime_identity, validate_environment
from validate_implementation_profile import (_validate_request, assert_structure, contract, record_array, validate_raw_arrays,
    validate_build_spec, validate_implementation_profile)

RUNTIME_MATCH_FIELDS = ("release", "version", "matlabroot", "executable", "executable_sha256", "version_file_sha256", "platform")


def same_runtime(left, right):
    return all((_path(left[key]) == _path(right[key]) if key in {"matlabroot", "executable"}
                else left[key] == right[key]) for key in RUNTIME_MATCH_FIELDS)


def _bound_external(binding, root=None):
    path = Path(binding["path"]).resolve()
    if root is not None and not path.is_relative_to(Path(root).resolve()):
        raise ValueError("native task dependency leaves project root")
    if not path.is_file() or sha256_file(path) != binding["sha256"]:
        raise ValueError("native external digest mismatch: " + str(path))
    return path


def validate_implementation_receipt(path, *, project_root=None, mapping_report=None):
    result = {"valid": False, "built": False, "structure_checked": False, "implementation_ready": False,
              "receipt_path": None, "receipt_sha256": None, "model_path": None, "model_sha256": None,
              "structure_path": None, "structure_sha256": None, "errors": []}
    try:
        path = Path(path).resolve()
        directory, names = path.parent, contract()["evidence"]
        if path.name != names["structure_receipt"]:
            raise ValueError("unexpected implementation receipt filename")
        receipt = load_document(path)
        request = load_document(directory / names["input"])
        raw = load_document(directory / names["raw"])
        _validate_request(request)
        if type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
            raise ValueError("implementation raw schema version differs")
        validate_raw_arrays(raw)
        if receipt.get("normalization_error"):
            raise ValueError("implementation raw normalization failed: " + str(receipt["normalization_error"]))
        if request.get("mode") != "implementation" or _path(request["output_directory"]) != _path(directory):
            raise ValueError("not a task-specific native implementation record")
        if type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 1 or receipt.get("run_id") != request["run_id"] or canonical_digest(receipt.get("sources")) != canonical_digest(request["sources"]):
            raise ValueError("implementation receipt source/run identity differs")
        for key in ("run_id", "channel", "host_fingerprint", "input_identity", "source_identity"):
            if raw.get(key) != request.get(key):
                raise ValueError("implementation raw identity differs: " + key)
        process = receipt["process"]
        if process.get("process_state") != "completed" or type(process.get("exit_code")) is not int or process["exit_code"] != 0:
            raise ValueError("implementation process failed or did not complete")
        times = [_time(process["started_at"]), _time(raw["started_at"]), _time(raw["finished_at"]), _time(process["finished_at"])]
        if not times[0] <= times[1] <= times[2] <= times[3] or times[0] == times[3]:
            raise ValueError("implementation process/raw time order is invalid")
        if times[-1] > datetime.now(timezone.utc):
            raise ValueError("implementation evidence is future dated")
        if raw.get("status") != "completed" or raw.get("simulation_run") is not False:
            raise ValueError("implementation did not finish as a structure-only operation")
        bindings = request["bindings"]
        # Revalidate qualifications at the start of this historical execution,
        # not against today's TTL. Bound bytes and source identities still matter.
        a_path = _bound_external(bindings["environment_profile"])
        d_path = _bound_external(bindings["implementation_profile"])
        _bound_external(bindings["environment_receipt"])
        _bound_external(bindings["implementation_profile_receipt"])
        a = validate_environment(a_path, expected_root=raw["runtime"]["matlabroot"], now=times[0], expected_host=request["host_fingerprint"])
        d = validate_implementation_profile(d_path, expected_root=raw["runtime"]["matlabroot"], now=times[0], expected_host=request["host_fingerprint"])
        if not a["valid"] or not d["valid"]:
            raise ValueError("qualification was not valid at execution: " + "; ".join(a["errors"] + d["errors"]))
        ar, dr = load_document(a_path)["runtime"], d["runtime"]
        if not same_runtime(ar, dr) or not same_runtime(dr, receipt["runtime"]):
            raise ValueError("implementation and qualification runtime identities differ")
        if _path(request["matlab_executable"]) != _path(dr["executable"]):
            raise ValueError("implementation executable differs from qualified runtime")
        if any(raw["runtime"][key] != dr[key] for key in ("release", "version", "platform")) or _path(raw["runtime"]["matlabroot"]) != _path(dr["matlabroot"]):
            raise ValueError("actual implementation runtime differs from qualified runtime")
        from validate_domain_mapping import semantic_digest
        snapshot = load_document(directory / "mapping-snapshot.json")
        if semantic_digest(snapshot) != bindings["mapping_semantic_sha256"] or canonical_digest(snapshot) != canonical_digest(bindings["mapping_snapshot"]):
            raise ValueError("mapping snapshot does not match native input semantic identity")
        original = directory / "mapping-original.yaml"
        if (original.read_bytes() != bindings["mapping_original_text"].encode("utf-8") or
                sha256_file(original) != bindings["mapping_input"]["sha256"] or
                semantic_digest(load_document(original)) != bindings["mapping_semantic_sha256"]):
            raise ValueError("complete original mapping capture differs from its bound input or semantic identity")
        if receipt.get("mapping_semantic_sha256") != bindings["mapping_semantic_sha256"] or receipt.get("project_id") != bindings["project_id"]:
            raise ValueError("implementation receipt mapping/project identity differs")
        for binding in bindings["bound_files"]:
            _bound_external(binding, project_root)
        cases, actual_cases = request["cases"], record_array(raw.get("cases"), "raw.cases")
        if len(cases) != 1 or len(actual_cases) != 1 or cases[0]["expect_failure"] is not False or actual_cases[0].get("call_success") is not True:
            raise ValueError("successful task-specific native case required")
        spec, actual = cases[0]["build_spec"], actual_cases[0]
        validate_build_spec(spec)
        if cases[0]["case_id"] != "implementation" or actual.get("case_id") != "implementation" or actual.get("attempted") is not True:
            raise ValueError("implementation case identity or attempt differs")
        if canonical_digest(spec) != bindings["build_spec_sha256"] or receipt.get("build_spec_sha256") != bindings["build_spec_sha256"]:
            raise ValueError("implementation build specification digest differs")
        if receipt.get("parameter_provenance_sha256") != bindings["parameter_provenance_sha256"]:
            raise ValueError("implementation parameter registry digest differs")
        manifest = receipt["artifacts"]
        expected = {"input": names["input"], "raw": names["raw"], "log": names["log"],
                    "mapping_snapshot": "mapping-snapshot.json", "mapping_original": "mapping-original.yaml", "implementation_model": spec["model_name"] + ".slx",
                    "implementation_structure": "implementation-structure.json"}
        if set(manifest) != set(expected):
            raise ValueError("implementation artifact manifest differs from the exact required set")
        for key, filename in expected.items():
            binding = manifest[key]
            if binding.get("file") != filename or sha256_file(contained_path(directory, filename)) != binding.get("sha256"):
                raise ValueError("implementation artifact digest mismatch: " + key)
        if actual.get("model_file") != expected["implementation_model"] or actual.get("structure_file") != expected["implementation_structure"]:
            raise ValueError("implementation raw artifact names differ")
        structure_path = directory / expected["implementation_structure"]
        structure = load_document(structure_path)
        assert_structure(structure, spec, directory, raw["runtime"]["matlabroot"])
        functions = record_array(raw.get("functions"), "raw.functions")
        resolutions = {item["name"]: item["path"] for item in functions}
        if (set(resolutions) != set(contract()["required_functions"]) or len(resolutions) != len(functions) or
                not all(_official_function(value, raw["runtime"]["matlabroot"]) for value in resolutions.values())):
            raise ValueError("actual native function resolutions differ from the qualified surface")
        observed_runtime = runtime_identity({**raw, "operations": [{"functions": functions, "operation_id": "simulink.library_load",
                                             "output": {"file_name": structure["library_file"]}}]}, request["matlab_executable"])
        if canonical_digest(observed_runtime) != canonical_digest(dr) or canonical_digest(receipt["runtime"]) != canonical_digest(dr):
            raise ValueError("actual native function/library runtime identity differs from qualification")
        if mapping_report is not None:
            for field in ("project_id", "semantic_sha256", "parameter_provenance_sha256", "build_spec_sha256"):
                expected_value = bindings["mapping_semantic_sha256"] if field == "semantic_sha256" else bindings[field]
                if mapping_report.get(field) != expected_value:
                    raise ValueError("current mapping differs from receipt: " + field)
            if canonical_digest(mapping_report.get("mapping_snapshot")) != canonical_digest(snapshot) or canonical_digest(mapping_report.get("build_spec")) != canonical_digest(spec):
                raise ValueError("current mapping snapshot or compiled build_spec differs")
            if canonical_digest(mapping_report.get("bound_files")) != canonical_digest(bindings["bound_files"]):
                raise ValueError("current mapping source closure differs")
        result.update(valid=True, built=True, structure_checked=True, implementation_ready=mapping_report is not None,
                      receipt_path=str(path), receipt_sha256=sha256_file(path), model_path=str(directory / expected["implementation_model"]),
                      model_sha256=manifest["implementation_model"]["sha256"], structure_path=str(structure_path),
                      structure_sha256=manifest["implementation_structure"]["sha256"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result["errors"].append(str(error))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--project-root", type=Path)
    args = parser.parse_args()
    result = validate_implementation_receipt(args.path, project_root=args.project_root)
    emit(result)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
