"""Adapter metadata checks; no installation or upstream tool execution."""
import re

from runtime_common import ROOT, load_document


def test_actual_pinned_skill_paths_and_license_resources_are_closed():
    mapping = load_document(ROOT / "adapters/mathworks/skill_mapping.yaml")
    pin = load_document(ROOT / mapping["pin_file"])
    repos = {item["repository"]: item for item in pin["repositories"]}
    assert repos["matlab/simulink-agentic-toolkit"]["commit"] == "c58e6aec7b904769ae43536e169d747feda95416"
    for repo in repos.values():
        assert re.fullmatch(r"[0-9a-f]{40}", repo["commit"])
        resources = {item["path"]: item for item in repo["resources"]}
        assert {"LICENSE.md", "manifest.yaml", "README.md"} <= set(resources)
        for item in resources.values():
            assert re.fullmatch(r"[0-9a-f]{40}", item["git_blob_sha1"])
            assert re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
            assert item["url"] == "https://github.com/" + repo["repository"] + "/blob/" + repo["commit"] + "/" + item["path"]
    for skill in mapping["skills"]:
        resources = {item["path"] for item in repos[skill["repository"]]["resources"]}
        assert skill["skill_path"] in resources and skill["manifest_path"] in resources
        assert skill["skill_path"].endswith("/" + skill["id"] + "/SKILL.md")


def test_adapter_range_and_native_fallback_do_not_claim_toolkit_installation():
    compatibility = load_document(ROOT / "adapters/mathworks/compatibility.yaml")
    assert compatibility["target_release"] == "R2025b"
    assert compatibility["upstream_installation"]["detected"] is False
    assert compatibility["upstream_installation"]["executed"] is False
    assert compatibility["upstream_compatibility"]["actual_tools_qualified"] is False
    assert compatibility["native_fallback"]["simulation_allowed"] is False
    assert compatibility["active_native_operation"] == "simulink.core_build_structure"
    assert compatibility["active_native_operation"] != "simulink.library_load"
    assert not compatibility["license"]["redistributed_upstream_code"]


def test_simulation_adapter_requires_current_a_e_and_individually_qualified_solver():
    compatibility = load_document(ROOT / "adapters/mathworks/compatibility.yaml")
    assert set(compatibility["active_native_operations"]) == {"simulink.core_build_structure", "simulink.core_simulation"}
    simulation = compatibility["simulation_fallback"]
    assert simulation["operation"] == "simulink.core_simulation"
    assert simulation["current_required_independent_profiles"] == ["phase_a_required_operations", "phase_e_core_simulation"]
    assert simulation["baseline_solvers"] == ["ode45", "ode4"]
    assert simulation["candidate_solvers"] == ["ode15s"]
    assert not simulation["toolkit_execution_qualified"]
    mapping = load_document(ROOT / "adapters/mathworks/skill_mapping.yaml")
    by_id = {item["id"]: item for item in mapping["skills"]}
    assert by_id["simulating-simulink-models"]["skill_path"] == "skills-catalog/model-based-design-core/simulating-simulink-models/SKILL.md"
    assert by_id["authoring-simulink-inputs"]["skill_path"] == "skills-catalog/simulink-simulation/authoring-simulink-inputs/SKILL.md"
