"""Synthetic consumer and boundary tests; only the actual batch probe qualifies MATLAB."""
import copy
from datetime import datetime, timedelta, timezone
import json

import pytest

import probe_implementation as producer
from native_factory import make_implementation_profile
from probe_environment import write_json
from runtime_common import canonical_digest, load_document, sha256_file
from test_runtime import make_profile
from validate_implementation_profile import OPERATION, validate_build_spec, validate_implementation_profile


def rebind_profile_artifact(path):
    receipt_path = path.parent / "implementation-profile-receipt.json"
    receipt = load_document(receipt_path)
    receipt["artifacts"]["profile"]["sha256"] = sha256_file(path)
    write_json(receipt_path, receipt)


def test_independent_native_profile_covers_all_six_types(tmp_path):
    a = make_profile(tmp_path / "a")
    d = make_implementation_profile(tmp_path / "d", a)
    report = validate_implementation_profile(d)
    assert report["valid"], report["errors"]
    assert report["qualified_operations"] == [OPERATION]
    request = load_document(d.parent / "inputs.json")
    kinds = {block["type"] for case in request["cases"] if not case["expect_failure"] for block in case["build_spec"]["blocks"]}
    assert kinds == {"Inport", "Outport", "Constant", "Gain", "Sum", "Integrator"}
    assert load_document(d)["operation"]["passed_cases"] == ["static", "feedback", "invalid_port"]
    assert "simulink.simulation_execution" not in report["qualified_operations"]


def test_native_profile_expiry_is_only_a_new_execution_gate(tmp_path):
    a = make_profile(tmp_path / "a", age_hours=25)
    d = make_implementation_profile(tmp_path / "d", a, age_hours=25)
    assert not validate_implementation_profile(d)["valid"]
    profile = load_document(d)
    clock = datetime.fromisoformat(profile["captured_at"].replace("Z", "+00:00")) + timedelta(seconds=1)
    assert validate_implementation_profile(d, now=clock)["valid"]


@pytest.mark.parametrize("field", ["schema_version", "installed", "qualified"])
def test_bool_number_profile_identity_is_not_python_loose_equality(tmp_path, field):
    a = make_profile(tmp_path / "a")
    d = make_implementation_profile(tmp_path / "d", a)
    value = load_document(d)
    if field == "schema_version":
        value[field] = True
    else:
        value["operation"][field] = 1
    write_json(d, value)
    rebind_profile_artifact(d)
    assert not validate_implementation_profile(d)["valid"]


@pytest.mark.parametrize("value", [True, float("inf"), float("nan"), 2**53 + 1, 10**1000, "2", [2]])
def test_unsupported_parameter_values_are_controlled_invalid(value):
    spec = producer.qualification_cases("00000000-0000-0000-0000-000000000001")[0]["build_spec"]
    spec["parameters"][0]["value"] = value
    with pytest.raises(ValueError, match="finite scalar"):
        validate_build_spec(spec)


def test_initial_condition_large_integer_is_not_silently_rounded():
    spec = producer.qualification_cases("00000000-0000-0000-0000-000000000001")[1]["build_spec"]
    next(block for block in spec["blocks"] if block["type"] == "Integrator")["parameters"]["InitialCondition"] = "9007199254740993"
    with pytest.raises(ValueError, match="native-representable"):
        validate_build_spec(spec)


@pytest.mark.parametrize("mutation", ["expression", "callback", "source", "schema", "port_bool"])
def test_runner_rejects_uncontrolled_request_before_directory_or_process(tmp_path, monkeypatch, mutation):
    a = make_profile(tmp_path / "a")
    executable = load_document(a)["runtime"]["executable"]
    request = producer.make_request(executable, tmp_path / "new-run")
    if mutation == "expression":
        request["cases"][0]["build_spec"]["blocks"][1]["parameters"]["Gain"] = "system('unexpected')"
    elif mutation == "callback":
        request["cases"][0]["build_spec"]["blocks"][1]["parameters"]["InitFcn"] = "unexpected"
    elif mutation == "source":
        request["supported_blocks"]["Gain"]["source"] = "unqualified/Custom"
    elif mutation == "schema":
        request["schema_version"] = True
    else:
        request["cases"][0]["build_spec"]["connections"][0]["source"]["port"] = True
    request["input_identity"] = canonical_digest({key: value for key, value in request.items() if key != "input_identity"})
    monkeypatch.setattr(producer, "_run_process", lambda *args: pytest.fail("process must not start"))
    with pytest.raises(ValueError):
        producer.execute_request(request)
    assert not (tmp_path / "new-run").exists()


def test_changed_saved_structure_and_stale_source_are_rejected(tmp_path, monkeypatch):
    a = make_profile(tmp_path / "a")
    d = make_implementation_profile(tmp_path / "d", a)
    model = next(d.parent.glob("native_static_*.slx"))
    model.write_bytes(model.read_bytes() + b"changed")
    assert not validate_implementation_profile(d)["valid"]
    import validate_implementation_profile as consumer
    real = consumer.source_identities
    monkeypatch.setattr(consumer, "source_identities", lambda: {**real(), "scripts/probe_implementation.py": "0" * 64})
    report = consumer.validate_implementation_profile(d)
    assert not report["valid"] and "native source files changed" in report["errors"]


@pytest.mark.parametrize("state,code", [("timed_out", 0), ("failed", 0), ("completed", 1), ("completed", False)])
def test_process_completion_is_required_separately_from_successful_calls(tmp_path, state, code):
    a = make_profile(tmp_path / "a")
    d = make_implementation_profile(tmp_path / "d", a)
    receipt_path = d.parent / "implementation-profile-receipt.json"
    receipt = load_document(receipt_path)
    receipt["process"].update(process_state=state, exit_code=code)
    write_json(receipt_path, receipt)
    result = validate_implementation_profile(d)
    assert not result["valid"] and "exit 0" in result["errors"][0]


def test_expected_bad_port_is_a_real_required_failure_not_a_success_flag(tmp_path):
    a = make_profile(tmp_path / "a")
    d = make_implementation_profile(tmp_path / "d", a)
    raw_path = d.parent / "raw-implementation.json"
    raw = load_document(raw_path)
    raw["cases"][-1]["call_success"] = True
    write_json(raw_path, raw)
    receipt_path = d.parent / "implementation-profile-receipt.json"
    receipt = load_document(receipt_path)
    receipt["artifacts"]["raw"]["sha256"] = sha256_file(raw_path)
    write_json(receipt_path, receipt)
    assert not validate_implementation_profile(d)["valid"]
