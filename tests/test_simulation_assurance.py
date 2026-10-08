"""Synthetic consumer tests; these fixtures never establish actual MATLAB qualification."""
import copy
import math
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from scipy.io import loadmat, savemat

import probe_simulation as producer
import run_simulation as runner
from probe_environment import write_json
from runtime_common import canonical_digest, load_document, sha256_file
from test_runtime import make_profile
from simulation_factory import make_simulation_protocol
from validate_environment import utc_text
from validate_simulation_profile import (assert_case, contract, derive_profile, native_records_equal,
                                        validate_run_spec, validate_simulation_profile)
from validate_simulation_protocol import validate_simulation_protocol
from validate_simulation_receipt import validate_simulation_receipt


def synthetic_case(case, directory, run_id, *, primary=False):
    """No MATLAB was run: explicit protocol-consumer fixture only."""
    directory = Path(directory).resolve()
    spec = case["run_spec"]
    model = directory / (spec["model_name"] + ".slx")
    model.write_bytes(b"SYNTHETIC E MODEL; NO MATLAB EXECUTION\n")
    source = Path(spec["model_path"])
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(model.read_bytes())
    if primary:
        model.write_bytes(source.read_bytes())
    before = [{**item, "value": item["value"] if primary else item["value"] - 0.25, "unit": item["unit"] or "", "class": "Simulink.Parameter"} for item in spec["parameters"]]
    applied = [{**item, "unit": item["unit"] or "", "class": "Simulink.Parameter"} for item in spec["parameters"]]
    original_sampling = [{"port": item["port"], "block_path": item["block_path"], "sample_time": "-1"} for item in spec["outputs"]]
    configured_sampling = [{**item, "sample_time": "0"} for item in original_sampling]
    configured = {"Solver": spec["solver"]["name"], "SolverType": "Fixed-step" if spec["solver"]["name"] == "ode4" else "Variable-step", "ZeroCrossControl": spec["solver"]["zero_crossing"]}
    for key, field in (("fixed_step","FixedStep"),("max_step","MaxStep"),("min_step","MinStep"),("initial_step","InitialStep"),("rel_tol","RelTol"),("abs_tol","AbsTol")):
        if spec["solver"][key] is not None:
            configured[field] = spec["solver"][key]
    actual = {"case_id": case["case_id"], "attempted": True, "completed": True, "simulation_returned": True,
              "error_message": "", "errors": [], "warnings": [], "functions": [], "before_parameters": before,
              "applied_parameters": applied, "after_parameters": copy.deepcopy(before), "reopened_parameters": copy.deepcopy(before),
              "before_output_sampling": original_sampling, "configured_output_sampling": configured_sampling,
              "after_output_sampling": copy.deepcopy(original_sampling), "reopened_output_sampling": copy.deepcopy(original_sampling),
              "output_sampling_restored": True,
              "source_unchanged": True, "owned_model_unchanged": True, "configuration_restored": True, "parameters_restored": True,
              "reopened": True, "closed_without_save": True, "model_file": str(model), "source_model_file": str(source),
              "requested_solver": spec["solver"], "configured_parameters": configured,
              "effective_configuration": {"StartTime": spec["start_time"], "StopTime": spec["stop_time"], "SimulationMode": "normal", "Solver":spec["solver"]["name"]},
              "observed_solver_info": {"Solver": spec["solver"]["name"],"Type":spec["solver"]["type"],"FixedStepSize" if spec["solver"]["name"] == "ode4" else "MaxStepSize":spec["solver"]["fixed_step"] if spec["solver"]["name"] == "ode4" else spec["solver"]["max_step"]}, "observed_solver_name": spec["solver"]["name"],
              "stop_event": "ReachedStopTime", "stop_event_time": spec["stop_time"], "time_source":"SimulationOutput.tout", "saved_time":[spec["start_time"],spec["stop_time"]], "output_count": len(spec["outputs"]),
              "mat_file": "", "raw_mat_file":case["case_id"] + "-returned.mat", "data_file": "", "outputs": []}
    if not any(block["type"] == "Integrator" for block in case["build_spec"]["blocks"]):
        compiled = "FixedStepDiscrete" if spec["solver"]["type"] == "fixed-step" else "VariableStepDiscrete"
        actual["observed_solver_info"]["Solver"] = compiled
        actual["observed_solver_name"] = actual["effective_configuration"]["Solver"] = compiled
    savemat(directory / actual["raw_mat_file"],{"run_id":run_id,"simulation_output":"SYNTHETIC; NO MATLAB"},format="5")
    if case["expectation"] != "success":
        if case["expectation"] == "error":
            actual.update(error_message="SYNTHETIC unknown Gain variable phase_e_missing_runtime_variable", errors=[{"identifier":"Simulink:Parameters:InvParamSetting"}], stop_event="DiagnosticError", stop_event_time=None,saved_time=[])
        elif case["expectation"] == "early_stop":
            actual.update(warnings=[{"identifier":"Simulink:Commands:SimTimeExceededTimeOut"}], stop_event="Timeout", stop_event_time=0.1,saved_time=[spec["start_time"],0.1])
        else:
            actual.update(output_count=0, output_boundary_error="SYNTHETIC missing root output")
        return actual
    times = [spec["start_time"] + i * (spec["stop_time"] - spec["start_time"]) / 200 for i in range(201)]
    params = {item["code_name"]: item["value"] for item in spec["parameters"]}
    for output in spec["outputs"]:
        if "decay_a" in params or "a" in params and "b" in params:
            a, b = (params["decay_a"], params["forcing_b"]) if "decay_a" in params else (params["a"], params["b"])
            u = spec["inputs"][0]["values"][0]
            values = [b*u/a + (0.25-b*u/a)*math.exp(-a*(t-spec["start_time"])) for t in times]
        elif case["case_id"] == "passthrough" or not params:
            signal = spec["inputs"][0]
            values = np.interp(times,signal["time"],signal["values"]).tolist()
        else:
            target = 2.0 if output["port"] == 1 else 6.0 if output["port"] == 2 else 7.0
            values = [target] * len(times)
        file = case["case_id"] + "-output-" + str(output["port"]) + ".csv"
        (directory / file).write_text("".join(format(t,".17g") + "," + format(v,".17g") + "\n" for t,v in zip(times,values)), encoding="utf-8")
        actual["outputs"].append({**output, "observed_unit":"", "time": times, "values": values, "csv_file": file})
    actual["data_file"] = case["case_id"] + "-outputs.json"
    actual["mat_file"] = case["case_id"] + "-output.mat"
    write_json(directory / actual["data_file"], {"schema_version": 1, "run_id": run_id, "outputs": actual["outputs"]})
    count = len(actual["outputs"])
    variables, units, mat_times, mat_values = (np.empty((count,1),dtype=object) for _ in range(4))
    for index, output in enumerate(actual["outputs"]):
        variables[index,0] = output["variable_id"]
        units[index,0] = output["unit"] or ""
        mat_times[index,0] = np.array(output["time"],dtype=float).reshape(-1,1)
        mat_values[index,0] = np.array(output["values"],dtype=float).reshape(-1,1)
    savemat(directory / actual["mat_file"], {"run_id":run_id,"output_ports":np.array([o["port"] for o in actual["outputs"]]).reshape(-1,1),
                                          "output_variables":variables,"output_units":units,"output_times":mat_times,"output_values":mat_values,"saved_time":np.array(actual["saved_time"],dtype=float).reshape(-1,1)}, format="5")
    return actual


