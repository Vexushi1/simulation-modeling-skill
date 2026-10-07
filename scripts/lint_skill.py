"""Check Phase A authorities, schemas, routing availability and navigation."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from generate_indexes import render_indexes, source_paths
from runtime_common import ROOT, UniqueLoader, emit, load_document, schema_errors


def lint(root: Path = ROOT) -> list[str]:
    errors = []
    try:
        paths = source_paths(root)
        for name in paths:
            if name.endswith((".yaml", ".yml")):
                data = load_document(root / name)
                if "$schema" in data:
                    schema_errors({}, data)  # checks the schema itself; instance errors are irrelevant here
        manifest = load_document(root / "manifest.yaml")
        bootstrap = load_document(root / "core/bootstrap.yaml")
        module_manifest = load_document(root / "core/module_manifest.yaml")
        taxonomy = load_document(root / "core/capability_taxonomy.yaml")
        runtime = load_document(root / "core/runtime_assurance_contract.yaml")
        baseline = load_document(root / "core/environment_baseline.yaml")
        router = load_document(root / "core/workflow_router.yaml")
        bindings = {
            "router": "core/workflow_router.yaml", "module_manifest": "core/module_manifest.yaml",
            "resolver": "scripts/resolve_runtime.py", "state_schema": "core/project_state.schema.yaml",
            "output_contract": "core/output_contract.yaml",
        }
        if bootstrap["runtime_entry"] != bindings:
            errors.append("bootstrap runtime entry differs from implemented consumers")
        for name in bindings.values():
            if not (root / name).is_file():
                errors.append(f"missing runtime entry: {name}")
        router_bindings = {"module_manifest": bindings["module_manifest"],
                           "capability_taxonomy": "core/capability_taxonomy.yaml",
                           "runtime_contract": "core/runtime_assurance_contract.yaml",
                           "project_state_schema": bindings["state_schema"]}
        if any(router.get(key) != value for key, value in router_bindings.items()):
            errors.append("router Authority references differ from implemented consumers")
        upstream = {"simulink_execution": "matlab/simulink-agentic-toolkit",
                    "matlab_execution": "matlab/matlab-agentic-toolkit"}
        if manifest["upstream_authorities"] != upstream:
            errors.append("official upstream repository names disagree")
        integration = (root / "core/upstream_integration_policy.md").read_text(encoding="utf-8")
        if any(f"`{name}`" not in integration for name in upstream.values()):
            errors.append("official upstream names are missing from the integration Authority")
        for name in manifest["active_authorities"]:
            if not (root / name).is_file():
                errors.append(f"missing authority: {name}")
        if "docs/V1_FULL_IMPLEMENTATION_PLAN.md" not in manifest["active_authorities"]:
            errors.append("full development plan is not an active authority")
        if bootstrap["development_authority"] != "docs/V1_FULL_IMPLEMENTATION_PLAN.md":
            errors.append("bootstrap development authority differs from full plan")
        versions = [bootstrap["version"], module_manifest["version"],
                    load_document(root / "core/output_contract.yaml")["version"]]
        frontmatter = (root / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[1]
        skill = yaml.load(frontmatter, Loader=UniqueLoader)
        versions.append(skill["metadata"]["version"])
        if any(str(version) != str(manifest["version"]) for version in versions):
            errors.append("active version carriers disagree")
        if (baseline["baseline"]["matlab_release"] != "R2025b"
                or runtime["target"]["matlab_release"] != "R2025b"
                or manifest["primary_runtime"]["release"] != "R2025b"):
            errors.append("runtime baseline must be R2025b")
        if str(baseline["baseline"]["simulink_version"]) != "25.2" or str(runtime["target"]["simulink_version"]) != "25.2":
            errors.append("Simulink baseline must be 25.2")
        if "quarantined_capabilities" in baseline or any(key.endswith("_available") for key in baseline):
            errors.append("baseline cannot contain historical/static availability decisions")
        if "Statistics and Machine Learning Toolbox" not in baseline["candidate_products"]:
            errors.append("Statistics must remain an ordinary runtime candidate")
        for name in runtime["evidence_policy"]["source_files"]:
            path = (root / name).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                errors.append(f"invalid runtime source binding: {name}")
        core_operations = ["matlab.basic_execution", "simulink.library_load"]
        modules = module_manifest["modules"]
        if runtime["core_operations"] != core_operations or modules["environment_assurance"]["required_operations"] != core_operations:
            errors.append("core operation selection differs between contracts")
        for identity, module in modules.items():
            if module["status"] == "implemented":
                if identity != "environment_assurance" or module["phase"] != "A":
                    errors.append(f"business capability activated before implementation: {identity}")
                for path in module["resources"]:
                    if not (root / path).is_file():
                        errors.append(f"missing module resource: {path}")
            elif module["status"] != "deferred" or module["resources"]:
                errors.append(f"invalid deferred module: {identity}")
        for identity, item in taxonomy["capabilities"].items():
            if identity not in modules or modules[identity]["status"] != "deferred" or modules[identity]["phase"] != item["phase"]:
                errors.append(f"taxonomy availability mismatch: {identity}")
        if router["intents"]["inspect"]["execution_allowed"] is not False:
            errors.append("inspect cannot grant execution")
        if router["future_capabilities"]["execution_allowed"] is not False:
            errors.append("future capabilities cannot grant execution")

        graph = bootstrap["authority_graph"]
        edges = {node: [] for node in graph["nodes"]}
        for name in graph["nodes"].values():
            if not (root / name).is_file():
                errors.append(f"missing Authority graph node: {name}")
        for parent, child in graph["edges"]:
            if parent not in edges or child not in edges:
                errors.append(f"unknown Authority edge: {parent}->{child}")
            else:
                edges[parent].append(child)
        visiting, visited = set(), set()
        def visit(node):
            if node in visiting:
                errors.append(f"Authority cycle at {node}")
                return
            if node in visited:
                return
            visiting.add(node)
            for child in edges[node]:
                visit(child)
            visiting.remove(node)
            visited.add(node)
        for node in edges:
            visit(node)
        for name in paths:
            if not name.endswith(".md") or not (root / name).is_file():
                continue
            text = (root / name).read_text(encoding="utf-8")
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
                if target.startswith(("https://", "http://", "#")):
                    continue
                target = target.split("#", 1)[0]
                if not ((root / name).parent / target).exists():
                    errors.append(f"{name}: missing Markdown target {target}")
        for name, content in render_indexes(root).items():
            if not (root / name).is_file() or (root / name).read_text(encoding="utf-8") != content:
                errors.append(f"stale generated index: {name}")
    except (ValueError, OSError, TypeError, KeyError, IndexError) as error:
        errors.append(str(error))
    return errors


if __name__ == "__main__":
    errors = lint()
    emit({"valid": not errors, "errors": errors, "scope": "static repository checks; no MATLAB qualification"})
    raise SystemExit(1 if errors else 0)
