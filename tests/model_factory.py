"""Synthetic design and human-decision records qualify infrastructure only."""
from __future__ import annotations

from pathlib import Path

from problem_factory import make_contract, read_contract, write_contract
from runtime_common import ROOT, sha256_file
from validate_model_contract import CHALLENGE_FIELDS, STRUCTURE_FIELDS, expected_locked_spec, semantic_digest


def file_ref(root: Path, path: Path) -> dict:
    return {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}


def approve_contract(path: Path) -> Path:
    """Create a clearly synthetic decision; production validators never do this."""
    root = path.parent
    contract = read_contract(path)
    contract["status"] = "approved"
    digest = semantic_digest(contract)
    actor = "synthetic-human-reviewer"
    quote = (f"project_id={contract['project_id']}\nproblem_sha256={contract['problem']['sha256']}\n"
             f"model_semantic_sha256={digest}\nactor={actor}\naction=approve\n"
             "SYNTHETIC TEST DECISION ONLY: this is not a person's approval of a real competition model.")
    decision_path = root / "human-model-decision.txt"
    decision_path.write_text(quote + "\n", encoding="utf-8", newline="\n")
    locked_path = write_contract(root / "locked-model-spec.json", expected_locked_spec(contract))
    approval = {"schema_version": 1, "project_id": contract["project_id"],
                "problem_sha256": contract["problem"]["sha256"], "model_semantic_sha256": digest,
                "decision": {**file_ref(root, decision_path), "start": 0, "end": len(quote), "quote": quote,
                             "actor": actor, "actor_kind": "human", "action": "approve"},
                "locked_model_spec": file_ref(root, locked_path)}
    approval_path = write_contract(root / "model-approval.json", approval)
    contract["approval"] = file_ref(root, approval_path)
    return write_contract(path, contract)


