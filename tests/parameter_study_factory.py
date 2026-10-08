"""Synthetic F inputs only; no real human approval or runtime qualification.

These helpers create current source-bound B/C records for unit tests. They must
not be consumed by independent forward-use tests or actual MATLAB qualification.
"""
from __future__ import annotations

import math
from pathlib import Path

from model_factory import approve_contract, file_ref, make_model_contract
from problem_factory import FACT_FIELDS, freeze_contract, read_contract, write_contract


METHODS = ("identification.arx_111", "calibration.simulink_gain", "optimization.quadratic_sqp")


def _observations(method: str) -> list[list[float]]:
    rows, previous = [], 0.2
    previous_input = 0.0
    for index in range(40):
        value = math.sin(index * 1.7) + 0.5 * math.cos(index * 0.37)
        output = 0.65 * previous + 1.25 * previous_input if method == METHODS[0] else 2.0 * value
        rows.append([index * 0.1, value, output])
        previous, previous_input = output, value
    return rows


def make_study_baseline(root: Path, method: str = METHODS[1]) -> Path:
    """Return approved-null synthetic C, with no D or E execution evidence."""
    if method not in METHODS:
        raise ValueError("unsupported synthetic study method")
    root = Path(root).resolve()
    model_path = make_model_contract(root, status="challenged")
    problem_path = root / "problem.json"
    problem, model_contract = read_contract(problem_path), read_contract(model_path)
    optimization = method == METHODS[2]
    arx = method == METHODS[0]
    names = ["a", "b"] if arx else ["x", "z"] if optimization else ["k"]
    expression = "y[k]=a*y[k-1]+b*u[k-1]" if arx else "J=1.0*((x-(2.0))/(1.0))^2+1.0*((z-(2.0))/(1.0))^2" if optimization else "y=k*u"
    csv_path = root / "observations.csv"
    csv_path.write_text("time,u,y\n" + "".join(",".join(format(value, ".17g") for value in row) + "\n"
                       for row in _observations(method)), encoding="utf-8", newline="\n")
    lines = [
        "SYNTHETIC INFRASTRUCTURE TEST ONLY: no actual human approval, physical observation or numerical verification.",
        f"System: explicit finite scalar mathematical kernel {expression}.",
        "No commanded input is required by this pure design objective." if optimization else "Input: scalar dimensionless u, sampled every 0.1 seconds.",
        "No initial state is required by this design objective." if optimization else "Initial measured output is supplied by the CSV; no state is invented.",
        "Time domain: 0 to 3.9 seconds in the supplied finite sample records.",
        f"Q1: review the declared {expression} mathematical representation.",
        "Q1 deliverable: source-bound mathematical design with unresolved parameters.",
        f"Q2: {'optimize design variables' if optimization else 'estimate unknown parameters'} {', '.join(names)} using the separately reviewed F study.",
        "No observations or holdout are required for the pure design objective." if optimization else "Q2: use CSV rows [0,20) for fitting and [20,40) for held-out checking; this split does not prove statistical independence.",
        "Q2 deliverable: candidate recommendation and limitations; no acceptance, physical validity or global-optimum claim.",
    ]
    categories = [None, "original_system", None if optimization else "commanded_inputs", None,
                  "time_domain", "direct_goal", "deliverables", "direct_goal", None if optimization else "data", "deliverables"]
    question_ids = [[], ["Q1", "Q2"], ["Q1", "Q2"], [], ["Q1", "Q2"], ["Q1"], ["Q1"], ["Q2"], ["Q2"], ["Q2"]]
    statement_path = root / "statement.txt"
    statement_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    problem.update(project_id=f"synthetic-f-{method.split('.')[0]}", status="draft", freeze=None, audit_units=[], requirements=[])
    problem["sources"][0].update(file_ref(root, statement_path))
    problem["sources"][0]["text"].update(file_ref(root, statement_path))
    problem["sources"][1].update(file_ref(root, csv_path))
    if optimization:
        problem["sources"] = problem["sources"][:1]
    offset = 0
    for index, line in enumerate(lines):
        category, identity = categories[index], f"R{index}"
        problem["audit_units"].append({"id": f"U{index}", "source_id": "statement", "start": offset,
            "end": offset + len(line), "quote": line, "disposition": "requirement" if category else "context",
            "reason": "Explicit synthetic mathematical task", "requirement_ids": [identity] if category else []})
        if category:
            problem["requirements"].append({"id": identity, "unit_ids": [f"U{index}"], "category": category,
                "question_ids": question_ids[index], "interpretation": line, "origin": "explicit"})
        offset += len(line) + 1
    problem["data_uses"] = [] if optimization else [
        {"id": "fit", "source_id": "measurements", "question_id": "Q2", "role": "calibration",
         "scope": {"kind": "rows", "start": 0, "end": 20}, "independence_declared": False},
        {"id": "check", "source_id": "measurements", "question_id": "Q2", "role": "validation",
         "scope": {"kind": "rows", "start": 20, "end": 40}, "independence_declared": True}]
    problem["question_dependencies"][0]["artefact"] = "Q1 synthetic mathematical representation"
    capability = "parameter_identification" if arx else "optimization" if optimization else "calibration"
    for question in problem["questions"]:
        facts = {field: {"status": "not_specified", "value": None, "reason": "Unspecified in explicit synthetic source", "requirement_ids": []}
                 for field in FACT_FIELDS}
        for requirement in problem["requirements"]:
            if question["id"] in requirement["question_ids"]:
                facts[requirement["category"]] = {"status": "specified", "value": requirement["interpretation"],
                    "reason": "Exact synthetic source requirement", "requirement_ids": [requirement["id"]]}
        facts["parameters"] = {"status": "specified", "value": names, "reason": "Explicit unresolved study variables", "requirement_ids": ["R7"] if question["id"] == "Q2" else ["R1"]}
        facts["state_variables"] = {"status": "deferred", "value": None, "reason": "C owns the mathematical representation", "requirement_ids": []}
        if optimization:
            facts["commanded_inputs"] = {"status": "not_applicable", "value": None, "reason": "Explicit pure design objective", "requirement_ids": []}
        question.update(facts=facts, variables=[], classification={"objectives": [capability], "model_structures": [],
                        "capabilities": ["problem_audit", "model_design", capability]})
    write_contract(problem_path, problem)
    freeze_contract(problem_path)
    foundation = root / "design-foundation.txt"
    foundation.write_text(f"SYNTHETIC INFRASTRUCTURE MATHEMATICS ONLY: {expression}\n"
        "Unknown parameters remain null. Candidate study initialization is not an adopted estimate.\n"
        + ("Constraint: 1.0*(x)+1.0*(z)<=3.0.\n" if optimization else "Declared observed variables u,y are dimensionless; time is seconds.\n"),
        encoding="utf-8", newline="\n")
    brief = root / "model-approval-brief.md"
    brief.write_text(f"# SYNTHETIC INFRASTRUCTURE BRIEF\n\n{expression}\n\n"
        "Unknown parameter values and proposed identification/calibration/optimization only. No person's real approval, numerical run or physical truth is represented.\n",
        encoding="utf-8", newline="\n")
    provenance = "identified" if arx else "optimized" if optimization else "calibrated"

    def variable(name, roles, parameter=None):
        return {"id": name, "symbol": name, "quantity": f"synthetic {name}", "roles": roles,
                "role_relation": None, "unit": "1", "parameter": parameter, "requirement_ids": []}

    variables = [] if optimization else [variable("u", ["commanded_input"]), variable("y", ["output", "observable"])]
    if not optimization:
        variables[1]["role_relation"] = "The synthetic output is directly observed in the supplied CSV"
    variables += [variable(name, ["parameter", "decision"] if optimization else ["parameter"],
        {"value": None, "provenance": provenance, "source_ids": ["foundation"] if optimization else ["measurements"],
         "plan": "Use the separately reviewed bounded F experiment; any final adoption requires new current C approval"}) for name in names]
    if optimization:
        for item in variables:
            item["role_relation"] = "The unresolved parameter represents a design decision, not an identified physical constant"
        variables.append(variable("J", ["output"]))
    relation = {"id": "objective" if optimization else "kernel", "expression": expression,
                "variable_ids": [item["id"] for item in variables], "requirement_ids": ["R1", "R5", "R7"], "role": "governing"}
    relations = [relation]
    if optimization:
        relations.append({"id": "constraint", "expression": "1.0*(x)+1.0*(z)<=3.0", "variable_ids": names,
                          "requirement_ids": ["R7"], "role": "constraint"})
    selected = model_contract["designs"][0]["models"][0]
    selected.update(id="study_kernel", name="Synthetic source-bound F kernel", structure="identified_linear_model" if arx else "state_space",
                    source_ids=["foundation"] if optimization else ["foundation", "measurements"])
    selected["body"].update(object="Synthetic mathematical kernel", boundary="Only declared scalar variables and observations",
        variables=variables, relations=relations, inputs=[] if optimization else ["u"], outputs=["J"] if optimization else ["y"],
        initial_conditions={"status": "not_applicable", "value": None, "reason": "Measured lags supply ARX prediction; gain and objective have no state", "requirement_ids": []},
        boundary_conditions={"status": "not_applicable", "value": None, "reason": "No spatial boundary", "requirement_ids": []},
        mechanisms=[{"id": "declared_kernel", "description": expression, "relation_ids": [relation["id"]]}], assumptions=[])
    selected["fidelity"].update(mechanisms=expression, scales="Finite declared scalar study", order="ARX [1 1 1]" if arx else "Algebraic",
                               data_support="Explicit synthetic source", selection_reason="Bounded infrastructure qualification task")
    selected["solver_plan"] = {"status": "proposed", "method": method, "risks": "Operation qualification and trial criteria are separate gates",
                               "reason": "Separately reviewed F trial, without adopted numerical values"}
    selected["validator_plan"][0].update(source_ids=["foundation"] if optimization else ["measurements"],
        method="Predeclared held-out one-step/output residual or explicit quadratic objective feasibility", target="Candidate only",
        criterion="Independent trial evidence required", claim_limit="No physical validation or numerical/global-optimum acceptance")
    review = {"status": "reviewed", "conclusion": "Reviewed the explicit synthetic mathematics and unresolved parameters",
              "reason": "Infrastructure test with no real human approval", "next_action": "Execute only separately qualified and reviewed F trial",
              "source_ids": ["foundation"]}
    selected["structure_review"] = {field: dict(review) for field in selected["structure_review"]}
    design = model_contract["designs"][0]
    design.update(id="study_design", main_model=selected["id"], requirement_ids=[item["id"] for item in problem["requirements"]],
                  selection_reason="Exact source-declared bounded study", alternative_review="No alternate model claimed")
    design["challenge"] = {field: dict(review) for field in design["challenge"]}
    sources = [{"id": "foundation", **file_ref(root, foundation), "purpose": "Explicit synthetic mathematical representation", "problem_source_id": None}]
    if not optimization:
        sources.append({"id": "measurements", **file_ref(root, csv_path), "purpose": "Finite explicit synthetic fit/holdout observations", "problem_source_id": "measurements"})
    settings = {"parameters": {name: {"initial": 1.0 if optimization else 1.5, "lower": -5.0 if optimization else 0.0,
                    "upper": 5.0 if optimization else 4.0, "unit": "1"} for name in names},
                "terms": {name: {"center": 2.0, "weight": 1.0, "scale": 1.0, "unit": "1"} for name in names},
                "constraint": {"coefficients": [1.0, 1.0], "rhs": 3.0}}
    settings_path = write_contract(root / "study-settings.json", settings)
    sources.append({"id": "study_settings", **file_ref(root, settings_path), "purpose": "Explicit synthetic bounds, initialization and objective source", "problem_source_id": None})
    model_contract.update(project_id=problem["project_id"], problem=file_ref(root, problem_path), sources=sources,
                          brief=file_ref(root, brief), status="challenged", approval=None)
    write_contract(model_path, model_contract)
    return approve_contract(model_path)