def replace_constant_mat_storage(path, *, matlab_class):
    """Real MAT v5 format: integer payload storage can still declare mxDOUBLE.

    This synthetic serialization fixture executes no MATLAB. Changing MATLAB's
    array flags to mxUINT8/logical supplies genuine wrong-class negative cases.
    """
    def element(kind, payload):
        return struct.pack("<II", kind, len(payload)) + payload + bytes(-len(payload) % 8)

    def matrix(array_class, shape, name, payload):
        header = element(6, struct.pack("<II", array_class, 0))
        header += element(5, struct.pack("<" + "i" * len(shape), *shape))
        header += element(1, name.encode("ascii"))
        return element(14, header + payload)

    data = {key: value for key, value in loadmat(path, mat_dtype=True).items() if not key.startswith("__")}
    values = data.pop("output_values")
    children = b""
    for value in values[:, 0]:
        assert np.all(value == np.floor(value)) and np.all((0 <= value) & (value <= 255))
        payload = np.asarray(value, dtype=np.uint8).tobytes(order="F")
        children += matrix(matlab_class, value.shape, "", element(2, payload))
    savemat(path, data, format="5")
    assert path.read_bytes()[126:128] == b"IM"
    with path.open("ab") as stream:
        stream.write(matrix(1, values.shape, "output_values", children))


def make_simulation_profile(directory, a_profile, *, age_hours=0):
    directory = Path(directory).resolve()
    runtime = load_document(a_profile)["runtime"]
    request = producer.make_request(runtime["executable"], directory, environment_profile=a_profile)
    directory.mkdir(parents=True,exist_ok=False)
    names = contract()["evidence"]
    write_json(directory / names["input"], request)
    (directory / names["log"]).write_text("SYNTHETIC E CONSUMER EVIDENCE; NO MATLAB EXECUTION\n",encoding="utf-8")
    functions = []
    for name in contract()["required_functions"]:
        file = Path(runtime["matlabroot"]) / "toolbox" / "simulation-fixture" / (name + ".m")
        file.parent.mkdir(parents=True,exist_ok=True)
        if not file.exists():
            file.write_text("% synthetic simulation function identity; no execution\n",encoding="utf-8")
        functions.append({"name":name,"path":str(file.resolve())})
    reference = datetime.now(timezone.utc) - timedelta(hours=age_hours,seconds=0.15)
    raw = {"schema_version":1,"run_id":request["run_id"],"status":"completed","channel":"matlab_batch","host_fingerprint":request["host_fingerprint"],
           "input_identity":request["input_identity"],"source_identity":request["source_identity"],"started_at":utc_text(reference-timedelta(seconds=0.1)),
           "finished_at":utc_text(reference),"runtime":{key:runtime[key] for key in ("release","version","matlabroot","platform")},
           "installed_products":[{"Name":"MATLAB","Version":"25.2"},{"Name":"Simulink","Version":"25.2"}],"licenses_inuse":[],"license_test":1,"functions":functions,
           "cases":[synthetic_case(case,directory,request["run_id"]) for case in request["cases"]]}
    process = {"started_at":utc_text(reference-timedelta(seconds=0.15)),"finished_at":utc_text(reference+timedelta(milliseconds=50)),"process_state":"completed","exit_code":0,"pid":0,"command":["SYNTHETIC; NO MATLAB"]}
    write_json(directory / names["raw"],raw)
    write_json(directory / names["process"],process)
    profile = derive_profile(raw,request,process)
    path = directory / names["profile"]
    write_json(path,profile)
    write_json(directory / names["profile_receipt"],{"schema_version":1,"run_id":request["run_id"],"sources":request["sources"],"process":process,"runtime_fingerprint":profile["runtime"]["fingerprint"],"artifacts":producer.artifact_manifest(directory,raw,include_profile=True)})
    return path


