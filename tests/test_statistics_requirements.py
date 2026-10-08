"""Optional/required Statistics error paths with synthetic evidence, not MATLAB qualification."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import pytest

import probe_environment as probe
from resolve_runtime import resolve_runtime
from runtime_common import canonical_digest, load_document, sha256_file
import validate_environment as environment
from test_runtime import CORE, make_profile


STATISTICS = ["statistics.normcdf", "statistics.fitlm", "statistics.lhsdesign"]
FAILURES = [(operation,) for operation in STATISTICS] + [tuple(STATISTICS)]
FAILURE_IDS = ["normcdf", "fitlm", "lhsdesign", "all"]


def _snapshot(directory):
    return {path.relative_to(directory): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


@pytest.mark.parametrize("failures", FAILURES, ids=FAILURE_IDS)
def test_optional_and_required(tmp_path, failures):
    profile = make_profile(tmp_path, include_statistics=True, failing_operations=failures)
    before = _snapshot(tmp_path)

    optional = environment.validate_environment(profile)
    assert optional["valid"] and optional["runtime_assured"] and optional["profile_current"]
    assert optional["required_operations"] == CORE
    assert not set(failures).intersection(optional["qualified_operations"])
    assert set(STATISTICS).difference(failures).issubset(optional["qualified_operations"])

    required = environment.validate_environment(profile, required_operations=list(failures))
    assert not required["valid"]
    assert required["runtime_assured"] and required["profile_current"]
    assert required["required_operations"] == CORE + list(failures)
    assert all(any(operation in error for error in required["errors"]) for operation in failures)

    core_route = resolve_runtime("assure_environment", profile_path=profile)
    assert core_route["status"] == "allowed"
    assert core_route["selected_operations"] == CORE
    required_route = resolve_runtime("assure_environment", profile_path=profile,
                                     required_operations=list(failures))
    assert required_route["status"] == "blocked"
    assert not required_route["execution_allowed"]
    assert required_route["selected_operations"] == CORE + list(failures)
    assert required_route["fallback"]["action"] == "repair_or_review_optional_requirement"

    records = {record["operation_id"]: record
               for record in load_document(profile.parent / "raw-probe.json")["operations"]}
    assert all(not records[operation]["call_success"] and records[operation]["error"]["message"]
               for operation in failures)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("operation", STATISTICS, ids=FAILURE_IDS[:3])
def test_required_probe_selection(tmp_path, operation):
    request = probe.make_request(tmp_path / "matlab/bin/matlab.exe", tmp_path / "new",
                                 required_operations=[operation, CORE[0], operation])
    assert request["required_operations"] == CORE + [operation]
    assert [spec["operation_id"] for spec in request["operation_specs"]] == CORE + [operation]
    assert not set(STATISTICS).difference([operation]).intersection(request["required_operations"])


@pytest.mark.parametrize("operation", STATISTICS, ids=FAILURE_IDS[:3])
def test_required_recovers(tmp_path, operation):
    failed = make_profile(tmp_path / "failed", include_statistics=True,
                          failing_operations=(operation,))
    recovered = make_profile(tmp_path / "recovered", include_statistics=True)
    before = _snapshot(tmp_path)

    assert not environment.validate_environment(failed, required_operations=[operation])["valid"]
    current = environment.validate_environment(recovered, required_operations=[operation])
    assert current["valid"] and operation in current["qualified_operations"]
    route = resolve_runtime("assure_environment", profile_path=recovered,
                            required_operations=[operation])
    assert route["status"] == "allowed"
    assert route["selected_operations"] == CORE + [operation]
    assert not route["business_execution_allowed"]
    assert not route["simulation_execution_allowed"]
    assert _snapshot(tmp_path) == before


def _run_cli(tmp_path, monkeypatch, capsys, *, failures, required, include_statistics):
    """Keep the producer/consumer chain real; replace only the native MATLAB process."""
    seed = make_profile(tmp_path / "seed", include_statistics=True,
                        failing_operations=failures)
    seed_before = _snapshot(tmp_path / "seed")
    template = load_document(seed.parent / "raw-probe.json")
    executable = load_document(seed)["runtime"]["executable"]

    def synthetic_process(command, directory, timeout):
        request = load_document(Path(directory) / "inputs.json")
        requested = {spec["operation_id"] for spec in request["operation_specs"]}
        raw = copy.deepcopy(template)
        moment = datetime.now(timezone.utc)
        raw.update(
            run_id=request["run_id"], input_identity=request["input_identity"],
            source_identity=canonical_digest(request["sources"]),
            host_fingerprint=request["host_fingerprint"],
            started_at=environment.utc_text(moment - timedelta(milliseconds=600)),
            finished_at=environment.utc_text(moment - timedelta(milliseconds=200)),
        )
        raw["operations"] = [record for record in raw["operations"]
                             if record["operation_id"] in requested]
        probe.write_json(Path(directory) / "raw-probe.json", raw)
        process = {
            "started_at": environment.utc_text(moment - timedelta(seconds=1)),
            "finished_at": environment.utc_text(moment), "process_state": "completed",
            "exit_code": 0, "pid": 0, "command": ["SYNTHETIC PROCESS; NO MATLAB"],
        }
        return process, "SYNTHETIC PROCESS; NO MATLAB EXECUTION\n"

    monkeypatch.setattr(probe, "_run_process", synthetic_process)
    directory = tmp_path / "run"
    arguments = ["probe_environment.py", "--matlab-executable", executable,
                 "--output-dir", str(directory)]
    if include_statistics:
        arguments.append("--include-statistics")
    for operation in required:
        arguments.extend(["--require-operation", operation])
    monkeypatch.setattr(sys, "argv", arguments)
    exit_code = probe.main()
    result = json.loads(capsys.readouterr().out)
    assert _snapshot(tmp_path / "seed") == seed_before
    receipt = load_document(directory / "receipt.json")
    assert receipt["artifacts"]["raw"]["sha256"] == sha256_file(directory / "raw-probe.json")
    assert receipt["process"]["process_state"] == "completed"
    assert receipt["process"]["exit_code"] == 0
    return exit_code, result, directory


@pytest.mark.parametrize("failures", FAILURES, ids=FAILURE_IDS)
@pytest.mark.parametrize("explicit", [False, True], ids=["optional", "required"])
def test_cli_error_paths(tmp_path, monkeypatch, capsys, failures, explicit):
    required = list(failures) if explicit else []
    exit_code, result, directory = _run_cli(
        tmp_path, monkeypatch, capsys, failures=failures, required=required,
        include_statistics=True,
    )
    assert exit_code == (1 if explicit else 0)
    assert result["valid"] is (not explicit)
    assert result["runtime_assured"] and result["profile_current"]
    assert result["required_operations"] == CORE + required
    assert not set(failures).intersection(result["qualified_operations"])
    request = load_document(directory / "inputs.json")
    assert request["required_operations"] == CORE + required
    assert {spec["operation_id"] for spec in request["operation_specs"]} == set(CORE + STATISTICS)
    records = {record["operation_id"]: record
               for record in load_document(directory / "raw-probe.json")["operations"]}
    assert all(not records[operation]["call_success"] and records[operation]["error"]["message"]
               for operation in failures)


@pytest.mark.parametrize("operation", STATISTICS, ids=FAILURE_IDS[:3])
@pytest.mark.parametrize("failed", [False, True], ids=["success", "failure"])
def test_cli_required_only(tmp_path, monkeypatch, capsys, operation, failed):
    exit_code, result, directory = _run_cli(
        tmp_path, monkeypatch, capsys, failures=(operation,) if failed else (),
        required=[operation], include_statistics=False,
    )
    assert exit_code == (1 if failed else 0)
    assert result["valid"] is (not failed)
    assert result["runtime_assured"] and result["profile_current"]
    assert (operation in result["qualified_operations"]) is (not failed)
    assert result["required_operations"] == CORE + [operation]
    request = load_document(directory / "inputs.json")
    assert [spec["operation_id"] for spec in request["operation_specs"]] == CORE + [operation]
    assert not set(STATISTICS).difference([operation]).intersection(result["qualified_operations"])