def review_parameter_study(path: Path) -> Path:
    """Create a labelled synthetic study review, never a real model approval."""
    from validate_parameter_study import semantic_digest

    path = Path(path)
    study = read_contract(path)
    digest = semantic_digest(study)
    reviewer = "synthetic-f-study-reviewer"
    quote = (f"project_id={study['project_id']}\nstudy_semantic_sha256={digest}\n"
             f"reviewed_by={reviewer}\naction=review\n"
             "SYNTHETIC INFRASTRUCTURE TEST REVIEW ONLY: no real human approval or accepted numerical evidence.")
    decision_path = path.parent / "study-review-decision.txt"
    decision_path.write_text(quote + "\n", encoding="utf-8", newline="\n")
    record = {"schema_version": 1, "project_id": study["project_id"], "study_semantic_sha256": digest,
              "decision": {**file_ref(path.parent, decision_path), "start": 0, "end": len(quote), "quote": quote,
                           "reviewed_by": reviewer, "action": "review"}}
    record_path = write_contract(path.parent / "study-review.json", record)
    study.update(status="reviewed", review_record=file_ref(path.parent, record_path))
    return write_contract(path, study)


def make_parameter_study(root: Path, method: str = METHODS[1], *, status: str = "reviewed") -> Path:
    """Return F study path; fixture evidence supplies no native runtime profile."""
    root = Path(root).resolve()
    model_path = make_study_baseline(root, method)
    model_contract = read_contract(model_path)
    selected = model_contract["designs"][0]["models"][0]
    arx, optimization = method == METHODS[0], method == METHODS[2]
    parameters = []
    for variable in selected["body"]["variables"]:
        if "parameter" not in variable["roles"]:
            continue
        name = variable["id"]
        settings = read_contract(root / "study-settings.json")["parameters"][name]
        parameters.append({"variable_id": name, "symbol": name, "unit": "1", "role": variable["parameter"]["provenance"],
            "initial": None if arx else settings["initial"], "lower": None if arx else settings["lower"],
            "upper": None if arx else settings["upper"], "numerical_basis": None if arx else {"source_id": "study_settings", "selector": ["parameters", name]},
            "source_ids": ["measurements"] if arx else ["study_settings"], "reason": "Synthetic candidate only; does not fill the approved C null"})
    sources = [{"id": source["id"], **file_ref(root, root / source["path"]), "purpose": source["purpose"],
                "model_source_id": source["id"], "problem_source_id": source["problem_source_id"]} for source in model_contract["sources"]]
    data = [] if optimization else [
        {"id": "training", "source_id": "measurements", "problem_data_use_id": "fit", "role": "train", "start": 0, "end": 20,
         "columns": {"time": "time", "input": "u", "output": "y"}, "units": {"time": "s", "input": "1", "output": "1"}, "weights": [1.0] * 20},
        {"id": "heldout", "source_id": "measurements", "problem_data_use_id": "check", "role": "holdout", "start": 20, "end": 40,
         "columns": {"time": "time", "input": "u", "output": "y"}, "units": {"time": "s", "input": "1", "output": "1"}, "weights": [1.0] * 20}]
    objective = None
    if optimization:
        settings = read_contract(root / "study-settings.json")
        objective = {"terms": [{"variable_id": item["variable_id"], **settings["terms"][item["variable_id"]],
                        "source_ref": {"source_id": "study_settings", "selector": ["terms", item["variable_id"]]},
                        "meaning": "Explicit synthetic design deviation from source center"} for item in parameters],
                     "constraints": [{**settings["constraint"], "relation_id": "constraint",
                        "source_ref": {"source_id": "study_settings", "selector": ["constraint"]}}],
                     "meaning": "Sum of declared scaled squared design deviations with a finite linear inequality"}
    study = {"schema_version": 1, "project_id": model_contract["project_id"], "status": "draft", "model": file_ref(root, model_path),
             "selection": {"design_id": "study_design", "model_id": "study_kernel", "relation_id": "objective" if optimization else "kernel",
                           "input_variable_id": None if optimization else "u", "output_variable_id": "J" if optimization else "y",
                           "constraint_relation_ids": ["constraint"] if optimization else []},
             "method": method, "sources": sources, "parameters": parameters, "data": data,
             "sample_time": None if optimization else 0.1, "objective": objective,
             "budget": {"max_iterations": 40, "max_evaluations": 150, "process_timeout": 240.0,
                        "simulation_timeout": 30.0 if method == METHODS[1] else None},
             "criteria": {"max_train_rmse": None if optimization else 1e-6, "max_holdout_rmse": None if optimization else 1e-6,
                          "max_condition_number": 1e6 if arx else None, "feasibility_tolerance": None if arx else 1e-7,
                          "reason": "Predeclared synthetic candidate tolerances only", "source_ids": ["foundation"]},
             "identifiability": None if optimization else {"reason": "Actual rank/conditioning or nonzero gain excitation must be checked",
                    "limitations": "Declared fit/holdout separation is not real statistical independence or physical validation", "source_ids": ["measurements"]},
             "warning_policy": "record", "required_A_operations": ["matlab.basic_execution", "simulink.library_load"], "review_record": None}
    path = write_contract(root / "parameter-study.json", study)
    return review_parameter_study(path) if status == "reviewed" else path