def _rebind(path, *, derive=False):
    names = contract()["evidence"]
    receipt = load_document(path.parent / names["profile_receipt"])
    raw = load_document(path.parent / names["raw"])
    if derive:
        value = derive_profile(raw,load_document(path.parent / names["input"]),receipt["process"])
        write_json(path,value)
    receipt["artifacts"] = producer.artifact_manifest(path.parent,raw,include_profile=True)
    write_json(path.parent / names["profile_receipt"],receipt)


def make_primary_receipt(root, *, solver="ode45", required_operations=None, age_hours=0):
    """Complete synthetic receipt consumer fixture; no accepted numerical evidence."""
    protocol = make_simulation_protocol(root,solver=solver,required_operations=required_operations,age_hours=age_hours)
    report = validate_simulation_protocol(protocol,project_root=protocol.parent,require_frozen=True)
    assert report["valid"] and report["execution_ready"], report["errors"]
    a = protocol.parent / "a-profile" / "evidence" / "profile.json"
    e = make_simulation_profile(protocol.parent / "e-profile",a,age_hours=age_hours)
    directory = protocol.parent / "primary"
    request = runner.make_task_request(protocol,load_document(a)["runtime"]["executable"],directory,report,a,e,project_root=protocol.parent)
    runner.verify_primary_bindings(request,historical_start=datetime.now(timezone.utc)-timedelta(hours=age_hours) if age_hours else None)
    directory.mkdir()
    names = contract()["evidence"]
    write_json(directory / names["input"],request)
    (directory / names["log"]).write_text("SYNTHETIC E PRIMARY; NO MATLAB EXECUTION\n",encoding="utf-8")
    raw = load_document(e.parent / names["raw"])
    reference = datetime.now(timezone.utc) - timedelta(hours=age_hours,seconds=0.03)
    raw.update(run_id=request["run_id"],input_identity=request["input_identity"],source_identity=request["source_identity"],
               started_at=utc_text(reference),finished_at=utc_text(reference+timedelta(milliseconds=10)),
               cases=[synthetic_case(request["cases"][0],directory,request["run_id"],primary=True)])
    process = {"started_at":utc_text(reference-timedelta(milliseconds=5)),"finished_at":utc_text(reference+timedelta(milliseconds=15)),
               "process_state":"completed","exit_code":0,"pid":0,"command":["SYNTHETIC; NO MATLAB"]}
    write_json(directory / names["raw"],raw)
    write_json(directory / names["process"],process)
    return runner.finish_task_request(request,process)


def _rebind_primary(path):
    receipt = load_document(path)
    receipt["artifacts"] = producer.artifact_manifest(path.parent,load_document(path.parent / contract()["evidence"]["raw"]),include_protocol=True)
    write_json(path,receipt)


def test_independent_solver_profile_and_baseline_exit_are_distinct(tmp_path):
    a = make_profile(tmp_path / "a")
    e = make_simulation_profile(tmp_path / "e",a)
    result = validate_simulation_profile(e)
    assert result["valid"], result["errors"]
    assert set(result["qualified_solvers"]) == {"ode45","ode4","ode15s"}
    assert all(item["passed"] for item in result["case_results"])
    assert result["qualified_operations"][0] == "simulink.core_simulation"


def test_one_solver_failure_does_not_qualify_that_solver(tmp_path):
    a = make_profile(tmp_path / "a")
    e = make_simulation_profile(tmp_path / "e",a)
    raw_path = e.parent / "raw-simulation.json"
    raw = load_document(raw_path)
    raw["cases"][0]["observed_solver_name"] = "ode15s"
    write_json(raw_path,raw)
    _rebind(e,derive=True)
    result = validate_simulation_profile(e)
    assert result["valid"] and "ode45" in result["unqualified_solvers"]
    assert not validate_simulation_profile(e,required_solver="ode45")["valid"]
    assert validate_simulation_profile(e,required_solver="ode4")["valid"]


@pytest.mark.parametrize("case_id",["invalid_override","early_stop","no_output"])
def test_failed_negative_assertion_disables_all_simulation_operations(tmp_path,case_id):
    a = make_profile(tmp_path / "a")
    e = make_simulation_profile(tmp_path / "e",a)
    raw = load_document(e.parent / "raw-simulation.json")
    actual = next(item for item in raw["cases"] if item["case_id"] == case_id)
    actual["completed"] = False
    write_json(e.parent / "raw-simulation.json",raw)
    _rebind(e,derive=True)
    result = validate_simulation_profile(e)
    assert not result["valid"]
    assert not next(item for item in result["case_results"] if item["case_id"] == case_id)["passed"]
    assert any(case_id in message for message in result["errors"])


def test_profile_declared_success_cannot_replace_recomputed_failed_case(tmp_path):
    a = make_profile(tmp_path / "a")
    e = make_simulation_profile(tmp_path / "e",a)
    raw = load_document(e.parent / "raw-simulation.json")
    raw["cases"][0]["observed_solver_info"] = {}
    write_json(e.parent / "raw-simulation.json",raw)
    _rebind(e)
    result = validate_simulation_profile(e)
    assert not result["valid"] and "ode45" not in result["qualified_solvers"]
    failed = result["case_results"][0]
    assert not failed["passed"] and any("public solver metadata" in message for message in failed["errors"])
    assert any("declared simulation profile differs" in message for message in result["errors"])


def test_tampered_profile_case_diagnostics_are_not_reported_as_observations(tmp_path):
    a = make_profile(tmp_path / "a")
    e = make_simulation_profile(tmp_path / "e",a)
    profile = load_document(e)
    profile["operation"]["case_results"][0].update(passed=False,errors=["invented diagnostic"])
    write_json(e,profile)
    _rebind(e)
    result = validate_simulation_profile(e)
    assert not result["valid"] and result["case_results"][0]["passed"]
    assert result["case_results"][0]["errors"] == []


