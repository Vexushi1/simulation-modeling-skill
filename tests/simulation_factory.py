"""Source-bound E consumer fixtures; no MATLAB execution or actual approval.

These records exercise identity consumers only. Native qualification and the
independent original-input workflow must use actual MATLAB and separate sources.
"""
from __future__ import annotations

from pathlib import Path

from mapping_factory import make_mapping_contract
from model_factory import approve_contract, file_ref
from native_factory import make_implementation_profile, make_implementation_receipt
from problem_factory import freeze_contract, read_contract, write_contract
from runtime_common import load_document, sha256_file
from test_runtime import make_profile
from validate_domain_mapping import validate_domain_mapping
from validate_simulation_protocol import semantic_digest


def freeze_simulation_protocol(path):
    """Write an explicitly synthetic review; production consumers never do this."""
    path = Path(path)
    contract = load_document(path)
    digest = semantic_digest(contract)
    reviewer = "synthetic-protocol-reviewer"
    quote = (f"project_id={contract['project_id']}\nprotocol_semantic_sha256={digest}\n"
             f"reviewed_by={reviewer}\naction=freeze\n"
             "SYNTHETIC INFRASTRUCTURE REVIEW ONLY: no real human model approval or accepted numerical evidence.")
    decision_path = path.parent / "protocol-freeze-decision.txt"
    decision_path.write_text(quote + "\n", encoding="utf-8", newline="\n")
    record = {"schema_version": 1, "project_id": contract["project_id"], "protocol_semantic_sha256": digest,
              "decision": {**file_ref(path.parent, decision_path), "start": 0, "end": len(quote), "quote": quote,
                           "reviewed_by": reviewer, "action": "freeze"}}
    record_path = write_contract(path.parent / "protocol-freeze.json", record)
    contract.update(status="frozen", freeze_record=file_ref(path.parent, record_path))
    return write_contract(path, contract)


def _e_sources(root, mapping_path, *, approved_input=None, scalar_source_input=False, source_time=None):
    """Review E's synthetic scope before constructing its D evidence fixture."""
    problem_path = root / "problem.json"
    problem = read_contract(problem_path)
    replacements = {
        "R4": "Time domain: t in [0,1] s; only reviewed synthetic infrastructure simulation is requested.",
        "R5": "Q1: run the declared synthetic mathematical kernel after separate E protocol and runtime gates.",
        "R6": "Q1 deliverable: model structure, a reproducible infrastructure run and declared scalar output; no physical validity claim.",
        "R7": "Q2: review the explicit parameter and input/output bindings for the same synthetic kernel.",
        "R9": "Q2 deliverable: a source-bound protocol/run review; no fitting, numerical verification or reality claim.",
    }
    if approved_input is not None:
        replacements["R2"] = f"Input: commanded dimensionless signal u; the approved constant value is u={approved_input}."
    lines, offset = [], 0
    for unit in problem["audit_units"]:
        quote = replacements.get(unit["requirement_ids"][0], unit["quote"]) if unit["requirement_ids"] else unit["quote"]
        unit.update(start=offset, end=offset + len(quote), quote=quote)
        lines.append(quote)
        offset += len(quote) + 1
    statement = root / "statement.txt"
    statement.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    problem["sources"][0].update(file_ref(root, statement))
    problem["sources"][0]["text"].update(file_ref(root, statement))
    by_unit = {item["id"]: item for item in problem["audit_units"]}
    for requirement in problem["requirements"]:
        requirement["interpretation"] = by_unit[requirement["unit_ids"][0]]["quote"]
    by_requirement = {item["id"]: item for item in problem["requirements"]}
    for question in problem["questions"]:
        for fact in question["facts"].values():
            if fact["status"] == "specified" and len(fact["requirement_ids"]) == 1:
                fact["value"] = by_requirement[fact["requirement_ids"][0]]["interpretation"]
        question["facts"]["time_domain"]["value"] = source_time if source_time is not None else {"start": 0.0, "stop": 1.0, "unit": "s"}
        if approved_input is not None and question["facts"]["commanded_inputs"]["status"] == "specified":
            question["facts"]["commanded_inputs"]["value"] = approved_input if scalar_source_input else {"u": approved_input}
    problem.update(status="draft", freeze=None)
    write_contract(problem_path, problem)
    freeze_contract(problem_path)
    mapping = read_contract(mapping_path)
    model_path = root / mapping["model"]["path"]
    model = read_contract(model_path)
    brief = root / model["brief"]["path"]
    brief.write_text("# Synthetic E model review\n\nOnly this declared infrastructure kernel and its exact coefficients are reviewed.\n"
                     "E protocol, solver, numerical execution and qualification have separate gates.\n"
                     "No actual human approval, estimates, numerical verification or physical validation is represented.\n",
                     encoding="utf-8", newline="\n")
    model.update(problem=file_ref(root, problem_path), brief=file_ref(root, brief), approval=None, status="challenged")
    for design in model["designs"]:
        for item in design["models"]:
            item["solver_plan"] = {"status": "proposed", "method": "ode45 or explicitly reviewed fixed-step ode4",
                "risks": "Actual operation qualification and output checks belong to E; no numerical convergence claim",
                "reason": "Synthetic mathematical kernel for separate infrastructure execution testing"}
    write_contract(model_path, model)
    approve_contract(model_path)
    parameter_path = root / mapping["parameters"]["path"]
    parameters = read_contract(parameter_path)
    parameters["model"] = file_ref(root, model_path)
    write_contract(parameter_path, parameters)
    mapping.update(model=file_ref(root, model_path), parameters=file_ref(root, parameter_path))
    return write_contract(mapping_path, mapping)


