"""Complete synthetic native chains for consumer tests; no MATLAB qualification."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from probe_environment import write_json
from probe_implementation import artifact_manifest, make_request
from run_implementation import finish_task_request, make_task_request
from runtime_common import load_document, sha256_file
from validate_domain_mapping import validate_domain_mapping
from validate_environment import utc_text
from validate_implementation_profile import contract, derive_profile


def synthetic_structure(spec, directory, runtime):
    directory, runtime = Path(directory), Path(runtime)
    library = runtime / "toolbox" / "simulink" / "blocks" / "library" / "simulink.slx"
    library.parent.mkdir(parents=True, exist_ok=True)
    if not library.exists():
        library.write_bytes(b"SYNTHETIC LIBRARY; CONTRACT TEST ONLY\n")
    model = directory / (spec["model_name"] + ".slx")
    model.write_bytes(b"SYNTHETIC MODEL PLACEHOLDER; NO MATLAB EXECUTION\n")
    counts = {"Inport": (0, 1), "Outport": (1, 0), "Constant": (0, 1), "Gain": (1, 1), "Sum": (2, 1), "Integrator": (1, 1)}
    return {"schema_version": 1, "model_name": spec["model_name"], "diagram_type": "model", "model_file": str(model.resolve()),
        "library_file": str(library.resolve()), "model_workspace_source": "Model File",
        "callbacks": {key: "" for key in ("PreLoadFcn", "PostLoadFcn", "InitFcn", "StartFcn", "StopFcn", "PreSaveFcn", "PostSaveFcn", "CloseFcn")},
        "blocks": [{**item, "source": contract()["supported_blocks"][item["type"]]["source"],
                    "ports": {"inport_count": counts[item["type"]][0], "outport_count": counts[item["type"]][1]},
                    "mask": "off", "reference_model": ""} for item in spec["blocks"]],
        "connections": spec["connections"],
        "parameters": [{**item, "unit": item["unit"] or "", "class": "Simulink.Parameter"} for item in spec["parameters"]],
        "updated_before_save": True, "saved": True, "closed_before_reload": True, "reopened": True,
        "updated_after_reload": True, "simulation_run": False}


def _evidence(request, runtime, *, reference=None):
    reference = reference or datetime.now(timezone.utc) - timedelta(seconds=4)
    directory = Path(request["output_directory"])
    directory.mkdir(parents=True, exist_ok=False)
    names = contract()["evidence"]
    write_json(directory / names["input"], request)
    (directory / names["log"]).write_text("SYNTHETIC CONTRACT TEST EVIDENCE; NO MATLAB EXECUTION\n", encoding="utf-8")
    functions = []
    for name in contract()["required_functions"]:
        path = Path(runtime["matlabroot"]) / "toolbox" / "fixture" / (name + ".m")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("% synthetic contract test function identity\n", encoding="utf-8")
        functions.append({"name": name, "path": str(path.resolve())})
    task = request["mode"] == "implementation"
    raw = {"schema_version": 1, "run_id": request["run_id"], "status": "completed", "channel": "matlab_batch",
        "host_fingerprint": request["host_fingerprint"], "input_identity": request["input_identity"], "source_identity": request["source_identity"],
        "started_at": utc_text(reference - timedelta(seconds=0.05 if task else 1)), "finished_at": utc_text(reference), "simulation_run": False,
        "runtime": {key: runtime[key] for key in ("release", "version", "matlabroot", "platform")},
        "installed_products": [{"Name": "MATLAB", "Version": "25.2"}, {"Name": "Simulink", "Version": "25.2"}],
        "licenses_inuse": [{"feature": "matlab"}, {"feature": "simulink"}],
        "license_test": 1, "functions": functions, "cases": []}
    for case in request["cases"]:
        actual = {"case_id": case["case_id"], "attempted": True, "call_success": not case["expect_failure"],
                  "error": {"identifier": "PhaseD:InvalidPort", "message": "SYNTHETIC expected bad port rejection"} if case["expect_failure"] else {},
                  "structure_file": "", "model_file": ""}
        if not case["expect_failure"]:
            actual["structure_file"] = case["case_id"] + "-structure.json"
            actual["model_file"] = case["build_spec"]["model_name"] + ".slx"
            write_json(directory / actual["structure_file"], synthetic_structure(case["build_spec"], directory, runtime["matlabroot"]))
        raw["cases"].append(actual)
    write_json(directory / names["raw"], raw)
    process = {"started_at": utc_text(reference - timedelta(seconds=0.1 if task else 2)), "finished_at": utc_text(reference + timedelta(milliseconds=100)),
               "process_state": "completed", "exit_code": 0, "pid": 0, "command": ["SYNTHETIC CONTRACT TEST; NO MATLAB"]}
    return raw, process


def make_implementation_profile(root, a_profile, *, age_hours=0):
    runtime = load_document(a_profile)["runtime"]
    directory = Path(root).resolve()
    request = make_request(runtime["executable"], directory)
    reference = datetime.now(timezone.utc) - timedelta(hours=age_hours, seconds=12)
    raw, process = _evidence(request, runtime, reference=reference)
    profile = derive_profile(raw, request, process)
    names = contract()["evidence"]
    path = directory / names["profile"]
    write_json(path, profile)
    receipt = {"schema_version": 1, "run_id": request["run_id"], "sources": request["sources"], "process": process,
               "runtime_fingerprint": profile["runtime"]["fingerprint"], "artifacts": artifact_manifest(directory, raw, include_profile=True)}
    write_json(directory / names["receipt"], receipt)
    return path


def make_implementation_receipt(root, mapping_path, a_profile, d_profile, *, age_hours=0):
    mapping = validate_domain_mapping(mapping_path, require_mapped=True)
    assert mapping["valid"] and mapping["build_ready"], mapping
    runtime = load_document(d_profile)["runtime"]
    directory = Path(root).resolve()
    request = make_task_request(runtime["executable"], directory, mapping, a_profile, d_profile, mapping_path=mapping_path)
    reference = datetime.now(timezone.utc) - timedelta(hours=age_hours, seconds=0.2)
    _, process = _evidence(request, runtime, reference=reference)
    return finish_task_request(request, process, runtime)