@pytest.mark.parametrize("field",["mat_file","data_file","csv"])
def test_independent_mat_json_csv_numeric_equality_survives_manifest_rebind(tmp_path,field):
    a = make_profile(tmp_path / "a")
    e = make_simulation_profile(tmp_path / "e",a)
    raw = load_document(e.parent / "raw-simulation.json")
    actual = raw["cases"][0]
    if field == "mat_file":
        savemat(e.parent / actual[field],{"run_id":"wrong identity"})
    elif field == "data_file":
        value = load_document(e.parent / actual[field])
        value["outputs"][0]["values"][1] += 1
        write_json(e.parent / actual[field],value)
    else:
        file = e.parent / actual["outputs"][0]["csv_file"]
        file.write_text(file.read_text().replace(",",",9",1))
    _rebind(e,derive=True)
    assert "ode45" not in validate_simulation_profile(e)["qualified_solvers"]


@pytest.mark.parametrize("state,code",[("failed",0),("timed_out",0),("completed",1),("completed",True)])
def test_process_state_and_zero_exit_are_independent_gates(tmp_path,state,code):
    a = make_profile(tmp_path / "a")
    e = make_simulation_profile(tmp_path / "e",a)
    receipt = load_document(e.parent / "simulation-profile-receipt.json")
    receipt["process"].update(process_state=state,exit_code=code)
    write_json(e.parent / "simulation-profile-receipt.json",receipt)
    assert not validate_simulation_profile(e)["valid"]


@pytest.mark.parametrize("field,value",[("cases",{}),("functions",{}),("installed_products",{}),("licenses_inuse",None)])
def test_record_collections_do_not_promote_singleton_objects(tmp_path,field,value):
    a = make_profile(tmp_path / "a")
    e = make_simulation_profile(tmp_path / "e",a)
    raw = load_document(e.parent / "raw-simulation.json")
    raw[field] = value
    write_json(e.parent / "raw-simulation.json",raw)
    assert not validate_simulation_profile(e)["valid"]


def test_native_double_readback_preserves_numeric_equality_but_not_boolean():
    assert native_records_equal([{"value":2}],[{"value":2.0}])
    assert not native_records_equal([{"value":True}],[{"value":1.0}])


@pytest.mark.parametrize("value",[True,0,-1,float("inf"),float("nan"),2**53+1])
def test_run_spec_rejects_illegal_steps_before_native_execution(tmp_path,value):
    case = producer.qualification_cases("00000000-0000-0000-0000-000000000001",tmp_path)[0]
    case["run_spec"]["solver"]["max_step"] = value
    with pytest.raises(ValueError):
        validate_run_spec(case["run_spec"])


@pytest.mark.parametrize("value",[0,-1e-12,False])
def test_zero_or_negative_minimum_step_is_rejected_before_simulation(tmp_path,value):
    spec = producer.qualification_cases("00000000-0000-0000-0000-000000000001",tmp_path)[0]["run_spec"]
    spec["solver"]["min_step"] = value
    with pytest.raises(ValueError,match="variable-step applicability"):
        validate_run_spec(spec)


def test_qualification_requests_explicit_positive_native_minimum_step(tmp_path):
    cases = producer.qualification_cases("00000000-0000-0000-0000-000000000001",tmp_path)
    variable_cases = [case for case in cases if case["run_spec"]["solver"]["type"] == "variable-step"]
    assert variable_cases
    assert all(case["run_spec"]["solver"]["min_step"] == 1e-12 for case in variable_cases)
    for case in cases:
        assert validate_run_spec(case["run_spec"]) == case["run_spec"]


@pytest.mark.parametrize("mutation",["different_error","marker_missing","identifier_missing"])
def test_unrelated_error_cannot_establish_controlled_missing_variable_boundary(tmp_path,mutation):
    case = next(item for item in producer.qualification_cases("00000000-0000-0000-0000-000000000001",tmp_path) if item["case_id"] == "invalid_override")
    actual = synthetic_case(case,tmp_path,"synthetic-native-api")
    if mutation == "different_error":
        actual.update(error_message="SYNTHETIC invalid MinStep",errors=[{"identifier":"Simulink:ConfigSet:BdInvSimParam"}])
    elif mutation == "marker_missing":
        actual["error_message"] = "SYNTHETIC unknown Gain variable another_variable"
    else:
        actual["errors"] = [{"identifier":"Simulink:ConfigSet:BdInvSimParam"}]
    with pytest.raises(ValueError,match="controlled missing-variable Gain diagnostic"):
        assert_case(actual,case,tmp_path,"synthetic-native-api")


@pytest.mark.parametrize("mutation",["stop_reason","warning_identifier","captured_error"])
def test_unrelated_stop_or_warning_cannot_establish_controlled_timeout_boundary(tmp_path,mutation):
    case = next(item for item in producer.qualification_cases("00000000-0000-0000-0000-000000000001",tmp_path) if item["case_id"] == "early_stop")
    actual = synthetic_case(case,tmp_path,"synthetic-native-api")
    if mutation == "stop_reason":
        actual["stop_event"] = "ModelStop"
    elif mutation == "warning_identifier":
        actual["warnings"] = [{"identifier":"Synthetic:UnrelatedWarning"}]
    else:
        actual.update(error_message="SYNTHETIC unrelated error",errors=[{"identifier":"Synthetic:UnrelatedError"}])
    with pytest.raises(ValueError,match="controlled timeout/early-stop diagnostic"):
        assert_case(actual,case,tmp_path,"synthetic-native-api")


