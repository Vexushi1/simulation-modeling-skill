"""Historical implementation closure tests using visibly synthetic model bytes."""
import json

import pytest

from mapping_factory import make_mapping_contract
from native_factory import make_implementation_profile, make_implementation_receipt
from probe_environment import write_json
from runtime_common import load_document, sha256_file
from test_runtime import make_profile
from validate_domain_mapping import validate_domain_mapping
from validate_implementation_receipt import validate_implementation_receipt


def chain(root, *, age_hours=0):
    project = root / "project"
    mapping = make_mapping_contract(project, case="feedback")
    a = make_profile(root / "a", age_hours=age_hours)
    d = make_implementation_profile(root / "d", a, age_hours=age_hours)
    receipt = make_implementation_receipt(project / "native-build", mapping, a, d, age_hours=age_hours)
    return project, mapping, receipt


def rebind_artifact(receipt, kind):
    value = load_document(receipt)
    value["artifacts"][kind]["sha256"] = sha256_file(receipt.parent / value["artifacts"][kind]["file"])
    write_json(receipt, value)


def test_full_original_input_and_semantic_snapshot_survive_ready_binding(tmp_path):
    project, mapping, receipt = chain(tmp_path)
    before = mapping.read_bytes()
    report = validate_implementation_receipt(receipt, project_root=project, mapping_report=validate_domain_mapping(mapping))
    assert report["valid"] and report["built"] and report["structure_checked"] and report["implementation_ready"], report["errors"]
    assert (receipt.parent / "mapping-original.yaml").read_bytes() == before
    standalone = validate_implementation_receipt(receipt, project_root=project)
    assert standalone["valid"] and not standalone["implementation_ready"]
    value = load_document(mapping)
    value["status"] = "ready"
    value["implementation"] = {"path": str(receipt.relative_to(project)), "sha256": sha256_file(receipt)}
    write_json(mapping, value)
    ready = validate_domain_mapping(mapping, project_root=project, require_ready=True)
    assert ready["valid"] and ready["implementation_ready"], ready["errors"]
    assert (receipt.parent / "mapping-original.yaml").read_bytes() == before


def test_historical_structure_remains_valid_when_today_profiles_expired(tmp_path):
    project, mapping, receipt = chain(tmp_path, age_hours=25)
    result = validate_implementation_receipt(receipt, project_root=project, mapping_report=validate_domain_mapping(mapping))
    assert result["valid"] and result["implementation_ready"], result["errors"]


@pytest.mark.parametrize("artifact", ["implementation_model", "mapping_original", "mapping_snapshot", "input", "log"])
def test_every_manifest_artifact_is_byte_bound(tmp_path, artifact):
    project, _, receipt = chain(tmp_path)
    value = load_document(receipt)
    path = receipt.parent / value["artifacts"][artifact]["file"]
    path.write_bytes(path.read_bytes() + b"\nchanged\n")
    assert not validate_implementation_receipt(receipt, project_root=project)["valid"]


@pytest.mark.parametrize("mutation", ["callback", "port_bool", "connection_bool", "parameter_bool"])
def test_readback_assertions_reject_typed_or_executable_changes_even_rehashed(tmp_path, mutation):
    project, _, receipt = chain(tmp_path)
    structure = receipt.parent / "implementation-structure.json"
    value = load_document(structure)
    if mutation == "callback":
        value["callbacks"]["InitFcn"] = "unexpected"
    elif mutation == "port_bool":
        value["blocks"][0]["ports"]["outport_count"] = True
    elif mutation == "connection_bool":
        value["connections"][0]["source"]["port"] = True
    else:
        value["parameters"][0]["value"] = True
    write_json(structure, value)
    rebind_artifact(receipt, "implementation_structure")
    assert not validate_implementation_receipt(receipt, project_root=project)["valid"]


def test_actual_function_resolution_and_current_c_closure_are_checked(tmp_path):
    project, _, receipt = chain(tmp_path)
    raw_path = receipt.parent / "raw-implementation.json"
    raw = load_document(raw_path)
    raw["functions"][0]["path"] = str(project / "unqualified.m")
    write_json(raw_path, raw)
    rebind_artifact(receipt, "raw")
    report = validate_implementation_receipt(receipt, project_root=project)
    assert not report["valid"] and "actual native function resolutions" in report["errors"][0]


def test_dependency_bytes_and_project_boundary_cannot_be_replaced(tmp_path):
    project, _, receipt = chain(tmp_path)
    request = load_document(receipt.parent / "inputs.json")
    dependency = request["bindings"]["bound_files"][0]["path"]
    from pathlib import Path
    path = Path(dependency)
    path.write_bytes(path.read_bytes() + b"changed")
    assert not validate_implementation_receipt(receipt, project_root=project)["valid"]


@pytest.mark.parametrize("state,code", [("timed_out", 0), ("failed", 0), ("completed", 1), ("completed", False)])
def test_failed_or_timeout_execution_never_has_ready_receipt(tmp_path, state, code):
    project, mapping, receipt = chain(tmp_path)
    value = load_document(receipt)
    value["process"].update(process_state=state, exit_code=code)
    write_json(receipt, value)
    result = validate_implementation_receipt(receipt, project_root=project, mapping_report=validate_domain_mapping(mapping))
    assert not result["valid"] and not result["built"] and not result["structure_checked"] and not result["implementation_ready"]
