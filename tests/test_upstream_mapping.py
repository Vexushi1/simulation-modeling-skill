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