@pytest.mark.parametrize("mutation",["captured_error","error_diagnostic","early_stop","boolean_count"])
def test_zero_output_boundary_requires_an_error_free_native_completion(tmp_path,mutation):
    case = next(item for item in producer.qualification_cases("00000000-0000-0000-0000-000000000001",tmp_path) if item["case_id"] == "no_output")
    actual = synthetic_case(case,tmp_path,"synthetic-native-api")
    if mutation == "captured_error":
        actual["error_message"] = "SYNTHETIC invalid MinStep"
    elif mutation == "error_diagnostic":
        actual["errors"] = [{"identifier":"Simulink:ConfigSet:BdInvSimParam"}]
    elif mutation == "early_stop":
        actual["stop_event"] = "Timeout"
    else:
        actual["output_count"] = False
    with pytest.raises(ValueError,match="required-output negative boundary"):
        assert_case(actual,case,tmp_path,"synthetic-native-api")


def test_run_spec_accepts_negative_time_and_positive_relative_tolerance_without_hidden_bounds(tmp_path):
    spec = producer.qualification_cases("00000000-0000-0000-0000-000000000001",tmp_path)[0]["run_spec"]
    spec["start_time"] = -1.0
    spec["solver"]["rel_tol"] = 2.0
    for item in spec["inputs"]:
        item["time"][0] = -1.0
    assert validate_run_spec(spec) == spec


@pytest.mark.parametrize("start",[0.05,-0.05])
def test_fixed_step_misaligned_start_is_rejected_before_simulation(tmp_path,start):
    spec = producer.qualification_cases("00000000-0000-0000-0000-000000000001",tmp_path)[1]["run_spec"]
    spec["solver"]["fixed_step"] = 0.1
    spec["start_time"] = start
    for item in spec["inputs"]:
        item["time"][0] = min(start,0.0)
    with pytest.raises(ValueError,match="start time.*step grid"):
        validate_run_spec(spec)


def test_fixed_step_grid_allows_representation_noise_and_non_grid_stop(tmp_path):
    spec = producer.qualification_cases("00000000-0000-0000-0000-000000000001",tmp_path)[1]["run_spec"]
    spec["solver"]["fixed_step"] = 0.1
    spec["start_time"],spec["stop_time"] = -0.3,0.95
    for item in spec["inputs"]:
        item["time"] = [-0.3,0.95]
    assert validate_run_spec(spec) == spec


def test_fixed_step_grid_rejects_overflowed_ratio(tmp_path):
    spec = producer.qualification_cases("00000000-0000-0000-0000-000000000001",tmp_path)[1]["run_spec"]
    spec["solver"]["fixed_step"] = 5e-324
    spec["start_time"],spec["stop_time"] = 1.0,2.0
    for item in spec["inputs"]:
        item["time"] = [1.0,2.0]
    with pytest.raises(ValueError,match="start time.*step grid"):
        validate_run_spec(spec)


def test_expired_profile_preserves_execution_time_readback_and_blocks_new_run(tmp_path):
    a = make_profile(tmp_path / "a",age_hours=25)
    e = make_simulation_profile(tmp_path / "e",a,age_hours=25)
    assert not validate_simulation_profile(e)["valid"]
    assert validate_simulation_profile(e,require_current=False)["valid"]


def test_invalid_request_does_not_create_directory_or_start_process(tmp_path,monkeypatch):
    a = make_profile(tmp_path / "a")
    request = producer.make_request(load_document(a)["runtime"]["executable"],tmp_path / "new-run",environment_profile=a)
    request["cases"][0]["run_spec"]["parameters"][0]["value"] = "unexpected expression"
    request["input_identity"] = canonical_digest({key:value for key,value in request.items() if key != "input_identity"})
    monkeypatch.setattr(producer,"_run_process",lambda *args:pytest.fail("must not start MATLAB"))
    with pytest.raises(ValueError):
        producer.execute_request(request)
    assert not (tmp_path / "new-run").exists()


def test_profile_consumer_is_read_only(tmp_path):
    a = make_profile(tmp_path / "a")
    e = make_simulation_profile(tmp_path / "e",a)
    before = {str(path):sha256_file(path) for path in tmp_path.rglob("*") if path.is_file()}
    assert validate_simulation_profile(e)["valid"]
    assert before == {str(path):sha256_file(path) for path in tmp_path.rglob("*") if path.is_file()}


@pytest.mark.parametrize("solver",["ode45","ode4","ode15s"])
def test_primary_receipt_recomputes_actual_outputs_without_native_execution(tmp_path,solver):
    receipt = make_primary_receipt(tmp_path / "project",solver=solver)
    before = {str(path):sha256_file(path) for path in tmp_path.rglob("*") if path.is_file()}
    result = validate_simulation_receipt(receipt,project_root=receipt.parent.parent)
    assert result["valid"] and result["primary_run_complete"] and result["criteria_satisfied"], result["errors"]
    assert result["model_sha256"] == sha256_file(result["model_path"])
    assert before == {str(path):sha256_file(path) for path in tmp_path.rglob("*") if path.is_file()}


@pytest.mark.parametrize("field,value",[("stop_event_time",0.5),("saved_time",[0.0,0.5]),("time_source","ModelInfo.StopTime"),("error_message","captured error"),("simulation_returned",False)])
def test_primary_receipt_rejects_incomplete_or_configured_time_claim(tmp_path,field,value):
    receipt = make_primary_receipt(tmp_path / "project")
    raw_path = receipt.parent / "raw-simulation.json"
    raw = load_document(raw_path)
    raw["cases"][0][field] = value
    write_json(raw_path,raw)
    _rebind_primary(receipt)
    assert not validate_simulation_receipt(receipt)["valid"]


