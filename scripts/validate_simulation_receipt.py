"""Read a historical primary simulation, recomputing outputs and declared criteria."""
from __future__ import annotations

import argparse
from pathlib import Path

from runtime_common import canonical_digest, emit, load_document, sha256_file
from validate_implementation_receipt import same_runtime
from validate_simulation_profile import assert_case, contract, observed_runtime, record_array, validate_evidence_chain


def validate_simulation_receipt(receipt_path, *, project_root=None, protocol_report=None):
    result = {"valid": False, "run_complete": False, "primary_run_complete": False, "criteria_satisfied": False,
              "receipt_path": None, "receipt_sha256": None, "model_path": None, "model_sha256": None,
              "raw_path": None, "data_path": None, "mat_path": None, "output_paths": [], "metrics": [],
              "project_id": None, "protocol_path": None, "protocol_sha256": None, "protocol_semantic_sha256": None,
              "run_spec_sha256": None, "model_identity": None, "errors": []}
    try:
        path, names = Path(receipt_path).resolve(), contract()["evidence"]
        if path.name != names["run_receipt"]:
            raise ValueError("unexpected simulation receipt filename")
        request, raw, receipt, times = validate_evidence_chain(path)
        if request["mode"] != "primary":
            raise ValueError("not a task-specific primary simulation receipt")
        from run_simulation import verify_primary_bindings
        from probe_simulation import artifact_manifest
        report, runtime = verify_primary_bindings(request, historical_start=times[0])
        bindings = request["bindings"]
        if project_root is not None and Path(bindings["project_root"]).resolve() != Path(project_root).resolve():
            raise ValueError("primary simulation project root differs")
        if canonical_digest(receipt["artifacts"]) != canonical_digest(artifact_manifest(path.parent, raw, include_protocol=True)):
            raise ValueError("primary simulation exact artifact set differs")
        if (path.parent / "protocol-original.yaml").read_bytes() != bindings["protocol_original_text"].encode("utf-8") or canonical_digest(load_document(path.parent / "protocol-snapshot.json")) != canonical_digest(bindings["protocol_snapshot"]):
            raise ValueError("captured full primary protocol differs")
        for field in ("project_id", "protocol_semantic_sha256", "run_spec_sha256"):
            if receipt.get(field) != bindings[field]:
                raise ValueError("primary receipt identity differs: " + field)
        if not same_runtime(observed_runtime(raw, request), runtime) or canonical_digest(receipt["runtime"]) != canonical_digest(observed_runtime(raw, request)):
            raise ValueError("actual primary simulation runtime/function identity differs")
        cases = record_array(raw.get("cases"), "raw.cases")
        if len(cases) != 1:
            raise ValueError("one primary task case required")
        checked = assert_case(cases[0], request["cases"][0], path.parent, request["run_id"])
        result.update(run_complete=checked["complete"], criteria_satisfied=checked["criteria_satisfied"], metrics=checked["metrics"])
        if not checked["criteria_satisfied"]:
            raise ValueError("predeclared primary run metric criteria failed")
        if protocol_report is not None and any(canonical_digest(protocol_report[field]) != canonical_digest(report[field]) for field in ("project_id", "contract_sha256", "semantic_sha256", "run_spec_sha256", "bound_files", "model_identity")):
            raise ValueError("supplied current protocol report differs from primary source bindings")
        actual = cases[0]
        result.update(valid=True, primary_run_complete=True, receipt_path=str(path), receipt_sha256=sha256_file(path),
                      model_path=report["native_model_path"], model_sha256=report["native_model_sha256"], raw_path=str(path.parent / names["raw"]),
                      data_path=str(path.parent / actual["data_file"]), mat_path=str(path.parent / actual["mat_file"]),
                      output_paths=[str(path.parent / item["csv_file"]) for item in checked["outputs"]], project_id=report["project_id"],
                      protocol_path=report["contract_path"], protocol_sha256=report["contract_sha256"], protocol_semantic_sha256=report["semantic_sha256"],
                      run_spec_sha256=report["run_spec_sha256"], model_identity=report["model_identity"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result["errors"].append(str(error))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--project-root", type=Path)
    args = parser.parse_args()
    result = validate_simulation_receipt(args.path, project_root=args.project_root)
    emit(result)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
