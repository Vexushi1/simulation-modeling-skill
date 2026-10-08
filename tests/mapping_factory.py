"""Explicit synthetic algebraic/feedback kernels; no real project approval."""
from __future__ import annotations

from pathlib import Path

from model_factory import approve_contract, file_ref, make_model_contract
from problem_factory import FACT_FIELDS, freeze_contract, read_contract, write_contract
from validate_domain_mapping import REVIEW_FIELDS


def _problem(root, case, root_output=True):
    path = root / "problem.json"
    problem = read_contract(path)
    problem.update(project_id=f"synthetic-{case}-kernel", status="draft", freeze=None, audit_units=[], requirements=[], data_uses=[])
    problem["sources"] = problem["sources"][:1]
    lines = ["SYNTHETIC INFRASTRUCTURE CASE ONLY; no real competition result or human approval.",
             f"System: a dimensionless {case} mathematical kernel.",
             "No external input is required: the constant kernel is y=k." if case == "constant" else "Input: commanded dimensionless signal u.",
             "Initial state: x(0)=0.25." if case == "feedback" else "The passthrough kernel y=u has no states, parameters or initial conditions." if case == "passthrough" else "The algebraic kernel has no initial state.",
             "Time domain: t in [0,1] s; no simulation is required in this case.",
             "Q1: inspect the declared mathematical-to-block structure.",
             "Q1 deliverable: a model file and structure evidence, no waveform." if root_output else "Q1 deliverable: a model file with internal mathematical output y; no root Outport or waveform is required.",
             "Q2: review the explicit absence of parameters and the direct input/output binding y=u." if case == "passthrough" else "Q2: review parameter and input/output bindings for the same kernel.",
             "No data attachment is used or required; no fitting or validation use is authorized.",
             "Q2 deliverable: a source-bound mapping review, no estimated parameters."]
    text = "\n".join(lines) + "\n"
    statement = root / "statement.txt"
    statement.write_text(text, encoding="utf-8", newline="\n")
    problem["sources"][0].update(file_ref(root, statement))
    problem["sources"][0]["text"].update(file_ref(root, statement))
    categories = [None, "original_system", None if case == "constant" else "commanded_inputs", "initial_conditions" if case == "feedback" else None,
                  "time_domain", "direct_goal", "deliverables", "direct_goal", None, "deliverables"]
    question_sets = [[], ["Q1", "Q2"], ["Q1", "Q2"], ["Q1", "Q2"], ["Q1", "Q2"], ["Q1"], ["Q1"], ["Q2"], ["Q2"], ["Q2"]]
    offset = 0
    for number, quote in enumerate(lines):
        category = categories[number]
        identity = f"R{number}"
        problem["audit_units"].append({"id": f"U{number}", "source_id": "statement", "start": offset,
            "end": offset + len(quote), "quote": quote, "disposition": "requirement" if category else "context",
            "reason": "Explicit synthetic kernel source", "requirement_ids": [identity] if category else []})
        if category:
            problem["requirements"].append({"id": identity, "unit_ids": [f"U{number}"], "category": category,
                "question_ids": question_sets[number], "interpretation": quote, "origin": "explicit"})
        offset += len(quote) + 1
    problem["question_dependencies"][0]["artefact"] = "Q1 synthetic kernel structure"
    for question in problem["questions"]:
        facts = {field: {"status": "not_specified", "value": None, "reason": "Not specified in this synthetic source", "requirement_ids": []} for field in FACT_FIELDS}
        for requirement in problem["requirements"]:
            if question["id"] in requirement["question_ids"]:
                facts[requirement["category"]] = {"status": "specified", "value": requirement["interpretation"],
                    "reason": "Exact synthetic source statement", "requirement_ids": [requirement["id"]]}
        facts["state_variables"] = {"status": "deferred", "value": None, "reason": "C defines the mathematical representation", "requirement_ids": []}
        if case == "constant":
            facts["commanded_inputs"] = {"status": "not_applicable", "value": None,
                "reason": "The explicit source says the constant kernel y=k requires no external input", "requirement_ids": []}
        if case == "passthrough":
            facts["parameters"] = {"status": "not_applicable", "value": None,
                "reason": "The explicit source defines y=u without any parameters", "requirement_ids": []}
        question.update(facts=facts, variables=[] if case == "constant" else [
            {"id": "input", "symbol": "u", "quantity": "dimensionless input", "roles": ["commanded_input"], "role_relation": None, "unit": "1", "status": "declared", "requirement_ids": ["R2"]}])
        question["classification"] = {"objectives": ["verification_validation"], "model_structures": [], "capabilities": ["problem_audit", "model_design"]}
    write_contract(path, problem)
    return freeze_contract(path)