def test_primary_extra_required_operation_is_kept_and_blocks_unqualified_operation(tmp_path,monkeypatch):
    receipt = make_primary_receipt(tmp_path / "project")
    request = load_document(receipt.parent / "simulation-inputs.json")
    protocol = request["bindings"]["protocol_input"]["path"]
    a = request["bindings"]["environment_profile"]["path"]
    e = request["bindings"]["simulation_profile"]["path"]
    out = receipt.parent.parent / "blocked"
    report = validate_simulation_protocol(protocol,project_root=receipt.parent.parent,require_frozen=True)
    new = runner.make_task_request(protocol,request["matlab_executable"],out,report,a,e,project_root=receipt.parent.parent,required_operations=["missing.operation"])
    assert new["bindings"]["required_A_operations"] == report["required_A_operations"] + ["missing.operation"]
    monkeypatch.setattr(producer,"_run_process",lambda *args:pytest.fail("must not start MATLAB"))
    with pytest.raises(ValueError,match="qualifications failed"):
        runner.run_simulation(protocol,request["matlab_executable"],out,environment_profile=a,simulation_profile=e,project_root=receipt.parent.parent,required_operations=["missing.operation"])
    assert not out.exists()


def test_metadata_missing_stop_event_time_uses_only_saved_tout(tmp_path):
    case = producer.qualification_cases("00000000-0000-0000-0000-000000000001",tmp_path)[0]
    actual = synthetic_case(case,tmp_path,"synthetic-native-api")
    # R2025b ExecutionInfo has no StopEventTime. Native metadata never supplies it.
    actual["observed_execution_info_fields"] = ["StopEvent","WarningDiagnostics","ErrorDiagnostic"]
    assert assert_case(actual,case,tmp_path,"synthetic-native-api")["complete"]
    actual["saved_time"] = []
    actual["stop_event_time"] = None
    with pytest.raises(ValueError,match="incomplete expected stop"):
        assert_case(actual,case,tmp_path,"synthetic-native-api")


@pytest.mark.parametrize("info",[{}, {"Type":"fixed-step","Solver":"ode45","MaxStepSize":0.02},
    {"Type":"variable-step","Solver":"ode15s","MaxStepSize":0.02}, {"Type":"variable-step","Solver":"ode45","MaxStepSize":0.03}])
def test_public_solver_metadata_missing_or_conflicting_does_not_qualify(tmp_path,info):
    case = producer.qualification_cases("00000000-0000-0000-0000-000000000001",tmp_path)[0]
    actual = synthetic_case(case,tmp_path,"synthetic-native-api")
    actual["observed_solver_info"] = info
    with pytest.raises(ValueError,match="actual public solver metadata"):
        assert_case(actual,case,tmp_path,"synthetic-native-api")


@pytest.mark.parametrize("method,accepted", [("VariableStepDiscrete", True),
    ("FixedStepDiscrete", False), ("discrete", False), ("ode45", False), ("ode15s", False)])
def test_stateless_variable_solver_records_exact_compiled_method(tmp_path,method,accepted):
    case = next(item for item in producer.qualification_cases("00000000-0000-0000-0000-000000000001",tmp_path)
                if item["case_id"] == "constant_no_input")
    actual = synthetic_case(case,tmp_path,"synthetic-native-api")
    actual["observed_solver_info"]["Solver"] = method
    actual["observed_solver_name"] = actual["effective_configuration"]["Solver"] = method
    if accepted:
        assert assert_case(actual,case,tmp_path,"synthetic-native-api")["complete"]
    else:
        with pytest.raises(ValueError,match="actual stateless solver"):
            assert_case(actual,case,tmp_path,"synthetic-native-api")


@pytest.mark.parametrize("method,accepted", [("FixedStepDiscrete", True), ("VariableStepDiscrete", False)])
def test_stateless_fixed_solver_records_exact_compiled_method(tmp_path,method,accepted):
    cases = producer.qualification_cases("00000000-0000-0000-0000-000000000001",tmp_path)
    case = next(item for item in cases if item["case_id"] == "constant_no_input")
    case["run_spec"]["solver"] = next(item for item in cases if item["case_id"] == "feedback_ode4")["run_spec"]["solver"]
    actual = synthetic_case(case,tmp_path,"synthetic-native-api")
    actual["observed_solver_info"]["Solver"] = method
    actual["observed_solver_name"] = actual["effective_configuration"]["Solver"] = method
    if accepted:
        assert assert_case(actual,case,tmp_path,"synthetic-native-api")["complete"]
    else:
        with pytest.raises(ValueError,match="actual stateless solver"):
            assert_case(actual,case,tmp_path,"synthetic-native-api")


def test_continuous_model_cannot_claim_compiled_discrete_solver(tmp_path):
    case = producer.qualification_cases("00000000-0000-0000-0000-000000000001",tmp_path)[0]
    actual = synthetic_case(case,tmp_path,"synthetic-native-api")
    actual["observed_solver_info"]["Solver"] = "VariableStepDiscrete"
    actual["observed_solver_name"] = actual["effective_configuration"]["Solver"] = "VariableStepDiscrete"
    with pytest.raises(ValueError,match="actual continuous solver"):
        assert_case(actual,case,tmp_path,"synthetic-native-api")


@pytest.mark.parametrize("field",["last_warning_message","last_warning_identifier"])
def test_warning_policy_reject_covers_matlab_lastwarn_side_channel(tmp_path,field):
    case = producer.qualification_cases("00000000-0000-0000-0000-000000000001",tmp_path)[0]
    case["warning_policy"] = case["run_spec"]["warning_policy"] = "reject"
    actual = synthetic_case(case,tmp_path,"synthetic-native-api")
    actual[field] = "synthetic warning"
    with pytest.raises(ValueError,match="warning policy"):
        assert_case(actual,case,tmp_path,"synthetic-native-api")


