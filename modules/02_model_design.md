# Model design, challenge, and human approval

## Scope and authorities

Use this module to design the mathematical or physical representation of an audited simulation task. Read [the trusted root](../core/bootstrap.yaml), the current frozen [Problem Contract](../core/problem_contract.schema.yaml), [the Model Contract schema](../core/model_contract.schema.yaml), [the Model Approval contract](../core/model_approval_contract.yaml), and [the router](../core/workflow_router.yaml). [The full plan §7](../docs/V1_FULL_IMPLEMENTATION_PLAN.md) owns the development scope and gates.

Phase C implements text design, challenge review, approval materials, and read-only checks. It requires no MATLAB profile. It does not build a business model, run a solver, estimate parameters, simulate, or execute verification and validation. Phases D–K remain deferred. Neither a frozen problem nor an approved model grants numerical execution.

A direct validator may inspect a legal incomplete draft. The `model_design` route requires the actual current frozen Problem Contract. A repository development request is authority to implement this infrastructure; it does not supply a task's missing facts or Human Model Approval. Validators and the resolver never write contracts, decisions, locked files, or project state.

## Review the problem and design basis

Read the complete current problem, its literal requirement map, data roles, dependency graph, ambiguities, and freeze decision. Preserve task conditions and required outputs. If the proposed model reveals a missing material task fact or conflicts with supplied conditions, return to problem review instead of silently rewriting its meaning.

Bind the Model Contract to the actual project identity and Problem file path/SHA-256. Register the current files used for model selection and their purposes. Preserve unknown numerical values: a parameter that will be identified or calibrated has a proposed provenance and method, not a fabricated estimate. Supplied, derived, identified, calibrated, optimized, and assumed are provenance roles, not a universal credibility ranking.

Cover every question and relevant requirement. One design can serve several questions; a question can have justified candidates. Select a minimally sufficient primary model supported by the task, mechanisms, data, and budget, then review 0..N useful alternatives. Record why an advanced route or another alternative would or would not test a material assumption. A fixed two-model quota and a fixed assumption count are inappropriate. Executing a structural comparator is a later decision and capability.

## Describe mathematical structure before implementation

Keep the roles separate:

- Model: mathematical or physical representation of the target system.
- Solver: proposed numerical integration, optimization, or search method.
- Validator: proposed independent reference or check of the model or solution.

A solver name cannot identify a model. Register objects and abstraction, system boundary, structural family, variables with units and roles, mathematical relations with explicit variable references, inputs and outputs, applicable initial and boundary conditions, mechanisms and coupling, and core assumptions. Choose expressions suitable for the system; a discrete, data-driven, algebraic, or noncausal network need not be forced into an explicit ODE.

For each core assumption explain its real meaning, mathematical role, justification, likely failure bias, and proposed test. A convenient Block or implementation shortcut is not a physical justification. Proposed mapping can describe expectations and risks; actual Simulink, Simscape, or Stateflow implementation belongs to Phase D.

For known or candidate parameters distinguish the source role, known value if any, unit, evidence, and future estimation or calibration plan. Use an explicit unknown value when evidence is absent. Preserve the declared separation between fitting and validation data. Proposed validation or identifiability work is not evidence that it has already succeeded.

## Select fidelity for this target

Use F0–F4 as contextual design labels:

- F0: conceptual representation.
- F1: lumped or low-order representation.
- F2: mechanisms sufficient for the engineering target.
- F3: detailed or coupled mechanisms.
- F4: mechanisms or scales resolved for the intended target.

Explain mechanisms, resolved scales, order, coupling, data support, parameter identifiability, computational cost, numerical risks, and the marginal benefit to the required conclusions. These labels are not a universal quality ranking. More domains or more computation do not by themselves mean higher fidelity. A benchmark/reference is a validation evidence role, not a fidelity level. An F0 candidate can be useful, but a conceptual label cannot replace the complete relations and variables required for a primary proposal.

## Challenge the proposal

Record four structural reviews: dimensional consistency, conservation, causality, and initial/boundary-condition closure. Then explicitly address all nine design challenges:

- omitted material mechanisms;
- parameter identifiability;
- adequacy of data support;
- unnecessary dimensionality;
- implementation convenience mistaken for physical justification;
- a simpler equivalent model;
- need for events or hybrid structure;
- need for Simscape;
- an executable future verification and validation plan.

Use `reviewed`, `pending`, `blocked`, or `not_applicable`, with a conclusion, reason, and proposed resolution or test. `not_applicable` requires a task-specific reason and cannot conceal a required mechanism or condition. Distinguish design reasoning from later numerical evidence; a review record is not an automatic proof of dimensional correctness, physical validity, identifiability, or real-system validation.

`proposal_complete` requires a structurally complete proposal. `challenge_complete` additionally requires all structural reviews and challenges to be performed, without `pending`; it can truthfully include unresolved `blocked` findings. `ready_for_approval` requires those material blockers to be resolved. Do not change the declared status to hide a missing gate.

## Identity and approval materials

The validator computes structural model identities from the objects/boundary, structural family, variable definitions/roles/units, mathematical relations, mechanisms, and core assumptions. Solver settings, proposed validators, implementation details, parameter provenance and current numerical values, and approval status are outside this structural identity. A solver or parameter-value change therefore does not create a second mathematical model.

