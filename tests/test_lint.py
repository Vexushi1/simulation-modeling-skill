"""Mutate copied authorities to verify the repository checks detect real drift."""
import shutil

import pytest

from generate_indexes import render_indexes, source_paths
from lint_skill import lint
from runtime_common import ROOT, load_document, schema_errors


@pytest.fixture
def copy_repo(tmp_path):
    target = tmp_path / "repo"
    for name in source_paths(ROOT):
        source = ROOT / name
        if source.is_file():
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    return target


def test_current_repository_and_indexes_are_consistent():
    assert lint() == []
    assert all((ROOT / name).read_text(encoding="utf-8") == text for name, text in render_indexes().items())


def test_index_enumeration_excludes_local_runs_and_caches(tmp_path):
    for directory in (".git", ".pytest_cache", "local-runs", "outputs"):
        hidden = tmp_path / directory / "large-run" / "record.json"
        hidden.parent.mkdir(parents=True)
        hidden.write_text("{}", encoding="utf-8")
    (tmp_path / "actual.txt").write_text("source", encoding="utf-8")
    assert source_paths(tmp_path) == ["REPOSITORY_INDEX.md", "SKILL_FILE_INDEX.md", "actual.txt"]


def test_missing_active_authority_is_detected(copy_repo):
    (copy_repo / "core/project_state.schema.yaml").unlink()
    assert any("missing authority" in error for error in lint(copy_repo))


def test_missing_real_resource_is_detected(copy_repo):
    (copy_repo / "scripts/matlab/probe_environment.m").unlink()
    assert any("missing module resource" in error for error in lint(copy_repo))


def test_future_capability_cannot_be_activated_by_manifest_change(copy_repo):
    path = copy_repo / "core/module_manifest.yaml"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("status: deferred", "status: implemented", 1), encoding="utf-8")
    assert any("activated before implementation" in error for error in lint(copy_repo))


def test_problem_audit_cannot_select_runtime_operations(copy_repo):
    path = copy_repo / "core/module_manifest.yaml"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("required_operations: []", "required_operations: [matlab.basic_execution]"), encoding="utf-8")
    assert any("cannot require numerical operations" in error for error in lint(copy_repo))


def test_problem_module_cannot_omit_its_validator(copy_repo):
    path = copy_repo / "core/module_manifest.yaml"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("    - scripts/validate_problem_contract.py\n", ""), encoding="utf-8")
    assert any("omits required contract resources" in error for error in lint(copy_repo))


def test_model_design_cannot_select_runtime_operations(copy_repo):
    path = copy_repo / "core/module_manifest.yaml"
    text = path.read_text(encoding="utf-8")
    marker = "  model_design:"
    before, after = text.split(marker, 1)
    path.write_text(before + marker + after.replace("required_operations: []", "required_operations: [matlab.basic_execution]", 1), encoding="utf-8")
    assert any("model design cannot require numerical operations" in error for error in lint(copy_repo))


def test_model_module_cannot_omit_approval_contract(copy_repo):
    path = copy_repo / "core/module_manifest.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("    - core/model_approval_contract.yaml\n", ""), encoding="utf-8")
    assert any("model module omits required contract resources" in error for error in lint(copy_repo))


def test_mapping_cannot_grant_execution(copy_repo):
    path = copy_repo / "core/workflow_router.yaml"
    before, after = path.read_text(encoding="utf-8").split("  domain_mapping:", 1)
    path.write_text(before + "  domain_mapping:" + after.replace("execution_allowed: false", "execution_allowed: true", 1), encoding="utf-8")
    assert any("domain mapping cannot" in error for error in lint(copy_repo))


def test_mapping_module_cannot_omit_parameter_consumer(copy_repo):
    path = copy_repo / "core/module_manifest.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("  - scripts/validate_parameter_provenance.py\n", ""), encoding="utf-8")
    assert any("domain mapping module omits" in error for error in lint(copy_repo))


def test_d_output_cannot_grant_simulation(copy_repo):
    path = copy_repo / "core/output_contract.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("simulation_execution_allowed: false", "simulation_execution_allowed: true"), encoding="utf-8")
    assert any("cannot grant simulation" in error for error in lint(copy_repo))


def test_index_drift_is_detected(copy_repo):
    (copy_repo / "REPOSITORY_INDEX.md").write_text("stale", encoding="utf-8")
    assert any("stale generated index" in error for error in lint(copy_repo))


def test_runtime_consumer_drift_is_detected(copy_repo):
    path = copy_repo / "core/bootstrap.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("resolver: scripts/resolve_runtime.py", "resolver: missing.py"),
                    encoding="utf-8")
    assert any("runtime entry differs" in error for error in lint(copy_repo))


def test_target_version_drift_is_detected(copy_repo):
    path = copy_repo / "core/runtime_assurance_contract.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("simulink_version: '25.2'", "simulink_version: '25.1'"),
                    encoding="utf-8")
    assert any("Simulink baseline" in error for error in lint(copy_repo))


def test_duplicate_keys_and_nonfinite_values_are_rejected(tmp_path):
    path = tmp_path / "input.json"
    for text in ('{"a": 1, "a": 2}', '{"a": NaN}'):
        path.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError):
            load_document(path)
    path = tmp_path / "input.yaml"
    path.write_text("a: 1\na: 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_document(path)


def test_invalid_or_remote_schemas_fail_without_fetching():
    with pytest.raises(ValueError, match="invalid schema"):
        schema_errors({}, {"type": "imaginary"})
    with pytest.raises(ValueError, match="external references"):
        schema_errors({}, {"$ref": "https://invalid.example/schema.json"})