@pytest.mark.parametrize("field,value",[("StartTime",False),("StopTime",True)])
def test_public_time_metadata_does_not_promote_booleans_to_numbers(tmp_path,field,value):
    case = producer.qualification_cases("00000000-0000-0000-0000-000000000001",tmp_path)[0]
    if field == "StopTime":
        case["run_spec"]["stop_time"] = 1.0
    actual = synthetic_case(case,tmp_path,"synthetic-native-api")
    actual["effective_configuration"][field] = value
    with pytest.raises(ValueError,match="public simulation metadata times"):
        assert_case(actual,case,tmp_path,"synthetic-native-api")


def test_output_count_boolean_cannot_satisfy_required_single_output(tmp_path):
    case = producer.qualification_cases("00000000-0000-0000-0000-000000000001",tmp_path)[0]
    actual = synthetic_case(case,tmp_path,"synthetic-native-api")
    actual["output_count"] = True
    with pytest.raises(ValueError,match="output count"):
        assert_case(actual,case,tmp_path,"synthetic-native-api")


@pytest.mark.parametrize("value", [None, False, True, "0", -1, 0.1])
def test_run_spec_rejects_unreviewed_root_output_sampling_before_execution(tmp_path, value):
    case = producer.qualification_cases("00000000-0000-0000-0000-000000000001", tmp_path)[0]
    case["run_spec"]["outputs"][0]["sample_time"] = value
    with pytest.raises(ValueError, match="continuous root-output sample_time"):
        validate_run_spec(case["run_spec"])


def test_run_spec_requires_output_sampling_in_every_port(tmp_path):
    cases = producer.qualification_cases("00000000-0000-0000-0000-000000000001", tmp_path)
    assert {len(case["run_spec"]["outputs"]) for case in cases} == {0, 1, 3}
    for case in cases:
        assert validate_run_spec(case["run_spec"]) == case["run_spec"]
        assert all(output["sample_time"] == 0 for output in case["run_spec"]["outputs"])
    multi = next(case for case in cases if case["case_id"] == "multiple_outputs")
    del multi["run_spec"]["outputs"][2]["sample_time"]
    with pytest.raises(ValueError, match="root-port binding"):
        validate_run_spec(multi["run_spec"])


@pytest.mark.parametrize("case_id", ["constant_no_input", "multiple_outputs", "no_output"])
def test_sampling_records_preserve_zero_one_multiple_port_arrays(tmp_path, case_id):
    case = next(item for item in producer.qualification_cases("00000000-0000-0000-0000-000000000001", tmp_path)
                if item["case_id"] == case_id)
    actual = synthetic_case(case, tmp_path, "synthetic-output-sampling")
    for key in ("before_output_sampling", "configured_output_sampling", "after_output_sampling", "reopened_output_sampling"):
        assert isinstance(actual[key], list) and len(actual[key]) == len(case["run_spec"]["outputs"])
    checked = assert_case(actual, case, tmp_path, "synthetic-output-sampling")
    assert checked["complete"] == (case_id != "no_output")


@pytest.mark.parametrize("record_key", ["before_output_sampling", "configured_output_sampling", "after_output_sampling", "reopened_output_sampling"])
@pytest.mark.parametrize("change", ["missing_port", "object_instead_of_array", "boolean_port", "wrong_path", "numeric_sample", "blank_sample"])
def test_actual_output_sampling_requires_complete_typed_port_bindings(tmp_path, record_key, change):
    case = next(item for item in producer.qualification_cases("00000000-0000-0000-0000-000000000001", tmp_path)
                if item["case_id"] == "multiple_outputs")
    actual = synthetic_case(case, tmp_path, "synthetic-output-sampling")
    if change == "missing_port":
        actual[record_key].pop()
    elif change == "object_instead_of_array":
        actual[record_key] = actual[record_key][0]
    else:
        field, value = {"boolean_port": ("port", True), "wrong_path": ("block_path", "wrong/Output"),
                        "numeric_sample": ("sample_time", 0), "blank_sample": ("sample_time", " ")}[change]
        actual[record_key][0][field] = value
    with pytest.raises(ValueError, match="sampling"):
        assert_case(actual, case, tmp_path, "synthetic-output-sampling")


@pytest.mark.parametrize("record_key", ["configured_output_sampling", "after_output_sampling", "reopened_output_sampling"])
def test_sampling_configuration_and_restoration_cannot_be_asserted_by_success_flags(tmp_path, record_key):
    case = producer.qualification_cases("00000000-0000-0000-0000-000000000001", tmp_path)[0]
    actual = synthetic_case(case, tmp_path, "synthetic-output-sampling")
    actual[record_key][0]["sample_time"] = "-1" if record_key == "configured_output_sampling" else "0"
    with pytest.raises(ValueError, match="sampling"):
        assert_case(actual, case, tmp_path, "synthetic-output-sampling")


def test_native_sampling_restore_flag_must_be_actual_boolean_true(tmp_path):
    case = producer.qualification_cases("00000000-0000-0000-0000-000000000001", tmp_path)[0]
    actual = synthetic_case(case, tmp_path, "synthetic-output-sampling")
    actual["output_sampling_restored"] = 1
    with pytest.raises(ValueError, match="restoration"):
        assert_case(actual, case, tmp_path, "synthetic-output-sampling")


def test_single_constant_sample_cannot_substitute_for_native_time_coverage(tmp_path):
    case = next(item for item in producer.qualification_cases("00000000-0000-0000-0000-000000000001", tmp_path)
                if item["case_id"] == "constant_no_input")
    actual = synthetic_case(case, tmp_path, "synthetic-output-sampling")
    data = load_document(tmp_path / actual["data_file"])
    data["outputs"][0].update(time=[0.0], values=[2.0])
    write_json(tmp_path / actual["data_file"], data)
    with pytest.raises(ValueError, match="time/value shape"):
        assert_case(actual, case, tmp_path, "synthetic-output-sampling")


