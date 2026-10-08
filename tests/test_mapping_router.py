"""D text review and core construction never imply simulation permission."""
import json
import subprocess
import sys

import pytest

from model_factory import make_model_contract
from mapping_factory import make_mapping_contract
from resolve_runtime import resolve_runtime
from runtime_common import ROOT, contained_path, load_document, sha256_file
from test_model_state import write_model_state
from test_runtime import make_profile


def assert_mapping_only(route):
    assert route["phase"] == "D"
    assert route["execution_scope"] == "domain_mapping"
    assert route["execution_allowed"] is False
    assert route["implementation_execution_allowed"] is False
    assert route["business_execution_allowed"] is False
    assert route["simulation_execution_allowed"] is False
    assert route["selected_operations"] == []
    assert not route["activated_packs"] and not route["upstream_skills"]
    assert route["state_mutated"] is False


def test_current_approved_design_opens_mapping_without_environment_or_writes(tmp_path):
    model = make_model_contract(tmp_path, status="approved")
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    route = resolve_runtime("domain_mapping", model_path=model)
    assert route["status"] == "allowed", route["errors"]
    assert route["model_contract_sha256"] == sha256_file(model)
    assert "mapping_contract_supplied" in route["missing_gates"]
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before
    assert_mapping_only(route)


@pytest.mark.parametrize("status", [None, "draft", "proposed", "challenged"])
def test_mapping_requires_current_c_approval_not_a_stage_label(tmp_path, status):
    model = make_model_contract(tmp_path, status=status) if status else None
    route = resolve_runtime("domain_mapping", model_path=model)
    assert route["status"] == "blocked"
    assert "model_design_approved" in route["missing_gates"]
    assert_mapping_only(route)


def test_changed_brief_or_old_approval_cannot_authorize_mapping(tmp_path):
    model = make_model_contract(tmp_path, status="approved")
    brief = contained_path(tmp_path, load_document(model)["brief"]["path"])
    brief.write_bytes(brief.read_bytes() + b"\nchanged brief\n")
    route = resolve_runtime("domain_mapping", model_path=model)
    assert route["status"] == "blocked"
    assert route["fallback"]["action"] == "review_model_sources_and_design"
    assert_mapping_only(route)


def test_mapping_review_ignores_environment_expiry_without_granting_build_permission(tmp_path):
    model = make_model_contract(tmp_path, status="approved")
    profile = make_profile(tmp_path / "runtime", age_hours=25)
    state = write_model_state(tmp_path, model, stage="MODEL_APPROVED", profile=profile)
    before = state.read_bytes()
    route = resolve_runtime("domain_mapping", state_path=state)
    assert route["status"] == "allowed", route["errors"]
    assert route["state_validation"]["scope"] == "implementation"
    assert route["state_validation"]["environment_checked"] is False
    assert state.read_bytes() == before
    assert_mapping_only(route)
    build = resolve_runtime("simulink_build", state_path=state)
    assert build["status"] == "blocked"
    assert build["implementation_execution_allowed"] is False


def test_approved_model_and_core_runtime_cannot_replace_a_mapping(tmp_path):
    model = make_model_contract(tmp_path, status="approved")
    profile = make_profile(tmp_path / "runtime")
    route = resolve_runtime("simulink_build", model_path=model, profile_path=profile)
    assert route["status"] == "blocked"
    assert "mapping_contract_build_ready" in route["missing_gates"]
    assert not route["execution_allowed"] and not route["implementation_execution_allowed"]
    assert not route["business_execution_allowed"] and not route["simulation_execution_allowed"]
    assert not route["activated_modules"] and not route["upstream_skills"]


@pytest.mark.parametrize("argument", ["problem", "model", "approval"])
def test_mapping_arguments_cannot_substitute_current_project_bindings(tmp_path, argument):
    model = make_model_contract(tmp_path, status="approved")
    state = write_model_state(tmp_path, model, stage="MODEL_APPROVED")
    value = load_document(model)
    original = model if argument == "model" else contained_path(tmp_path, value[argument]["path"])
    copy = tmp_path / f"copied-{argument}.json"
    copy.write_bytes(original.read_bytes())
    route = resolve_runtime("domain_mapping", state_path=state, **{f"{argument}_path": copy})
    assert route["status"] == "blocked"
    assert f"{argument}_state_binding_matches" in route["missing_gates"]
    assert_mapping_only(route)


def test_unknown_native_operations_and_arbitrary_simulation_intent_are_not_selected(tmp_path):
    model = make_model_contract(tmp_path, status="approved")
    route = resolve_runtime("simulink_build", model_path=model, required_operations=["simulink.simulation_execution"])
    assert route["status"] == "invalid"
    assert not route["implementation_execution_allowed"]
    for intent in ("simulation_execution", "simscape_build", "stateflow_build"):
        route = resolve_runtime(intent)
        assert route["status"] == ("blocked" if intent == "simulation_execution" else "deferred")
        assert not route["execution_allowed"] and not route["implementation_execution_allowed"]
        assert not route["activated_modules"] and not route["upstream_skills"]


def test_mapping_cli_inspects_current_design_without_matlab(tmp_path):
    model = make_model_contract(tmp_path, status="approved")
    completed = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/resolve_runtime.py"),
                                "--intent", "domain_mapping", "--model", str(model)],
                               capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout
    route = json.loads(completed.stdout)
    assert route["status"] == "allowed"
    assert_mapping_only(route)


