# Problem audit and requirement freeze

## Scope and authorities

Use this module to audit the supplied simulation task, its attachments, and cross-question requirements before designing a model. Follow [the trusted root](../core/bootstrap.yaml), [the Problem Contract schema](../core/problem_contract.schema.yaml), and [the router](../core/workflow_router.yaml). The development scope and exit gates are in [the full plan §6](../docs/V1_FULL_IMPLEMENTATION_PLAN.md).

Phase B freezes the task meaning and conditions already supplied. [Phase C model design](02_model_design.md) then reviews fidelity and mathematical relations; implementation, simulation, and numerical evidence production remain deferred to Phases D–K. Candidate model clues are allowed in B; a frozen Problem Contract does not approve a model or authorize numerical execution.

Text review and read-only contract validation require no MATLAB capability profile. Environment assurance and problem meaning have separate dependencies. Validators and the resolver never create a freeze decision or write project state.

## Read the original material first

1. Locate the actual statement and attachments inside the declared project root. Preserve their identities; do not use a previous summary as the statement authority.
2. Bind every statement's original file and UTF-8 review text to their exact SHA-256 values. Direct UTF-8 text can serve both roles. For a PDF or OCR extraction, verify the review text against the original and bind a current verification record. An unverified extraction cannot support an audited or frozen contract. This phase does not supply a generic extraction engine.
3. Read every supplied question and condition. Keep explicit facts separate from interpretations, candidate assumptions, and unresolved ambiguities. Record missing or contradictory material rather than inventing values.
4. Register data attachments by source and intended use range. A spreadsheet requires traceable data roles and ranges, not a character-by-character map of every cell.

## Construct a literal requirement map

Partition each statement's review text into audit units with stable IDs, exact quotes, and Unicode codepoint offsets: `start` is inclusive and `end` is exclusive. Every non-whitespace character must be covered once; units must not overlap. Use the dispositions `requirement`, `context`, and `excluded`. Explain every exclusion.

Create stable requirement IDs and connect each requirement to its question and source units. Maintain both directions of the references. A requirement unit without a requirement, an unknown reference, or a quote that differs from its recorded text slice prevents an audit-complete result.

Coverage proves that the material was mapped mechanically. Independently review whether the requirements preserve the meaning of the original conditions and requested outputs; coverage alone does not prove that interpretation.

## Describe each question without preselecting its model

Record the original system, direct goal, and required deliverables explicitly. For the other required categories, use the schema's status and supporting references:

- `specified`: supported by the supplied material;
- `not_specified`: absent from the supplied material, with the consequence stated;
- `not_applicable`: a reasoned determination for this task;
- `deferred`: a choice that belongs to model design, with a reason.

Model-dependent abstraction, state representation, algebraic variables, derived parameters, or event and switching representation may be deferred. Do not defer a given system object, initial or boundary condition, or requested deliverable to bypass a material uncertainty. Candidate `model_structures` can remain empty pending Phase C.

Record question-level objectives and capabilities. Distinguish task facts from proposed interpretations. When an unknown condition affects the task or the validity of its deliverable, register it as a critical ambiguity with its source, consequence, and required resolution. A structural question left for Phase C is not automatically a missing fact in Phase B.

## Preserve variable, data, and dependency roles

Give each known or candidate variable a stable ID, physical quantity, unit, source, status, and role. Record an unknown unit explicitly rather than fabricating it. The same physical quantity can have multiple roles only when their relationship is explained; a label does not lock a state equation or model representation. The validator checks identities, references, role relationships, and fact status; physical meaning and dimensional correctness still require review.

For each data use, bind the source, question, role, and use range. Use `scope: {kind: all}` or a logical record interval `scope: {kind: rows, start: 0, end: 3}` with a zero-based inclusive start and exclusive end. The same attachment can supply disjoint fitting and validation ranges. Overlapping calibration and validation intervals cannot declare independence; equal-byte copies or different source IDs cannot bypass that check. This phase checks declared roles and interval overlap without parsing tables. Record layout, statistical independence, and validation adequacy require later evidence.

Describe each cross-question dependency with its producer, consumer, type, expected artefact, and requirement basis. Reject unknown nodes, self-edges, duplicates, and cycles. Future expected artefacts need not already have been calculated. Do not create numerical outputs to satisfy the dependency map.

## Validate, review, and freeze

Use [the draft template](../templates/contracts/problem_contract.yaml) only after reviewing this module and the schema. The template starts unfilled; its existence is not evidence of an audit.

Run the read-only checks against the actual project files:

```text
python scripts/validate_problem_contract.py '<contract-path>' --project-root '<project-root>'
python scripts/validate_problem_contract.py '<contract-path>' --project-root '<project-root>' --require-frozen
```

Use `--require-frozen` when the caller requires the frozen Gate. It checks that Gate; it does not create the decision or change the contract's status.

The validator reports distinct results:

- `schema_valid`: the document has a legal structure;
- `valid`: the supplied contract passes the checks applicable to its declared status;
- `audit_complete`: current source identity, coverage, references, roles, ranges, and question dependencies pass the audited checks;
- `freeze_ready`: required material is clear and critical ambiguities are resolved;
- `frozen`: the declared frozen contract also has a current, matching review decision.

A legal draft can contain unknowns and open ambiguities. Do not rename it `audited` or `frozen` to satisfy a requested stage. Review the complete original task and contract before deciding to freeze. Bind the decision to its current source file, exact decision quote, and semantic contract digest. Status and freeze metadata are outside that digest to avoid a circular identity.

The `freeze` record binds `semantic_sha256` and a decision with `path`, `sha256`, `start`, `end`, `quote`, and `reviewed_by`. The exact decision quote must identify the current semantic digest, so a generic old approval cannot freeze changed task meaning. Extraction verification likewise identifies both original and review-text identities. An ambiguity's resolution must be backed by its own current decision reference.

The freeze decision must reflect the actual task authorization and resolved material choices. Use existing authorization when it covers the review; obtain a necessary decision when a critical ambiguity needs the user's missing fact or preference. Do not require repeated approval for every question. Authorization to develop this repository supplies neither answers to a real task nor its Model Approval.

Contract and state writing belong to a separate authorized caller. After validating the actual contract, an explicit state update can record its path and SHA-256. `PROBLEM_AUDITED` requires an audit-complete contract declared `audited` or `frozen`; `PROBLEM_FROZEN` requires the matching frozen contract. An accepted problem artefact also requires the declared audited or frozen status. Validate the project's identity and current evidence before recording either state.

## Failure and change handling

For missing material, an unverified extraction, a changed source, an invalid map, conflicting data roles, an invalid dependency graph, an open critical ambiguity, or a mismatching review decision, report the concrete issue and return to the relevant audit step. Preserve earlier evidence and history. Do not replace an unresolved fact with a convenient model assumption.

Changing the contract, statement, attachment, extraction verification, or review decision invalidates the affected problem evidence and accepted artefacts that actually depend on it. Re-review and rebind them through an explicit update. A runtime profile's expiry does not invalidate unchanged problem meaning; operations requiring MATLAB must independently obtain current runtime evidence.

The Phase B development fixtures establish this infrastructure's behavior. They do not freeze another competition task or prove the physical validity of a future model. Current routing must leave Phases D–K deferred and must never activate an upstream execution skill to bypass that boundary. Phase C separately requires the current frozen Problem before its text-design route.