def _model(root, case, known_parameters, root_output=True):
    path = make_model_contract(root, status="challenged")
    problem_path = _problem(root, case, root_output)
    problem, contract = read_contract(problem_path), read_contract(path)
    coefficients = {} if case == "passthrough" else {"a": 0.75, "b": 1.5} if case == "feedback" else {"k": 2.0}
    expression = "y = u" if case == "passthrough" else "dx/dt = b*u - a*x; y = x" if case == "feedback" else "y = k" if case == "constant" else "y = k*u"
    foundation = root / "design-foundation.txt"
    foundation.write_text(f"SYNTHETIC KERNEL ONLY: {expression}\nExplicit fixture coefficients: {coefficients}\n"
                          + ("The exact identity y=u requires no parameters or default gain.\n" if case == "passthrough" else "")
                          +
                          "These are declared infrastructure values, not identified/calibrated physical estimates.\n"
                          "Unknown-parameter tests retain null; no real task approval or numerical result is represented.\n",
                          encoding="utf-8", newline="\n")
    brief = root / "model-approval-brief.md"
    brief.write_text(f"# Synthetic {case} kernel approval brief\n\n{expression}\n"
                     + ("This exact identity contains no parameters; it maps to a direct input/output connection.\n" if case == "passthrough" else "")
                     + ("The mathematical output y remains internal; the source requires no root Outport.\n" if not root_output else "")
                     +
                     "Only source-bound mathematical and engineering structure is reviewed.\n"
                     "No simulation, solver, parameter fitting, physical validity or actual human approval is asserted.\n",
                     encoding="utf-8", newline="\n")
    source = {"id": "foundation", **file_ref(root, foundation), "purpose": "Explicit synthetic kernel and coefficients", "problem_source_id": None}

    def variable(identity, roles, unit="1", parameter=None):
        return {"id": identity, "symbol": identity, "quantity": f"synthetic kernel {identity}", "roles": roles,
                "role_relation": "The synthetic state is also the declared output" if len(roles) > 1 else None,
                "unit": unit, "parameter": parameter, "requirement_ids": []}

    variables = ([variable("u", ["commanded_input"])] if case != "constant" else []) + [variable("y", ["output"])]
    if case == "feedback":
        variables.append(variable("x", ["state"]))
    for name, value in coefficients.items():
        variables.append(variable(name, ["parameter"], "1/s" if case == "feedback" else "1", parameter={
            "value": value if known_parameters else None, "provenance": "assumed", "source_ids": ["foundation"],
            "plan": "Explicit synthetic coefficient for infrastructure qualification; retain unknown in missing-value cases"}))
    review = {"status": "reviewed", "conclusion": "Reviewed the explicitly declared synthetic kernel only",
              "reason": "Infrastructure test, not a physical or numerical validation", "next_action": "Execute only qualified structure operations", "source_ids": ["foundation"]}
    initial = {"status": "specified", "value": {"x": 0.25}, "reason": "Exact synthetic source initial condition", "requirement_ids": ["R3"]} if case == "feedback" else {"status": "not_applicable", "value": None, "reason": "No state in the explicitly algebraic kernel", "requirement_ids": []}
    model = contract["designs"][0]["models"][0]
    model.update(id=f"{case}_kernel", name=f"Synthetic {case} mathematical kernel", structure="state_space" if case in {"feedback", "constant"} else "transfer_function", source_ids=["foundation"])
    model["body"] = {"object": "Explicit synthetic mathematical kernel", "boundary": "Only declared input/output and coefficients",
        "variables": variables, "relations": [{"id": "kernel", "expression": expression,
            "variable_ids": [item["id"] for item in variables], "requirement_ids": ["R1", "R5", "R7"], "role": "governing"}],
        "inputs": [] if case == "constant" else ["u"], "outputs": ["y"], "initial_conditions": initial,
        "boundary_conditions": {"status": "not_applicable", "value": None, "reason": "No spatial boundary in the source", "requirement_ids": []},
        "mechanisms": [{"id": "kernel_mechanism", "description": expression, "relation_ids": ["kernel"]}],
        "assumptions": []}
    model["fidelity"] = {"level": "F1", "mechanisms": expression, "scales": "Synthetic [0,1] s", "order": "One state" if case == "feedback" else "Algebraic",
        "coupling": "Declared scalar signals", "data_support": "Explicit synthetic source", "selection_reason": "Minimal structure qualification kernel"}
    model["solver_plan"] = {"status": "not_applicable", "method": None, "risks": "No simulation is allowed in D", "reason": "Only engineering structure is tested"}
    model["validator_plan"] = [{"id": "structure_only", "status": "planned", "method": "Port/connection/parameter readback",
        "target": "Declared engineering structure", "source_ids": ["foundation"], "criterion": "Exact declared block structure",
        "claim_limit": "No physical, solver or numerical validity"}]
    model["structure_review"] = {field: dict(review) for field in model["structure_review"]}
    design = contract["designs"][0]
    design.update(id="kernel_design", main_model=model["id"], requirement_ids=[item["id"] for item in problem["requirements"]],
        selection_reason="Explicit source-bound synthetic kernel", alternative_review="No alternate kernel is needed for this single infrastructure case")
    design["challenge"] = {field: dict(review) for field in design["challenge"]}
    contract.update(project_id=problem["project_id"], problem=file_ref(root, problem_path), sources=[source], brief=file_ref(root, brief), approval=None)
    write_contract(path, contract)
    return approve_contract(path)