@pytest.mark.parametrize("known_parameters", [True, False])
def test_real_mapping_inspection_preserves_unknown_values_and_uses_no_profile(tmp_path, known_parameters):
    mapping = make_mapping_contract(tmp_path, known_parameters=known_parameters)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    route = resolve_runtime("domain_mapping", mapping_path=mapping)
    assert route["status"] == "inspected", route["errors"]
    assert route["mapping_validation"]["mapping_complete"]
    assert route["mapping_validation"]["build_ready"] is known_parameters
    assert route["mapping_contract_sha256"] == sha256_file(mapping)
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before
    assert_mapping_only(route)


def test_a_library_loading_does_not_supply_independent_d_qualification(tmp_path):
    mapping = make_mapping_contract(tmp_path)
    profile = make_profile(tmp_path / "runtime")
    route = resolve_runtime("simulink_build", mapping_path=mapping, profile_path=profile)
    assert route["status"] == "blocked", route["errors"]
    assert "implementation_profile_current" in route["missing_gates"]
    assert route["execution_allowed"] is False and route["implementation_execution_allowed"] is False
    assert route["selected_operations"] == ["matlab.basic_execution", "simulink.library_load", "simulink.core_build_structure"]


def test_unknown_required_parameters_block_build_before_runtime_selection(tmp_path):
    mapping = make_mapping_contract(tmp_path, known_parameters=False)
    route = resolve_runtime("simulink_build", mapping_path=mapping)
    assert route["status"] == "blocked", route["errors"]
    assert "mapping_contract_build_ready" in route["missing_gates"]
    assert any("native_parameter_scalar_known" in gate for gate in route["missing_gates"])
    assert route["selected_operations"] == []
    assert not route["implementation_execution_allowed"]


def test_unqualified_domain_can_be_reviewed_but_cannot_activate_a_native_builder(tmp_path):
    mapping = make_mapping_contract(tmp_path)
    value = load_document(mapping)
    value["targets"][0]["domain"] = "simscape"
    mapping.write_text(json.dumps(value), encoding="utf-8")
    route = resolve_runtime("domain_mapping", mapping_path=mapping)
    assert route["status"] == "inspected", route["errors"]
    assert route["mapping_validation"]["mapping_complete"]
    assert not route["mapping_validation"]["build_ready"]
    assert_mapping_only(route)
    route = resolve_runtime("simulink_build", mapping_path=mapping)
    assert route["status"] == "blocked"
    assert "native_domain_deferred:simscape" in route["missing_gates"]
    assert not route["activated_modules"] and not route["implementation_execution_allowed"]


def test_current_a_and_d_qualification_allow_only_supported_implementation_execution(tmp_path):
    from native_factory import make_implementation_profile

    mapping = make_mapping_contract(tmp_path)
    profile = make_profile(tmp_path / "runtime")
    native_profile = make_implementation_profile(tmp_path / "native-profile", profile)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    route = resolve_runtime("simulink_build", mapping_path=mapping, profile_path=profile,
                            implementation_profile_path=native_profile)
    assert route["status"] == "allowed", route["errors"]
    assert route["phase"] == "D" and route["execution_scope"] == "implementation_execution"
    assert route["execution_allowed"] and route["implementation_execution_allowed"]
    assert not route["business_execution_allowed"] and not route["simulation_execution_allowed"]
    assert route["implementation_profile_sha256"] == sha256_file(native_profile)
    assert route["mapping_contract_sha256"] == sha256_file(mapping)
    assert not route["missing_gates"] and not route["state_mutated"]
    assert not route["upstream_skills"] and not route["activated_packs"]
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before
    completed = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/resolve_runtime.py"),
        "--intent", "simulink_build", "--mapping", str(mapping), "--profile", str(profile),
        "--implementation-profile", str(native_profile)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout
    cli_route = json.loads(completed.stdout)
    assert cli_route["implementation_execution_allowed"] is True
    assert cli_route["simulation_execution_allowed"] is False
    assert cli_route["mapping_contract_sha256"] == route["mapping_contract_sha256"]


def test_d_profile_is_insufficient_without_independent_current_a_qualification(tmp_path):
    from native_factory import make_implementation_profile

    mapping = make_mapping_contract(tmp_path)
    profile = make_profile(tmp_path / "runtime")
    native_profile = make_implementation_profile(tmp_path / "native-profile", profile)
    route = resolve_runtime("simulink_build", mapping_path=mapping, implementation_profile_path=native_profile)
    assert route["status"] == "blocked" and "capability_profile_current" in route["missing_gates"]
    assert not route["implementation_execution_allowed"]


def test_different_individually_qualified_runtime_profiles_cannot_be_combined(tmp_path):
    from native_factory import make_implementation_profile

    mapping = make_mapping_contract(tmp_path)
    profile = make_profile(tmp_path / "runtime")
    other_profile = make_profile(tmp_path / "other-runtime")
    native_profile = make_implementation_profile(tmp_path / "native-profile", other_profile)
    route = resolve_runtime("simulink_build", mapping_path=mapping, profile_path=profile,
                            implementation_profile_path=native_profile)
    assert route["status"] == "blocked", route["errors"]
    assert "implementation_runtime_matches" in route["missing_gates"]
    assert not route["implementation_execution_allowed"]


def test_implementation_ready_does_not_activate_simulation_or_unqualified_domains(tmp_path):
    from test_mapping_state import ready_native_project

    mapping, profile, native_profile, receipt, state = ready_native_project(tmp_path)
    for intent in ("simulation_execution", "simscape_build", "stateflow_build"):
        route = resolve_runtime(intent, state_path=state)
        assert route["status"] == ("blocked" if intent == "simulation_execution" else "deferred"), route["errors"]
        assert not route["execution_allowed"] and not route["simulation_execution_allowed"]
        assert not route["implementation_execution_allowed"] and not route["activated_modules"]
        if intent == "simulation_execution":
            assert "model_structure_checked" not in route["missing_gates"]
            assert "simulation_protocol_supplied" in route["missing_gates"]