def make_simulation_protocol(root, *, status="frozen", case="feedback", solver="ode45", root_output=True,
                             required_operations=None, age_hours=0, approved_input=None, input_value=1.0,
                             scalar_source_input=False, source_time=None):
    """Return a protocol bound to complete labelled Python D evidence fixtures."""
    root = Path(root).resolve()
    mapping_path = make_mapping_contract(root, case=case, root_output=root_output)
    _e_sources(root, mapping_path, approved_input=approved_input, scalar_source_input=scalar_source_input,
               source_time=source_time)
    a_profile = make_profile(root / "a-profile", include_statistics=True, age_hours=age_hours)
    d_profile = make_implementation_profile(root / "d-profile", a_profile, age_hours=age_hours)
    receipt = make_implementation_receipt(root / "implementation", mapping_path, a_profile, d_profile, age_hours=age_hours)
    mapping = read_contract(mapping_path)
    mapping.update(status="ready", implementation=file_ref(root, receipt))
    write_contract(mapping_path, mapping)
    report = validate_domain_mapping(mapping_path, project_root=root, require_ready=True)
    assert report["valid"] and report["implementation_ready"], report["errors"]
    target = mapping["targets"][0]
    model = read_contract(root / mapping["model"]["path"])
    selected_model = model["designs"][0]["models"][0]
    by_variable = {item["id"]: item for item in selected_model["body"]["variables"]}
    input_data = {"kind": "constant", "value": input_value, "time": [], "values": [], "interpolation": "zoh"}
    scenario_source = write_contract(root / "scenario-source.json", {"description": "Explicit synthetic E scenario only", "u": input_data})
    inputs, outputs = [], []
    for block in target["blocks"]:
        if block["type"] not in {"Inport", "Outport"}:
            continue
        field, trace_kind = (inputs, "input") if block["type"] == "Inport" else (outputs, "output")
        variable_id = next(item["subject_id"] for item in target["traces"] if item["kind"] == trace_kind and block["id"] in item["block_ids"])
        record = {"port": block["parameters"]["Port"]["setting"]["value"], "block_path": block["path"],
                  "variable_id": variable_id, "unit": by_variable[variable_id]["unit"]}
        if field is inputs:
            record.update(data=input_data, source_ref={"source_id": "scenario_data", "selector": ["u"]}, requirement_ids=["R2"],
                          reason="The explicit synthetic source and frozen review declare this finite infrastructure input")
        field.append(record)
    fixed = solver == "ode4"
    has_states = any(block["type"] == "Integrator" for block in target["blocks"])
    settings = {"name": solver, "type": "fixed-step" if fixed else "variable-step", "fixed_step": 0.01 if fixed else None,
        "max_step": None if fixed else 0.05, "min_step": None if fixed else 1e-12, "initial_step": None if fixed else 0.01,
        "rel_tol": None if fixed else 1e-6, "abs_tol": None if fixed else 1e-8, "zero_crossing": "DisableAll",
        "reason": "Explicit controlled fixture solver; actual native qualification is a separate requirement",
        "classification": {"dynamics": "continuous" if has_states else "algebraic", "stiffness": "non_stiff" if has_states else "not_applicable",
            "dae": False, "events": False, "algebraic_loop": False, "multirate": False, "real_time_codegen": False,
            "reason": "Declared scalar continuous Integrator feedback or stateless six-block synthetic core; no deferred semantics"}}
    contract = {"schema_version": 1, "project_id": mapping["project_id"], "status": "draft", "mapping": file_ref(root, mapping_path),
        "selection": {key: target[key] for key in ("design_id", "model_id")}, "parameter_set": mapping["parameters"],
        "sources": [{"id": "scenario_data", **file_ref(root, scenario_source), "purpose": "Original explicit synthetic input scenario for E review",
                     "model_source_id": None, "problem_source_id": None}],
        "scenario": {"id": "infrastructure_primary", "description": "Finite scalar synthetic infrastructure run, not numerical V&V",
                     "requirement_ids": ["R5"], "source_ids": ["scenario_data"]},
        "conditions": {key: selected_model["body"][key] for key in ("initial_conditions", "boundary_conditions")},
        "time": {"start": 0.0, "stop": 1.0, "unit": "s", "requirement_ids": ["R4"]}, "solver": settings,
        "inputs": inputs, "outputs": outputs, "logging": {"format": "Dataset", "output_variable": "yout", "time_variable": "tout",
                  "reason": "Root Outport Dataset without adding logging blocks or changing source SLX"},
        "seed": {"value": 1729, "generator": "twister", "reason": "Explicit reproducible infrastructure RNG state, restored after execution"},
        "metrics": [{"id": f"output_{item['port']}_final", "output_port": item["port"], "statistic": "final", "unit": item["unit"],
                     "lower": -1e6, "upper": 1e6, "reason": "Finite infrastructure output range only; no physical or convergence validation"} for item in outputs],
        "runtime_class": "normal_serial", "warning_policy": {"action": "record", "reason": "Record all actual warnings for explicit review"},
        "required_A_operations": list(required_operations or ["matlab.basic_execution", "simulink.library_load"]), "freeze_record": None}
    contract["selection"]["target_id"] = target["id"]
    path = write_contract(root / "simulation-protocol.json", contract)
    return freeze_simulation_protocol(path) if status == "frozen" else path