Record structural initial or boundary relations, such as an imposed temperature versus a no-flux boundary, in `body.relations` with role `initial` or `boundary`, and explain the system boundary in `body.boundary`. The separate condition `value` fields hold scenario assignments, not structural operators. Numerical changes to those assignments preserve structural identity; changing an operator changes it. Registration lists and reference sets are normalized by stable identifiers, so rearranging declarations does not create another model.

This digest identifies the registered structural representation; it is not a symbolic equivalence proof. Renaming variables or rewriting equivalent equations can change the digest. Different hashes alone cannot establish a meaningful structural comparator: the later comparison review must identify the actual mechanism, abstraction, or mathematical-structure difference.

The separate full-design semantic digest binds the current Problem, design sources, complete design content, and current Approval Brief identity. Only status and approval references are excluded. A change outside structural identity can still alter the design awaiting approval and invalidate an older approval.

Prepare [the Approval Brief](../templates/contracts/model_approval_brief.md) from the actual reviewed contract and sources. Include the selected and alternative routes, equations or relations, states and parameters, assumptions, expected implementation mapping, solver risks, validation plan, cost, recommendation, and unresolved issues. The Brief can cite independent structural model IDs. It must not embed the full-design digest that includes the Brief itself: write the Brief first, bind its file SHA in the contract, then compute the full-design digest.

Human Model Approval is an actual person's explicit decision on the current Brief and design. Existing approval can be reused only while its context and bound identities still match. Development continuation, an agent recommendation, `status: approved`, or a self-written reviewer field cannot substitute for that decision. Faithfully record the person's words and decision context; do not require the person to calculate or type hashes. Ask for this decision only after producing concrete reviewable materials and resolving required input decisions.

After a real approval, an authorized explicit caller records the external ModelApproval binding to the project, current Problem SHA, full-design semantic digest, exact current human decision quote, and locked model specification. The quote uses inclusive `start` and exclusive `end` Unicode codepoint offsets and must identify the current decision context with an explicit approving action. A rejection, withdrawal, agent decision, or old generic approval cannot pass by containing a matching digest. Byte and actor/action checks verify recorded consistency; they do not authenticate an invented record as a real human action.

The external approval uses `project_id`, `problem_sha256`, `model_semantic_sha256`, `decision`, and `locked_model_spec`. `decision` records `path`, `sha256`, `start`, `end`, `quote`, `actor`, `actor_kind: human`, and `action: approve`. The caller's decision record includes exactly one complete line for each of `project_id=...`, `problem_sha256=...`, `model_semantic_sha256=...`, `actor=...`, and `action=approve`, then faithfully supplies the person's words and their source context. Those mechanical context lines are recorded by the caller after the real decision; they do not make a refusal or an invented approval valid, and the user need not format or calculate them.

The locked specification is produced by the explicit caller after actual approval and contains the matching full design and digest. `locked: true` without that content is insufficient. A validator never produces approval or lock files.

## Read-only validation and project state

Construct [a draft Model Contract](../templates/contracts/model_contract.yaml) only after reading the current schema and this module. Use the actual project files:

```text
python scripts/validate_model_contract.py '<contract-path>' --project-root '<project-root>'
python scripts/validate_model_contract.py '<contract-path>' --project-root '<project-root>' --require-proposed
python scripts/validate_model_contract.py '<contract-path>' --project-root '<project-root>' --require-challenged
python scripts/validate_model_contract.py '<contract-path>' --project-root '<project-root>' --require-approved
```

These commands check their requested gate without changing status or writing evidence. Read `schema_valid`, `valid`, `proposal_complete`, `challenge_complete`, `ready_for_approval`, `approved`, identities, errors, missing gates, and changed sources together. Legal draft shape, completed challenge, readiness, and actual approval are distinct results.

An explicit caller can bind current model and approval files in project state after validation. `MODEL_PROPOSED`, `MODEL_CHALLENGED`, and `MODEL_APPROVED` require the current frozen Problem and the corresponding declared contract status and gate; a successful check cannot promote a draft automatically. Accepted model/approval artefacts must match the current file and their required problem/model/approval anchors. They must not depend on environment evidence.

Model-scoped state checks assess the current B/C evidence and leave environment readiness unassessed. Problem-scoped checks leave the model unassessed and cannot establish overall `MODEL_APPROVED` validity. Default `all` retains environment checks. Report the selected scope explicitly. The `model_design` route selects no runtime operation and grants no numerical execution.

## Change and failure handling

Changed or missing Problem sources/freeze records, model sources, contract, Brief, human decision, or locked specification invalidate their actual bindings and accepted dependents. Phase C binds the entire Problem file and checks B's current sources conservatively: even an independently changed validation attachment can invalidate the model binding. This implementation does not claim a fine-grained source impact graph.

Environment expiry does not expire unchanged text design. Operations that eventually require MATLAB must independently satisfy their current runtime gate. On a source, reference, structure, challenge, decision, or lock failure, report the concrete issue and return to its owner; preserve prior history and obtain actual missing decisions. Do not repair evidence by inventing a fact, parameter value, approval, or successful run.

Development fixtures qualify the infrastructure's checks. They do not approve another task, prove mathematical/physical truth, establish statistical independence, or qualify a simulation. Phases D–K and upstream execution skills remain deferred until their own implementations and gates are qualified.