@pytest.mark.parametrize("case_id", ["constant_no_input", "multiple_outputs"])
def test_compact_mat_integer_storage_preserves_double_class_and_exact_outputs(tmp_path, case_id):
    case = next(item for item in producer.qualification_cases("00000000-0000-0000-0000-000000000001", tmp_path)
                if item["case_id"] == case_id)
    actual = synthetic_case(case, tmp_path, "synthetic-compact-mat")
    path = tmp_path / actual["mat_file"]
    replace_constant_mat_storage(path, matlab_class=6)  # mxDOUBLE_CLASS; miUINT8 data payload.
    stored = loadmat(path, mat_dtype=False)["output_values"]
    restored = loadmat(path, mat_dtype=True)["output_values"]
    assert all(item.dtype == np.dtype("uint8") for item in stored[:, 0])
    assert all(item.dtype == np.dtype("float64") for item in restored[:, 0])
    assert assert_case(actual, case, tmp_path, "synthetic-compact-mat")["complete"]


@pytest.mark.parametrize("matlab_class,expected_dtype", [(9, "uint8"), (9 | 0x200, "bool")])
def test_true_integer_or_logical_matlab_class_is_rejected_without_casting(tmp_path, matlab_class, expected_dtype):
    case = next(item for item in producer.qualification_cases("00000000-0000-0000-0000-000000000001", tmp_path)
                if item["case_id"] == "constant_no_input")
    actual = synthetic_case(case, tmp_path, "synthetic-wrong-mat-class")
    path = tmp_path / actual["mat_file"]
    replace_constant_mat_storage(path, matlab_class=matlab_class)
    assert loadmat(path, mat_dtype=True)["output_values"][0, 0].dtype == np.dtype(expected_dtype)
    with pytest.raises(ValueError, match="numeric class must be double"):
        assert_case(actual, case, tmp_path, "synthetic-wrong-mat-class")


@pytest.mark.parametrize("field", ["output_values", "output_times", "saved_time"])
def test_complex_matlab_double_cannot_pass_by_dropping_its_imaginary_component(tmp_path, field):
    case = producer.qualification_cases("00000000-0000-0000-0000-000000000001", tmp_path)[0]
    actual = synthetic_case(case, tmp_path, "synthetic-complex-mat")
    path = tmp_path / actual["mat_file"]
    data = {key: value for key, value in loadmat(path).items() if not key.startswith("__")}
    if field == "saved_time":
        data[field] = data[field].astype(np.complex128) + 1j
    else:
        data[field][0, 0] = data[field][0, 0].astype(np.complex128) + 1j
    savemat(path, data, format="5")
    with pytest.raises(ValueError, match="complex data.*real-double"):
        assert_case(actual, case, tmp_path, "synthetic-complex-mat")


def test_restoring_matlab_class_keeps_exact_numeric_equality_requirement(tmp_path):
    case = next(item for item in producer.qualification_cases("00000000-0000-0000-0000-000000000001", tmp_path)
                if item["case_id"] == "constant_no_input")
    actual = synthetic_case(case, tmp_path, "synthetic-exact-mat")
    path = tmp_path / actual["mat_file"]
    data = {key: value for key, value in loadmat(path).items() if not key.startswith("__")}
    data["output_values"][0, 0][0, 0] = np.nextafter(2.0, 3.0)
    savemat(path, data, format="5")
    with pytest.raises(ValueError, match="MAT numeric values differ from JSON"):
        assert_case(actual, case, tmp_path, "synthetic-exact-mat")


def test_historical_primary_receipt_retains_execution_time_qualification(tmp_path,monkeypatch):
    receipt = make_primary_receipt(tmp_path / "project",age_hours=25)
    assert validate_simulation_receipt(receipt)["valid"]
    request = load_document(receipt.parent / "simulation-inputs.json")
    a,e = (request["bindings"][key]["path"] for key in ("environment_profile","simulation_profile"))
    out = receipt.parent.parent / "blocked-expired"
    monkeypatch.setattr(producer,"_run_process",lambda *args:pytest.fail("must not start MATLAB"))
    with pytest.raises(ValueError,match="qualifications failed"):
        runner.run_simulation(request["bindings"]["protocol_input"]["path"],request["matlab_executable"],out,
            environment_profile=a,simulation_profile=e,project_root=receipt.parent.parent)
    assert not out.exists()


def test_core_success_does_not_satisfy_explicit_failed_statistics_requirement(tmp_path,monkeypatch):
    import simulation_factory
    from validate_environment import validate_environment
    monkeypatch.setattr(simulation_factory,"make_profile",lambda *args,**kwargs:make_profile(*args,**kwargs,failing_operations=["statistics.fitlm"]))
    protocol = make_simulation_protocol(tmp_path / "project",required_operations=["matlab.basic_execution","simulink.library_load","statistics.fitlm"])
    report = validate_simulation_protocol(protocol,project_root=protocol.parent,require_frozen=True)
    a = protocol.parent / "a-profile" / "evidence" / "profile.json"
    assert validate_environment(a)["valid"]
    assert not validate_environment(a,required_operations=["statistics.fitlm"])["valid"]
    e = make_simulation_profile(protocol.parent / "e-profile",a)
    out = protocol.parent / "blocked-required-statistics"
    monkeypatch.setattr(producer,"_run_process",lambda *args:pytest.fail("must not start MATLAB"))
    with pytest.raises(ValueError,match="qualifications failed"):
        runner.run_simulation(protocol,load_document(a)["runtime"]["executable"],out,environment_profile=a,simulation_profile=e,project_root=protocol.parent)
    assert report["execution_ready"] and not out.exists()
