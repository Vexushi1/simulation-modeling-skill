# Model Approval Brief — unfilled draft

Read the current frozen Problem Contract, design sources, Model Contract schema, and [model-design module](../../modules/02_model_design.md) before replacing these placeholders. This template supplies no task fact, parameter estimate, review conclusion, or human approval. Record future work as proposed and known evidence with its current source.

## Review context

- Project ID: [actual project]
- Problem path and current SHA-256: [current frozen Problem]
- Design IDs and covered question/requirement IDs: [actual coverage]
- Current design sources and intended uses: [source IDs, paths, SHA-256, purposes]
- Review status and unresolved material decisions: [current findings]

Write and bind the completed Brief before calculating the full-design semantic digest. Do not embed that digest in this Brief, because the digest includes this file's SHA. Independent structural model identities can be cited below. The caller can attach the full-design digest as external decision context after this file is final.

## Recommended primary route

[Describe the target object, abstraction and boundary, mathematical structure, shared question coverage, independent structural identity, and why this is the minimally sufficient route. Separate the model from solver and implementation choices.]

## Alternatives and fidelity

[List 0..N useful alternatives with the mechanism or assumption each could test, source/data support, additional states/parameters, cost, expected evidence benefit, and selection decision. Explain when no additional route adds useful information.]

[Record contextual F0–F4 selection, represented mechanisms, resolved scales, order, coupling, data support, identifiability and marginal benefit. Benchmark/reference belongs to the validation plan, not the fidelity label.]

## Mathematical relations and variables

[Give the actual governing/output/constraint/event/constitutive relations, explicit variable references, units, input/output roles, and applicable initial/boundary conditions. Preserve absent conditions as unresolved and explain their consequences.]

| Variable or parameter | Symbol and unit | Role | Known value or unknown | Source/evidence and provenance | Proposed estimation or check |
|---|---|---|---|---|---|
| [actual entry] | [actual unit] | [actual role] | [supported value or unknown] | [actual source or assumption] | [future plan, if needed] |

## Core assumptions and structural review

[For each core assumption give its real meaning, mathematical role, justification, failure bias, and proposed test. The task determines the count.]

| Structural review | Status | Conclusion and task reason | Proposed resolution or test |
|---|---|---|---|
| Dimensions and units | [pending/reviewed/blocked/not_applicable] | [actual finding] | [actual next action] |
| Conservation | [status] | [actual finding] | [actual next action] |
| Causality | [status] | [actual finding] | [actual next action] |
| Initial/boundary closure | [status] | [actual finding] | [actual next action] |

## Model challenge

| Challenge | Status | Conclusion, evidence basis, and task reason | Proposed resolution or test |
|---|---|---|---|
| Key mechanisms | [pending/reviewed/blocked/not_applicable] | [actual finding] | [actual next action] |
| Identifiability | [status] | [actual finding] | [actual next action] |
| Data support | [status] | [actual finding] | [actual next action] |
| Unnecessary dimensionality | [status] | [actual finding] | [actual next action] |
| Implementation bias | [status] | [actual finding] | [actual next action] |
| Simpler equivalent model | [status] | [actual finding] | [actual next action] |
| Events or hybrid structure | [status] | [actual finding] | [actual next action] |
| Need for Simscape | [status] | [actual finding] | [actual next action] |
| Future executable V&V | [status] | [actual finding] | [actual next action] |

No pending review can be presented as a completed challenge. A completed challenge may identify a blocker; unresolved material blockers prevent approval readiness. Reasons for not_applicable must follow the actual task. Design review is not numerical or physical validation evidence.

## Expected implementation and solver risks

[Describe expected MATLAB/Simulink/Simscape/Stateflow mapping and numerical risks only as future proposals. Explain why implementation convenience did not determine physics. Do not build model files or run a solver in Phase C.]

## Proposed verification and validation

[For each planned check state the target, method, intended independent source/reference, criterion, claim boundary, and prerequisites. Keep calibration data separate from independent validation. Identify missing references or thresholds and any permitted qualitative conclusions.]

## Cost, recommendation, and approval request

[State expected computation and data cost, recommendation, unresolved material issues, limits, and the concrete design decision requested. Obtain any necessary missing task input before presenting the design as ready.]

Actual approval must come from a person's explicit decision on this current Brief and design. An agent recommendation, repository development request, template checkbox, or synthetic fixture is not that decision. After a real approval, an authorized explicit caller binds the external decision and matching complete locked specification to the current project, Problem, and full-design digest. Do not require the person to type hashes. The validator remains read-only and model approval grants no numerical execution.

The external approval fields are `project_id`, `problem_sha256`, `model_semantic_sha256`, `decision`, and `locked_model_spec`. The caller's external decision record faithfully preserves the human words and source context alongside complete, unique context lines for those three identity fields, `actor`, and `action=approve`. This record is created only after the actual decision; the Brief itself contains no approval and no self-dependent full-design digest.