def make_model_contract(tmp_path: Path, *, status="draft", blocked_challenge=False) -> Path:
    root = Path(tmp_path)
    problem_path = make_contract(root, status="frozen")
    problem = read_contract(problem_path)
    foundation_path = root / "design-foundation.txt"
    foundation_path.write_bytes((ROOT / "tests/fixtures/model_design/design-foundation.txt").read_bytes())
    brief_path = root / "model-approval-brief.md"
    brief_path.write_text(
        "# Synthetic approval brief\n\nShared Q1/Q2 model: a well-mixed thermal energy balance.\n"
        "C_eff and H remain unknown; identification, simulation and V&V have not run.\n"
        "Constant ambient temperature is an explicit assumption; the planned holdout cannot establish validity before execution.\n"
        "Review zero useful alternatives at this initial scope; the later comparison decision remains open.\n"
        "No real human approval or business execution is represented by this fixture.\n", encoding="utf-8", newline="\n")

    def review(field, *, structure=False):
        explanations = {
            "units": "C_eff*dT/dt and P/H*(T-Ta) are powers; temperature differences use K even when observations use degC.",
            "conservation": "The declared heat storage equals heating input minus ambient heat loss; this is design reasoning, not an executed residual test.",
            "causality": "The state derivative depends on current temperature, commanded power and ambient disturbance.",
            "initial_boundary": "Initial temperature is source-given; constant ambient is a disclosed assumption rather than a source fact.",
            "key_mechanisms": "Input, heat storage and ambient heat loss are represented; unresolved transport physics is limited by the lumped assumption.",
            "identifiability": "Unknown coefficients need a later excitation/identifiability study; no numerical estimates are asserted.",
            "data_support": "Calibration and held-out scopes follow the Problem Contract; statistical independence remains to be checked.",
            "dimensionality": "One temperature state is sufficient for this candidate abstraction; no unnecessary state is added.",
            "implementation_bias": "The energy relation is selected from mechanism reasoning before any Block choice.",
            "simpler_equivalent": "A simpler static relation would lose the requested transient response.",
            "hybrid_events": "No event or switching law is required by the source within the proposed domain.",
            "simscape_need": "An acausal implementation is optional; the declared single thermal balance does not require it.",
            "executable_vv": "Convergence, conservation and held-out errors can be checked in later phases; none has been executed.",
        }
        state = "reviewed" if status in {"challenged", "approved"} else "pending"
        if blocked_challenge and field == "identifiability":
            state = "blocked"
        return {"status": state, "conclusion": explanations[field], "reason": "Synthetic design review with explicitly limited claims",
                "next_action": "Perform the declared later verification; do not claim it has passed",
                "source_ids": ["foundation"] if structure else ["foundation", "measurements"]}

    def variable(identity, symbol, quantity, roles, unit, *, requirement_ids=None, parameter=None):
        return {"id": identity, "symbol": symbol, "quantity": quantity, "roles": roles,
                "role_relation": "The temperature state is directly observed and is the requested output" if len(roles) > 1 else None,
                "unit": unit, "parameter": parameter, "requirement_ids": requirement_ids or []}

    variables = [
        variable("temperature", "T", "uniform water temperature", ["state", "output", "observable"], "degC", requirement_ids=["R3"]),
        variable("power", "P", "heating power", ["commanded_input"], "W", requirement_ids=["R2"]),
        variable("ambient", "T_a", "ambient temperature", ["disturbance"], "degC"),
        variable("time", "t", "elapsed time", ["independent_variable"], "s", requirement_ids=["R4"]),
        variable("capacity", "C_eff", "effective thermal capacity", ["parameter"], "J/K", parameter={"value": None, "provenance": "identified", "source_ids": ["measurements"], "plan": "Identify jointly under the prescribed calibration scope; assess identifiability before accepting estimates"}),
        variable("loss", "H", "ambient heat-loss coefficient", ["parameter"], "W/K", requirement_ids=["R7"], parameter={"value": None, "provenance": "identified", "source_ids": ["measurements"], "plan": "Estimate heat loss using the prescribed calibration data, preserving held-out records"}),
    ]
    model = {
        "id": "thermal_balance", "name": "Lumped thermal energy balance", "structure": "ode", "source_ids": ["foundation", "measurements"],
        "body": {"object": "The synthetic water tank and heater", "boundary": "Water volume with commanded heater input and ambient heat exchange",
                 "variables": variables, "relations": [{"id": "energy", "expression": "C_eff*dT/dt = P - H*(T-T_a)",
                    "variable_ids": [item["id"] for item in variables], "requirement_ids": ["R1", "R5", "R7"], "role": "governing"}],
                 "inputs": ["power", "ambient"], "outputs": ["temperature"],
                 "initial_conditions": {"status": "specified", "value": {"temperature": 20, "unit": "degC"}, "reason": "Explicit source condition", "requirement_ids": ["R3"]},
                 "boundary_conditions": {"status": "specified", "value": {"ambient_temperature": 20, "unit": "degC"}, "reason": "Disclosed synthetic constant-ambient assumption, not a given condition", "requirement_ids": []},
                 "mechanisms": [{"id": "storage_and_loss", "description": "Thermal storage, heating and ambient exchange", "relation_ids": ["energy"]}],
                 "assumptions": [
                     {"id": "well_mixed", "meaning": "Water temperature is spatially uniform", "mathematical_role": "A single temperature state represents stored energy", "justification": "A candidate abstraction requiring adequate mixing", "failure_bias": "May miss gradients and extrema", "test_plan": "Review spatial evidence or a resolved comparator when the task requires it", "relation_ids": ["energy"]},
                     {"id": "constant_ambient", "meaning": "Ambient temperature is constant over the selected scenario", "mathematical_role": "T_a is an imposed disturbance", "justification": "Explicit synthetic design assumption", "failure_bias": "Changing ambient conditions can change heat loss", "test_plan": "Check actual ambient records and expand scenarios if needed", "relation_ids": ["energy"]},
                 ]},
        "fidelity": {"level": "F1", "mechanisms": "Storage and ambient exchange", "scales": "Lumped water volume, 0 to 60 seconds", "order": "One temperature state", "coupling": "Heater input and ambient thermal coupling", "data_support": "Sparse observed temperatures, with declared fitting and holdout scopes", "selection_reason": "Minimal dynamic mechanism supporting the two questions; higher labels are not quality evidence"},
        "solver_plan": {"status": "proposed", "method": "ODE integration family; exact method deferred", "risks": "Time scale, step refinement and parameter identification conditioning need later checks", "reason": "The mathematical relation is an ODE; no solver has run"},
        "validator_plan": [{"id": "energy_and_holdout", "status": "planned", "method": "Energy residual and held-out trajectory error", "target": "Declared balance and prescribed observable", "source_ids": ["measurements"], "criterion": "Report numerical residual and held-out errors against a separately defined later protocol", "claim_limit": "A plan only; no numerical verification, statistical independence or real-system validity is asserted"}],
        "structure_review": {field: review(field, structure=True) for field in STRUCTURE_FIELDS},
    }
    contract = {
        "schema_version": 1, "project_id": problem["project_id"], "status": status,
        "problem": file_ref(root, problem_path),
        "sources": [{"id": "foundation", **file_ref(root, foundation_path), "purpose": "Explicit synthetic model abstraction and assumptions", "problem_source_id": None},
                    {"id": "measurements", **file_ref(root, root / "observations.csv"), "purpose": "Declared support for future identification and held-out validation", "problem_source_id": "measurements"}],
        "designs": [{"id": "shared_tank_design", "question_ids": ["Q1", "Q2"], "requirement_ids": [item["id"] for item in problem["requirements"]],
                     "main_model": model["id"], "selection_reason": "One shared energy balance supports response and parameter-estimation questions", "alternative_review": "No material alternate structure is required to establish this initial proposal; later structural-comparison disposition remains unexecuted", "models": [model], "challenge": {field: review(field) for field in CHALLENGE_FIELDS}}],
        "brief": file_ref(root, brief_path), "approval": None,
    }
    path = write_contract(root / "model.json", contract)
    return approve_contract(path) if status == "approved" else path
