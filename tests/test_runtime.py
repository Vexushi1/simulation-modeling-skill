"""Contract/consumer tests with simulated evidence; these do not qualify MATLAB."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import sys

import pytest

import probe_environment as probe
import validate_environment as environment
from runtime_common import ROOT, canonical_digest, host_fingerprint, load_document, sha256_file

CORE = ["matlab.basic_execution", "simulink.library_load"]


def _finish(profile_path, raw, request, process):
    contract = environment._contract()
    names = contract["evidence_policy"]["artifacts"]
    directory = profile_path.parent
    probe.write_json(directory / names["input"], request)
    probe.write_json(directory / names["raw"], raw)
    profile = environment.build_profile(raw, request, process, contract)
    probe.write_json(profile_path, profile)
    receipt = {
        "schema_version": 1, "run_id": request["run_id"], "channel": "matlab_batch",
        "host_fingerprint": request["host_fingerprint"], "input_identity": request["input_identity"],
        "sources": request["sources"], "process": process,
        "runtime_fingerprint": profile["runtime"]["fingerprint"],
        "artifacts": {kind: {"file": filename, "sha256": sha256_file(directory / filename)}
                      for kind, filename in names.items()},
    }
    probe.write_json(directory / "receipt.json", receipt)


def make_profile(tmp_path, *, include_statistics=False, failing_operations=(), age_hours=0, host=None) -> Path:
    """Build a complete synthetic chain for validator/router tests, never run MATLAB."""
    tmp_path = Path(tmp_path)
    runtime = tmp_path / "matlab"
    executable = runtime / "bin" / "matlab.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"SIMULATED MATLAB EXECUTABLE FOR CONTRACT TESTS\n")
    (runtime / "VersionInfo.xml").write_text(
        "<MathWorks_version_info><version>25.2.0.2998904</version><release>R2025b</release></MathWorks_version_info>",
        encoding="utf-8",
    )
    directory = tmp_path / "evidence"
    directory.mkdir()
    request = probe.make_request(executable, directory, include_statistics=include_statistics, host=host)
    reference = datetime.now(timezone.utc) - timedelta(hours=age_hours, seconds=1)
    raw = {
        "schema_version": 1, "run_id": request["run_id"], "status": "completed", "channel": "matlab_batch",
        "host_fingerprint": request["host_fingerprint"], "input_identity": request["input_identity"],
        "source_identity": canonical_digest(request["sources"]),
        "started_at": environment.utc_text(reference - timedelta(seconds=1)),
        "finished_at": environment.utc_text(reference),
        "runtime": {"release": "R2025b", "version": "25.2.0.2998904 (R2025b)",
                    "matlabroot": str(runtime.resolve()), "platform": "SYNTHETIC_TEST_PLATFORM"},
        "installed_products": [{"Name": "MATLAB", "Version": "25.2"}, {"Name": "Simulink", "Version": "25.2"}],
        "licenses_inuse": [{"feature": "matlab"}, {"feature": "simulink"}],
        "operations": [],
    }
    if include_statistics:
        raw["installed_products"].append({"Name": "Statistics and Machine Learning Toolbox", "Version": "25.2"})
        raw["licenses_inuse"].append({"feature": "statistics_toolbox"})
    for spec in request["operation_specs"]:
        operation_id = spec["operation_id"]
        functions = []
        for function in spec["functions"]:
            function_path = runtime / "toolbox" / "fixture" / (function + ".m")
            function_path.parent.mkdir(parents=True, exist_ok=True)
            function_path.write_text("% synthetic test fixture\n", encoding="utf-8")
            functions.append({"name": function, "path": str(function_path.resolve())})
        if operation_id == CORE[0]:
            output = {"value": 6}
        elif operation_id == CORE[1]:
            library = runtime / "toolbox" / "simulink" / "blocks" / "library" / "simulink.slx"
            library.parent.mkdir(parents=True)
            library.write_bytes(b"SYNTHETIC LIBRARY IDENTITY ONLY; NOT A SIMULINK MODEL")
            output = {"library_name": "simulink", "loaded": True, "diagram_type": "library",
                      "file_name": str(library.resolve()), "simulation_run": False,
                      "model_saved": False, "closed_without_save": True}
        elif operation_id == "statistics.normcdf":
            output = {"value": 0.5}
        elif operation_id == "statistics.fitlm":
            output = {"coefficients": [1, 2], "predictions": [1, 5, 11], "rmse": 0.1}
        else:
            output = {"sample": [[(row + 0.5) / 6, ((row + 2) % 6 + 0.5) / 6] for row in range(6)]}
        failed = operation_id in failing_operations
        raw["operations"].append({
            "operation_id": operation_id, "parameters": spec["input"], "license_test": 1,
            "functions": functions, "attempted": True, "call_success": not failed,
            "output": None if failed else output,
            "error": {"identifier": "Fixture:CallFailed", "message": "simulated call failure"} if failed else None,
        })
    (directory / "matlab-batch.log").write_text("SIMULATED CONTRACT TEST EVIDENCE; NO MATLAB EXECUTION\n", encoding="utf-8")
    process = {"started_at": environment.utc_text(reference - timedelta(seconds=2)),
               "finished_at": environment.utc_text(reference + timedelta(milliseconds=500)),
               "process_state": "completed", "exit_code": 0, "pid": 0, "command": ["simulated fixture"]}
    profile_path = directory / "profile.json"
    _finish(profile_path, raw, request, process)
    return profile_path


def _parts(profile):
    directory = profile.parent
    return (load_document(directory / "raw-probe.json"), load_document(directory / "inputs.json"),
            load_document(directory / "receipt.json")["process"])


def _rebind_profile(profile_path, profile):
    probe.write_json(profile_path, profile)
    receipt_path = profile_path.parent / "receipt.json"
    receipt = load_document(receipt_path)
    receipt["artifacts"]["profile"]["sha256"] = sha256_file(profile_path)
    probe.write_json(receipt_path, receipt)


def test_core_profile_and_receipt_are_valid_and_do_not_qualify_simulation(tmp_path):
    profile = make_profile(tmp_path)
    result = environment.validate_environment(profile)
    assert result["valid"] and result["runtime_assured"] and result["profile_current"]
    assert result["qualified_operations"] == CORE
    assert result["receipt_sha256"] == sha256_file(profile.parent / "receipt.json")
    assert result["profile_sha256"] == sha256_file(profile)
    assert "simulink.simulation_execution" not in result["qualified_operations"]
    assert set(load_document(profile)["operations"]) == set(CORE)


def test_optional_failure_keeps_core_current_but_explicit_requirement_fails(tmp_path):
    profile = make_profile(tmp_path, include_statistics=True, failing_operations=("statistics.fitlm",))
    core = environment.validate_environment(profile)
    assert core["valid"] and core["runtime_assured"]
    assert "statistics.fitlm" not in core["qualified_operations"]
    explicit = environment.validate_environment(profile, required_operations=["statistics.fitlm"])
    assert not explicit["valid"] and explicit["runtime_assured"] and explicit["profile_current"]
    raw = load_document(profile.parent / "raw-probe.json")
    assert next(op for op in raw["operations"] if op["operation_id"] == "statistics.fitlm")["error"]["message"]


def test_statistics_can_recover_on_a_new_probe_without_historical_quarantine(tmp_path):
    failed = make_profile(tmp_path / "failed", include_statistics=True, failing_operations=("statistics.fitlm",))
    recovered = make_profile(tmp_path / "recovered", include_statistics=True)
    before = failed.read_bytes()
    assert not environment.validate_environment(failed, required_operations=["statistics.fitlm"])["valid"]
    assert environment.validate_environment(recovered, required_operations=["statistics.fitlm"])["valid"]
    assert failed.read_bytes() == before


@pytest.mark.parametrize("file", ["inputs.json", "raw-probe.json", "matlab-batch.log", "profile.json"])
def test_bound_artifact_byte_changes_invalidate_profile(tmp_path, file):
    profile = make_profile(tmp_path)
    path = profile.parent / file
    path.write_bytes(path.read_bytes() + b"\n")
    result = environment.validate_environment(profile)
    assert not result["valid"] and not result["profile_current"]
    assert any("digest mismatch" in error for error in result["errors"])


@pytest.mark.parametrize("bad", ["{", "[]", '{"schema_version":1,"schema_version":1}', '{"value":NaN}'])
def test_malformed_duplicate_or_nonfinite_json_is_rejected(tmp_path, bad):
    profile = make_profile(tmp_path)
    profile.write_text(bad, encoding="utf-8")
    assert not environment.validate_environment(profile)["valid"]


def test_expired_future_and_reversed_times_are_rejected(tmp_path):
    expired = make_profile(tmp_path / "expired", age_hours=25)
    assert not environment.validate_environment(expired)["profile_current"]
    profile = make_profile(tmp_path / "current")
    result = environment.validate_environment(profile, now=datetime.now(timezone.utc) - timedelta(hours=1))
    assert not result["valid"] and any("future" in error for error in result["errors"])
    raw, request, process = _parts(profile)
    process["finished_at"] = process["started_at"]
    _finish(profile, raw, request, process)
    assert not environment.validate_environment(profile)["valid"]


def test_host_root_and_runtime_file_changes_are_rejected(tmp_path):
    profile = make_profile(tmp_path)
    assert not environment.validate_environment(profile, expected_host="wrong-host")["valid"]
    assert not environment.validate_environment(profile, expected_root=tmp_path / "other")["valid"]
    assert environment.validate_environment(profile, expected_host=host_fingerprint())["valid"]
    runtime = load_document(profile)["runtime"]
    Path(runtime["executable"]).write_bytes(b"runtime changed")
    assert not environment.validate_environment(profile)["profile_current"]


def test_version_and_function_file_changes_invalidate_profile(tmp_path):
    profile = make_profile(tmp_path / "version")
    Path(load_document(profile)["runtime"]["matlabroot"], "VersionInfo.xml").write_text(
        "<MathWorks_version_info><version>26.1</version><release>R2026a</release></MathWorks_version_info>", encoding="utf-8")
    assert not environment.validate_environment(profile)["valid"]
    profile = make_profile(tmp_path / "function")
    Path(load_document(profile)["runtime"]["function_files"][0]["path"]).write_bytes(b"function changed")
    assert not environment.validate_environment(profile)["profile_current"]


def test_loaded_library_byte_changes_make_previous_profile_stale(tmp_path):
    profile = make_profile(tmp_path)
    raw = load_document(profile.parent / "raw-probe.json")
    library = Path(raw["operations"][1]["output"]["file_name"])
    assert str(library) in {item["path"] for item in load_document(profile)["runtime"]["function_files"]}
    library.write_bytes(b"changed library bytes")
    result = environment.validate_environment(profile)
    assert not result["valid"] and not result["profile_current"]


@pytest.mark.parametrize("field", ["artifacts", "process"])
def test_malformed_receipt_sections_fail_with_controlled_errors(tmp_path, field):
    profile = make_profile(tmp_path)
    receipt_path = profile.parent / "receipt.json"
    receipt = load_document(receipt_path)
    receipt[field] = ["invalid receipt section"]
    probe.write_json(receipt_path, receipt)
    result = environment.validate_environment(profile)
    assert not result["valid"] and result["errors"]


def test_malformed_inventory_fails_with_controlled_errors(tmp_path):
    profile = make_profile(tmp_path)
    raw = load_document(profile.parent / "raw-probe.json")
    raw["installed_products"] = ["invalid product record"]
    probe.write_json(profile.parent / "raw-probe.json", raw)
    result = environment.validate_environment(profile)
    assert not result["valid"] and not result["runtime_assured"]


def test_current_source_changes_make_previous_evidence_stale(tmp_path, monkeypatch):
    authority = tmp_path / "authority"
    names = environment._contract()["evidence_policy"]["source_files"]
    for name in names:
        target = authority / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    monkeypatch.setattr(environment, "ROOT", authority)
    monkeypatch.setattr(probe, "ROOT", authority)
    profile = make_profile(tmp_path / "project")
    with (authority / "scripts/matlab/probe_environment.m").open("a", encoding="utf-8") as stream:
        stream.write("\n% changed probe\n")
    result = environment.validate_environment(profile)
    assert not result["profile_current"] and any("source identity" in error for error in result["errors"])


@pytest.mark.parametrize("mutation", ["license_only", "call_failed", "wrong_output", "not_resolvable", "missing_function_file", "no_install"])
def test_license_or_static_flags_cannot_establish_qualification(tmp_path, mutation):
    profile = make_profile(tmp_path)
    raw, request, process = _parts(profile)
    operation = raw["operations"][1]
    if mutation == "license_only":
        operation["attempted"] = False
        operation["call_success"] = False
    elif mutation == "call_failed":
        operation["call_success"] = False
        operation["error"] = {"message": "license checkout failed despite license test"}
    elif mutation == "wrong_output":
        operation["output"]["simulation_run"] = True
    elif mutation == "not_resolvable":
        operation["functions"][0]["path"] = ""
    elif mutation == "missing_function_file":
        operation["functions"][0]["path"] = str(Path(raw["runtime"]["matlabroot"]) / "toolbox/missing/load_system.m")
    else:
        raw["installed_products"] = [raw["installed_products"][0]]
    _finish(profile, raw, request, process)
    result = environment.validate_environment(profile)
    assert not result["valid"] and not result["runtime_assured"]
    fabricated = load_document(profile)
    fabricated["operations"][CORE[1]]["qualified"] = True
    _rebind_profile(profile, fabricated)
    assert any("qualification" in error for error in environment.validate_environment(profile)["errors"])


def test_modified_declared_inputs_and_raw_inputs_are_rejected(tmp_path):
    profile = make_profile(tmp_path)
    raw, request, process = _parts(profile)
    raw["operations"][0]["parameters"] = {"values": [1, 2, 100], "expected": 103}
    _finish(profile, raw, request, process)
    assert any("input mismatch" in error for error in environment.validate_environment(profile)["errors"])
    request["operation_specs"][0]["input"] = raw["operations"][0]["parameters"]
    request["input_identity"] = canonical_digest({key: value for key, value in request.items() if key != "input_identity"})
    raw["input_identity"] = request["input_identity"]
    _finish(profile, raw, request, process)
    assert any("specification changed" in error for error in environment.validate_environment(profile)["errors"])


@pytest.mark.parametrize("state,code", [("running", None), ("timed_out", -1), ("failed", 7)])
def test_incomplete_timeout_and_nonzero_processes_cannot_pass(tmp_path, state, code):
    profile = make_profile(tmp_path)
    raw, request, process = _parts(profile)
    process.update(process_state=state, exit_code=code)
    _finish(profile, raw, request, process)
    result = environment.validate_environment(profile)
    assert not result["valid"] and not result["runtime_assured"]


def test_lhs_dimensions_range_and_strata_are_recomputed(tmp_path):
    profile = make_profile(tmp_path, include_statistics=True)
    raw, request, process = _parts(profile)
    lhs = next(record for record in raw["operations"] if record["operation_id"] == "statistics.lhsdesign")
    lhs["output"]["sample"][1] = lhs["output"]["sample"][0]
    _finish(profile, raw, request, process)
    result = environment.validate_environment(profile, required_operations=["statistics.lhsdesign"])
    assert not result["valid"] and result["runtime_assured"]


def test_core_requirements_cannot_be_removed_and_future_operation_is_unknown(tmp_path):
    profile = make_profile(tmp_path)
    assert environment.validate_environment(profile, required_operations=[])["required_operations"] == CORE
    assert not environment.validate_environment(profile, required_operations=["simulink.simulation_execution"])["valid"]
    assert not environment.validate_environment(profile, required_operations="statistics.normcdf")["valid"]
    request = probe.make_request(tmp_path / "matlab/bin/matlab.exe", tmp_path / "new",
                                 required_operations=["statistics.normcdf"])
    assert request["required_operations"] == CORE + ["statistics.normcdf"]
    assert [spec["operation_id"] for spec in request["operation_specs"]] == CORE + ["statistics.normcdf"]


def test_runner_preserves_existing_directory_and_does_not_launch_again(tmp_path, monkeypatch):
    profile = make_profile(tmp_path)
    executable = load_document(profile)["runtime"]["executable"]
    monkeypatch.setattr(probe, "_run_process", lambda *args: pytest.fail("must not start another process"))
    before = profile.read_bytes()
    with pytest.raises(FileExistsError):
        probe.run_probe(executable, profile.parent)
    assert profile.read_bytes() == before


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), 0, -1])
def test_nonfinite_or_nonpositive_deadlines_never_launch_a_process(tmp_path, monkeypatch, timeout):
    profile = make_profile(tmp_path / "original")
    executable = load_document(profile)["runtime"]["executable"]
    monkeypatch.setattr(probe, "_run_process", lambda *args: pytest.fail("invalid deadline must not launch"))
    target = tmp_path / "invalid-timeout"
    with pytest.raises(ValueError, match="finite and positive"):
        probe.run_probe(executable, target, timeout=timeout)
    assert not target.exists()


@pytest.mark.parametrize("version_metadata", ["missing", "malformed"])
def test_failed_process_preserves_receipt_without_valid_runtime_metadata(tmp_path, monkeypatch, version_metadata):
    original = make_profile(tmp_path / "original")
    runtime = load_document(original)["runtime"]
    version_path = Path(runtime["matlabroot"]) / "VersionInfo.xml"
    if version_metadata == "missing":
        version_path.unlink()
    else:
        version_path.write_text("<invalid", encoding="utf-8")
    timestamp = environment.utc_text(datetime.now(timezone.utc) - timedelta(seconds=1))
    process = {"started_at": timestamp, "finished_at": timestamp, "process_state": "failed",
               "exit_code": 7, "pid": 0, "command": ["simulated failure"]}
    monkeypatch.setattr(probe, "_run_process", lambda *args: (process, "simulated launch failure\n"))
    directory = tmp_path / "failed-evidence"
    result = probe.run_probe(runtime["executable"], directory)
    assert not result["valid"] and not result["runtime_assured"]
    assert {"inputs.json", "raw-probe.json", "matlab-batch.log", "profile.json", "receipt.json"}.issubset(
        {path.name for path in directory.iterdir()})
    assert load_document(directory / "raw-probe.json")["status"] == "failed"
    assert load_document(directory / "receipt.json")["process"]["exit_code"] == 7
    assert result["receipt_sha256"] == sha256_file(directory / "receipt.json")


def test_invalid_native_report_is_preserved_and_bound_to_failed_receipt(tmp_path, monkeypatch):
    original = make_profile(tmp_path / "original")
    executable = load_document(original)["runtime"]["executable"]
    timestamp = environment.utc_text(datetime.now(timezone.utc) - timedelta(seconds=1))
    process = {"started_at": timestamp, "finished_at": timestamp, "process_state": "completed",
               "exit_code": 0, "pid": 0, "command": ["simulated invalid report"]}
    def malformed_process(command, directory, timeout):
        (Path(directory) / "raw-probe.json").write_bytes(b"{invalid native JSON")
        return process, "simulated malformed JSON\n"
    monkeypatch.setattr(probe, "_run_process", malformed_process)
    directory = tmp_path / "malformed-evidence"
    result = probe.run_probe(executable, directory)
    assert not result["valid"] and not result["runtime_assured"]
    assert (directory / "raw-probe.json").read_bytes() == b"{invalid native JSON"
    receipt = load_document(directory / "receipt.json")
    assert receipt["artifacts"]["raw"]["sha256"] == sha256_file(directory / "raw-probe.json")
    assert "normalization_error" in load_document(directory / "profile.json")


def test_actual_child_exit_and_timeout_are_captured_without_matlab(tmp_path):
    failed, _ = probe._run_process([sys.executable, "-c", "raise SystemExit(7)"], tmp_path, 10)
    assert failed["process_state"] == "failed" and failed["exit_code"] == 7
    timeout, _ = probe._run_process([sys.executable, "-c", "import time; time.sleep(10)"], tmp_path, 0.05)
    assert timeout["process_state"] == "timed_out" and timeout["exit_code"] != 0


def test_matlab_paths_are_passed_without_a_shell_and_apostrophes_are_quoted(tmp_path):
    command = probe.matlab_command(tmp_path / "matlab/bin/matlab.exe", tmp_path / "it's a path/inputs.json", tmp_path / "log file.log")
    assert command[0].endswith("matlab.exe") and "-batch" in command
    assert "it''s a path" in command[command.index("-batch") + 1]
    assert command[-1].endswith("log file.log")
