"""Read-only mathematical mapping and bounded native implementation gates."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from runtime_common import canonical_digest, emit, load_contract, load_document, schema_errors, sha256_file
from validate_model_contract import validate_model_contract
from validate_parameter_provenance import (MATLAB_KEYWORDS, MATLAB_NAME, bind_file, json_value,
    main_model_keys, mathematical_models, model_anchors, ref_key, validate_parameter_provenance)

REVIEW_FIELDS = ("mathematical_semantics", "interfaces_units", "initial_boundary_events", "scope_and_defaults")
NATIVE_BLOCKS = {"Inport": {"Port"}, "Outport": {"Port"}, "Constant": {"Value"},
                 "Gain": {"Gain"}, "Sum": {"Inputs"}, "Integrator": {"InitialCondition"}}
SUM_INPUTS = {"++", "+-", "-+", "--"}


def semantic_digest(contract):
    return canonical_digest({key: value for key, value in contract.items() if key not in {"status", "implementation"}})


def finite_scalar(value):
    # Conservative exact integer range for MATLAB's baseline double storage.
    return (type(value) is int and abs(value) <= 2**53) or (type(value) is float and math.isfinite(value))


def _condition_value(reference, models):
    model = models.get((reference["design_id"], reference["model_id"]))
    if model is None:
        raise ValueError("unknown C condition model reference")
    condition = model["body"][reference["field"]]
    if condition["status"] != "specified":
        return None
    value = condition["value"]
    for item in reference["selector"]:
        if type(value) is dict and type(item) is str and item in value:
            value = value[item]
        elif type(value) is list and type(item) is int and 0 <= item < len(value):
            value = value[item]
        else:
            raise ValueError("condition selector does not identify an actual C value")
    return value


def _subjects(body):
    result = {(kind, item["id"]) for kind, field in (("relation", "relations"), ("variable", "variables"),
              ("mechanism", "mechanisms"), ("assumption", "assumptions")) for item in body[field]}
    result |= {(kind, identity) for kind, field in (("input", "inputs"), ("output", "outputs")) for identity in body[field]}
    result |= {("initial_conditions", None), ("boundary_conditions", None)}
    return result


def _check_target(target, model, errors, missing, parameter_index, models):
    label = f"target:{target['id']}"
    blocks = {block["id"]: block for block in target["blocks"]}
    if len(blocks) != len(target["blocks"]):
        errors.append(f"{label}: block IDs must be unique")
    paths = [block["path"] for block in target["blocks"]]
    if len(set(paths)) != len(paths):
        errors.append(f"{label}: implementation paths must be unique")
    connections, driven = set(), set()
    for connection in target["connections"]:
        source, destination = connection["source"], connection["destination"]
        edge = (source["block_id"], source["port"], destination["block_id"], destination["port"])
        if edge in connections:
            errors.append(f"{label}: duplicate connection")
        connections.add(edge)
        endpoint = (destination["block_id"], destination["port"])
        if endpoint in driven:
            errors.append(f"{label}: input port has multiple drivers")
        driven.add(endpoint)
        for point in (source, destination):
            if point["block_id"] not in blocks:
                errors.append(f"{label}: connection references an unknown block")
            if type(point["port"]) is not int:
                errors.append(f"{label}: port must be an actual positive integer")
    expected = _subjects(model["body"])
    traced = set()
    for trace in target["traces"]:
        subject = (trace["kind"], trace["subject_id"])
        if subject in traced:
            errors.append(f"{label}: duplicate mathematical trace subject")
        traced.add(subject)
        if subject not in expected:
            errors.append(f"{label}: unknown mathematical trace subject {subject}")
        if set(trace["block_ids"]) - set(blocks):
            errors.append(f"{label}: trace references an unknown block")
        if trace["disposition"] == "mapped" and not trace["block_ids"]:
            missing.append(f"trace_objects:{target['id']}:{trace['kind']}:{trace['subject_id']}")
        if trace["disposition"] == "not_applicable" and trace["block_ids"]:
            errors.append(f"{label}: not_applicable trace must not claim implementation objects")
        if trace["kind"] in {"relation", "input", "output"} and trace["disposition"] != "mapped":
            missing.append(f"material_trace:{target['id']}:{trace['kind']}:{trace['subject_id']}")
        if trace["kind"] in {"initial_conditions", "boundary_conditions"}:
            condition = model["body"][trace["kind"]]
            if condition["status"] == "specified" and trace["disposition"] != "mapped":
                missing.append(f"condition_trace:{target['id']}:{trace['kind']}")
    if not blocks:
        missing.append(f"implementation_objects:{target['id']}")
    for block in blocks.values():
        for name, binding in block["parameters"].items():
            if "parameter_ref" in binding:
                key = ref_key(binding["parameter_ref"])
                if key not in parameter_index:
                    errors.append(f"{label}.{block['id']}.{name}: unknown parameter binding")
                elif key[:2] != (target["design_id"], target["model_id"]):
                    errors.append(f"{label}.{block['id']}.{name}: parameter belongs to another mathematical model")
            elif "value_ref" in binding:
                reference = binding["value_ref"]
                if (reference["design_id"], reference["model_id"]) != (target["design_id"], target["model_id"]):
                    errors.append(f"{label}.{block['id']}.{name}: condition belongs to another mathematical model")
                try:
                    _condition_value(reference, models)
                except (ValueError, KeyError, TypeError) as error:
                    errors.append(f"{label}.{block['id']}.{name}: {error}")
    return traced


def _native_spec(targets, parameters, models):
    """Translate declared safe bindings only; never interpret C expressions."""
    missing = []
    if len(targets) != 1:
        return None, ["native_single_target_required"]
    target = targets[0]
    if target["domain"] != "simulink":
        return None, [f"native_domain_deferred:{target['domain']}"]
    model_name = target["model_name"]
    if model_name in MATLAB_KEYWORDS:
        missing.append("native_model_name")
    selected = [item for item in parameters if ref_key(item["reference"])[:2] == (target["design_id"], target["model_id"])]
    parameter_index = {ref_key(item["reference"]): item for item in selected}
    assignments = []
    for parameter in selected:
        if parameter["scope"]["owner"] != model_name:
            missing.append(f"native_parameter_owner:{parameter['code_name']}")
        if parameter["code_name"] == model_name:
            missing.append(f"native_parameter_model_name_collision:{parameter['code_name']}")
        if not finite_scalar(parameter["value"]):
            missing.append(f"native_parameter_scalar_known:{parameter['code_name']}")
        else:
            assignments.append({"code_name": parameter["code_name"], "value": parameter["value"], "unit": parameter["unit"]})
    blocks = []
    counts = {}
    for block in target["blocks"]:
        identity, kind = block["id"], block["type"]
        if not MATLAB_NAME.fullmatch(identity) or identity in MATLAB_KEYWORDS or block["path"] != f"{model_name}/{identity}":
            missing.append(f"native_flat_block_path:{identity}")
        if kind not in NATIVE_BLOCKS:
            missing.append(f"native_block_deferred:{kind}")
            continue
        counts[identity] = (0, 1) if kind in {"Inport", "Constant"} else (1, 0) if kind == "Outport" else (2, 1) if kind == "Sum" else (1, 1)
        if set(block["parameters"]) != NATIVE_BLOCKS[kind]:
            missing.append(f"native_explicit_parameters:{identity}")
        values = {}
        for name, binding in block["parameters"].items():
            if name not in NATIVE_BLOCKS[kind]:
                continue
            if kind in {"Constant", "Gain"}:
                parameter = parameter_index.get(ref_key(binding["parameter_ref"])) if "parameter_ref" in binding else None
                if parameter is None:
                    missing.append(f"native_parameter_ref_required:{identity}.{name}")
                else:
                    values[name] = parameter["code_name"]
            elif kind == "Integrator":
                if "value_ref" not in binding:
                    missing.append(f"native_approved_initial_value_required:{identity}")
                else:
                    reference = binding["value_ref"]
                    value = _condition_value(reference, models)
                    if reference["field"] != "initial_conditions" or not finite_scalar(value):
                        missing.append(f"native_initial_scalar_known:{identity}")
                    else:
                        values[name] = str(value)
            else:
                setting = binding.get("setting")
                if kind == "Sum":
                    if not setting or setting["kind"] != "enum" or setting["value"] not in SUM_INPUTS:
                        missing.append(f"native_sum_inputs_enum:{identity}")
                    else:
                        values[name] = setting["value"]
                elif not setting or setting["kind"] != "port" or type(setting["value"]) is not int or setting["value"] < 1:
                    missing.append(f"native_port_setting:{identity}")
                else:
                    values[name] = str(setting["value"])
        blocks.append({"id": identity, "path": block["path"], "type": kind, "parameters": values})
    port_numbers = {"Inport": [], "Outport": []}
    for block in blocks:
        if block["type"] in port_numbers and "Port" in block["parameters"]:
            port_numbers[block["type"]].append(int(block["parameters"]["Port"]))
    for kind, ports in port_numbers.items():
        if ports and sorted(ports) != list(range(1, len(ports) + 1)):
            missing.append(f"native_contiguous_{kind.lower()}_ports")
    driven = set()
    for connection in target["connections"]:
        for direction, point in ((1, connection["source"]), (0, connection["destination"])):
            count = counts.get(point["block_id"], (0, 0))[direction]
            if type(point["port"]) is not int or not 1 <= point["port"] <= count:
                missing.append(f"native_endpoint:{point['block_id']}:{point['port']}")
        driven.add((connection["destination"]["block_id"], connection["destination"]["port"]))
    for identity, (inputs, _) in counts.items():
        if any((identity, port) not in driven for port in range(1, inputs + 1)):
            missing.append(f"native_required_input_connection:{identity}")
    spec = {"schema_version": 1, "model_name": model_name, "blocks": blocks,
            "connections": target["connections"], "parameters": assignments}
    if not missing:
        # Keep the mapping gate aligned with the actual producer's accepted API.
        # This helper validates data only; it never invokes MATLAB.
        try:
            from validate_implementation_profile import validate_build_spec
            validate_build_spec(spec)
        except (ImportError, ValueError, KeyError, TypeError, OverflowError) as error:
            missing.append(f"native_builder_spec:{error}")
    return (None if missing else spec), missing


def validate_domain_mapping(path, *, project_root=None, require_mapped=False, require_ready=False):
    result = {"schema_valid": False, "valid": False, "mapping_complete": False,
              "build_ready": False, "built": False, "structure_checked": False, "implementation_ready": False,
              "implementation_checked": False, "current_model_approved": False,
              "project_id": None, "semantic_sha256": None, "contract_sha256": None,
              "model_path": None, "model_sha256": None, "model_semantic_sha256": None,
              "model_approval_path": None, "model_approval_sha256": None,
              "locked_model_path": None, "locked_model_sha256": None,
              "parameters_path": None, "parameters_sha256": None,
              "parameter_provenance_path": None, "parameter_provenance_sha256": None,
              "implementation_path": None, "implementation_sha256": None,
              "native_model_path": None, "native_model_sha256": None,
              "native_structure_validation": None, "build_spec": None, "build_spec_sha256": None,
              "mapping_snapshot": None, "bound_files": [], "native_missing_gates": [],
              "errors": [], "missing_gates": [], "changed_sources": []}
    errors, missing, changed = result["errors"], result["missing_gates"], result["changed_sources"]
    try:
        path = Path(path).resolve()
        root = Path(project_root).resolve() if project_root is not None else path.parent
        if not path.is_relative_to(root):
            raise ValueError("contract path leaves project root")
        contract = load_document(path)
        result["contract_sha256"] = sha256_file(path)
        json_value(contract)
        errors.extend(schema_errors(contract, load_contract("core/domain_mapping.schema.yaml")))
        if errors:
            return result
        snapshot = {key: value for key, value in contract.items() if key not in {"status", "implementation"}}
        result.update(schema_valid=True, project_id=contract["project_id"],
                      semantic_sha256=semantic_digest(contract), mapping_snapshot=snapshot)
        model = None
        model_path = bind_file(root, contract["model"], "model", errors, changed, result["bound_files"])
        if model_path:
            model = load_document(model_path)
            report = validate_model_contract(model_path, project_root=root)
            result["model_validation"] = report
            if not report["valid"]:
                errors.extend(f"model: {error}" for error in report["errors"])
                changed.extend(f"model:{item}" for item in report["changed_sources"])
            if report["schema_valid"]:
                result.update(model_anchors(root, model_path, model, report, errors, changed, result["bound_files"]))
                if report["project_id"] != contract["project_id"]:
                    errors.append("model: project_id differs from mapping")
                result["current_model_approved"] = report["approved"] and report["valid"]
            else:
                model = None
        if not result["current_model_approved"]:
            missing.append("current_human_model_approval")
        parameters_path = bind_file(root, contract["parameters"], "parameters", errors, changed, result["bound_files"])
        parameter_report = None
        if parameters_path:
            result.update(parameters_path=str(parameters_path), parameters_sha256=sha256_file(parameters_path),
                          parameter_provenance_path=str(parameters_path), parameter_provenance_sha256=sha256_file(parameters_path))
            parameter_report = validate_parameter_provenance(parameters_path, project_root=root)
            result["parameter_validation"] = parameter_report
            if not parameter_report["valid"]:
                errors.extend(f"parameters: {error}" for error in parameter_report["errors"])
                changed.extend(f"parameters:{item}" for item in parameter_report["changed_sources"])
            if parameter_report["project_id"] != contract["project_id"]:
                errors.append("parameters: project_id differs from mapping")
            if parameter_report["model_path"] != result["model_path"] or parameter_report["model_sha256"] != result["model_sha256"]:
                errors.append("parameters: model binding differs from mapping")
            if not parameter_report["binding_complete"] or parameter_report["status"] != "bound":
                missing.append("current_parameter_bindings")
        else:
            missing.append("parameter_provenance_supplied")
        parameters = parameter_report["parameters"] if parameter_report else []
        parameter_index = {ref_key(item["reference"]): item for item in parameters}
        sources = {source["id"]: source for source in contract["sources"]}
        if len(sources) != len(contract["sources"]):
            errors.append("mapping source IDs must be unique")
        for identity, source in sources.items():
            bind_file(root, source, f"mapping_source:{identity}", errors, changed, result["bound_files"])
        for field, review in contract["reviews"].items():
            if set(review["source_ids"]) - set(sources):
                errors.append(f"review:{field}: unknown mapping source reference")
            if review["status"] in {"pending", "blocked"}:
                missing.append(f"mapping_review:{field}:{review['status']}")
        models = mathematical_models(model) if model else {}
        required = main_model_keys(model) if model else set()
        targets, target_ids, target_names, traced_by_model = set(), set(), set(), {}
        for target in contract["targets"]:
            key = (target["design_id"], target["model_id"])
            if target["id"] in target_ids:
                errors.append("mapping target IDs must be unique")
            target_ids.add(target["id"])
            if target["model_name"] in target_names:
                errors.append("mapping model_name must identify a unique implementation target")
            target_names.add(target["model_name"])
            targets.add(key)
            if key not in models:
                errors.append(f"target:{target['id']}: unknown C model reference")
            elif key not in required:
                errors.append(f"target:{target['id']}: target must reference a selected C main_model")
            else:
                traced_by_model.setdefault(key, set()).update(_check_target(target, models[key], errors, missing, parameter_index, models))
        for key in required:
            if _subjects(models[key]["body"]) - traced_by_model.get(key, set()):
                missing.append(f"mathematical_trace_coverage:{key[0]}:{key[1]}")
        if not targets or required - targets:
            missing.append("selected_main_model_mapping_coverage")
        result["mapping_complete"] = bool(model) and result["current_model_approved"] and not errors and not missing
        if result["mapping_complete"]:
            spec, native_missing = _native_spec(contract["targets"], parameters, models)
            result["native_missing_gates"] = sorted(set(native_missing))
            result["build_spec"] = spec
            result["build_spec_sha256"] = canonical_digest(spec) if spec else None
            result["build_ready"] = spec is not None and contract["status"] in {"mapped", "ready"}
        if contract["implementation"] is not None:
            receipt_path = bind_file(root, contract["implementation"], "implementation", errors, changed, [])
            if receipt_path:
                result.update(implementation_path=str(receipt_path), implementation_sha256=sha256_file(receipt_path), implementation_checked=True)
                try:
                    from validate_implementation_receipt import validate_implementation_receipt
                    receipt_report = validate_implementation_receipt(receipt_path, project_root=root, mapping_report=result)
                    result["native_structure_validation"] = receipt_report
                    result["built"] = bool(receipt_report.get("valid") and receipt_report.get("built"))
                    result["structure_checked"] = bool(receipt_report.get("valid") and receipt_report.get("structure_checked"))
                    result["native_model_path"] = receipt_report.get("model_path")
                    result["native_model_sha256"] = receipt_report.get("model_sha256")
                    if not receipt_report.get("valid"):
                        errors.extend(f"implementation: {error}" for error in receipt_report.get("errors", []))
                        changed.extend(f"implementation:{item}" for item in receipt_report.get("changed_sources", []))
                except ImportError:
                    missing.append("native_receipt_consumer_implemented")
        if not result["structure_checked"]:
            missing.append("actual_native_structure_receipt")
        result["implementation_ready"] = (contract["status"] == "ready" and result["mapping_complete"] and
                                          result["build_ready"] and result["built"] and result["structure_checked"] and not errors)
        if contract["status"] in {"mapped", "ready"} and not result["mapping_complete"]:
            errors.append("status: mapped/ready requires a complete current mathematical mapping")
        if contract["status"] == "ready" and not result["implementation_ready"]:
            errors.append("status: ready requires actual current supported implementation and structure evidence")
        if require_mapped and (contract["status"] not in {"mapped", "ready"} or not result["mapping_complete"]):
            errors.append("required mapped gate is not satisfied")
        if require_ready and not result["implementation_ready"]:
            errors.append("required implementation-ready gate is not satisfied")
        result["valid"] = not errors
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors.append(str(error))
    result["missing_gates"] = sorted(set(missing + result["native_missing_gates"]))
    result["changed_sources"] = sorted(set(changed))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--require-mapped", action="store_true")
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    report = validate_domain_mapping(args.path, project_root=args.project_root,
                                     require_mapped=args.require_mapped, require_ready=args.require_ready)
    emit(report)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