def make_mapping_contract(tmp_path, *, status="mapped", known_parameters=True, case="static", root_output=True):
    """Return a source-bound mapping path; all approvals are labelled synthetic."""
    if case not in {"static", "feedback", "constant", "passthrough"}:
        raise ValueError("unknown synthetic kernel case")
    root = Path(tmp_path)
    model_path = _model(root, case, known_parameters, root_output)
    model_contract = read_contract(model_path)
    design, model = model_contract["designs"][0], model_contract["designs"][0]["models"][0]
    model_name = f"synthetic_{case}"
    parameters = []
    for variable in model["body"]["variables"]:
        if "parameter" in variable["roles"]:
            parameters.append({"reference": {"design_id": design["id"], "model_id": model["id"], "variable_id": variable["id"]},
                "symbol": variable["symbol"], "code_name": variable["id"],
                "scope": {"kind": "model_workspace", "owner": model_name, "data_source": "ModelFile"},
                "value": variable["parameter"]["value"], "unit": variable["unit"], "provenance": variable["parameter"]["provenance"],
                "source_ids": variable["parameter"]["source_ids"],
                "uncertainty": {"status": "unknown", "value": None, "reason": "No uncertainty analysis is asserted"},
                "tunability": {"status": "fixed", "reason": "This explicit fixture builds one declared coefficient set; no tuning is authorized"}})
    parameters_path = write_contract(root / "parameters.json", {"schema_version": 1, "project_id": model_contract["project_id"], "status": "bound",
        "model": file_ref(root, model_path), "parameters": parameters})

    def parameter(name):
        return {"parameter_ref": {"design_id": design["id"], "model_id": model["id"], "variable_id": name}}

    def block(identity, kind, settings):
        return {"id": identity, "path": f"{model_name}/{identity}", "type": kind,
                "purpose": f"Explicit synthetic {kind} operation for the declared {case} kernel", "parameters": settings}

    def connection(source, destination, port=1):
        return {"source": {"block_id": source, "port": 1}, "destination": {"block_id": destination, "port": port}}

    blocks = [block("Input", "Inport", {"Port": {"setting": {"kind": "port", "value": 1}}})] if case != "constant" else []
    if root_output:
        blocks.append(block("Output", "Outport", {"Port": {"setting": {"kind": "port", "value": 1}}}))
    if case == "static":
        blocks.append(block("GainK", "Gain", {"Gain": parameter("k")}))
        connections = [connection("Input", "GainK")]
        result_block = "GainK"
    elif case == "constant":
        blocks.append(block("Coefficient", "Constant", {"Value": parameter("k")}))
        connections = []
        result_block = "Coefficient"
    elif case == "passthrough":
        connections = []
        result_block = "Input"
    else:
        blocks.extend([block("GainB", "Gain", {"Gain": parameter("b")}), block("GainA", "Gain", {"Gain": parameter("a")}),
            block("Balance", "Sum", {"Inputs": {"setting": {"kind": "enum", "value": "+-"}}}),
            block("State", "Integrator", {"InitialCondition": {"value_ref": {"design_id": design["id"], "model_id": model["id"], "field": "initial_conditions", "selector": ["x"]}}})])
        connections = [connection("Input", "GainB"), connection("GainB", "Balance"), connection("State", "GainA"),
                       connection("GainA", "Balance", 2), connection("Balance", "State")]
        result_block = "State"
    if root_output:
        connections.append(connection(result_block, "Output"))
    traces = []
    for kind, field in (("relation", "relations"), ("variable", "variables"), ("mechanism", "mechanisms")):
        for item in model["body"][field]:
            objects = {"u": "Input", "y": "Output" if root_output else result_block, "x": "State", "a": "GainA", "b": "GainB", "k": result_block}
            traces.append({"kind": kind, "subject_id": item["id"], "block_ids": [objects.get(item["id"], result_block)],
                           "disposition": "mapped", "reason": "Reviewed explicit synthetic relationship and its declared engineering objects"})
    if case != "constant":
        traces.append({"kind": "input", "subject_id": "u", "block_ids": ["Input"], "disposition": "mapped", "reason": "Declared input interface"})
    traces.append({"kind": "output", "subject_id": "y", "block_ids": ["Output" if root_output else result_block], "disposition": "mapped", "reason": "Declared root output" if root_output else "The approved source requires only an internal mathematical output, with no root Outport"})
    for field in ("initial_conditions", "boundary_conditions"):
        applicable = model["body"][field]["status"] == "specified"
        traces.append({"kind": field, "subject_id": None, "block_ids": ["State"] if applicable else [],
                       "disposition": "mapped" if applicable else "not_applicable", "reason": model["body"][field]["reason"]})
    mapping_source = root / "mapping-review.txt"
    mapping_source.write_text(f"SYNTHETIC STRUCTURE REVIEW: {case} kernel is mapped explicitly, no free-text expression is executed.\n"
                              "No simulation, estimates, physical truth or actual project approval is claimed.\n", encoding="utf-8", newline="\n")
    reviews = {field: {"status": "reviewed", "conclusion": "Reviewed the explicit synthetic mapping", "reason": "Structure qualification only", "source_ids": ["mapping_review"]} for field in REVIEW_FIELDS}
    contract = {"schema_version": 1, "project_id": model_contract["project_id"], "status": status,
        "model": file_ref(root, model_path), "parameters": file_ref(root, parameters_path),
        "sources": [{"id": "mapping_review", **file_ref(root, mapping_source), "purpose": "Actual explicit synthetic mapping review text"}],
        "targets": [{"id": "kernel", "design_id": design["id"], "model_id": model["id"], "domain": "simulink",
            "reason": "Scalar signal flow directly represents this declared kernel", "alternatives": [], "coupling": "No additional domain or architecture components needed",
            "model_name": model_name, "blocks": blocks, "connections": connections, "traces": traces}],
        "reviews": reviews, "implementation": None}
    return write_contract(root / "mapping.json", contract)
