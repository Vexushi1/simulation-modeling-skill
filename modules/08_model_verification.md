# Finite model claim assessment

Read [the H2 contract](../core/model_verification_contract.yaml), [H1](07_numerical_verification.md),
current C approvals, D implementations, independently frozen E protocols and the full plan
§12.9–12.15. H2 computes finite evidence in Python. It grants no MATLAB operation,
real-system validation, publication acceptance, automatic model approval or state transition.

## Review a claim and its required analyses

Start with [the draft template](../templates/contracts/model_verification.yaml). Bind the
current accepted primary H1 receipt as `primary_numerical_receipt`. Register other H1
receipts in `members`; `primary` is reserved. Every participant must have its own current
accepted H1 and complete source-bound E evidence. Historical analysis leaves current
runtime readiness unassessed, while each E receipt retains its execution-time A/E gates.
New simulations use the existing E producer and current required operation qualifications.

Each material claim states actual Problem requirement IDs, a finite domain, metric,
observable mapping, known units, prior criterion and limitations. Give exactly one decision
for `sensitivity`, `robustness`, `solver_comparison` and `model_comparison`.
The first three use `required | not_required`; model comparison uses
`required | not_applicable`. An omission needs its task-specific technical reason.
An explicitly requested or materially necessary analysis cannot be omitted because the
method, evidence or budget is unavailable. Such a required analysis remains blocked.

The `obligation_source_ref` selects the complete structured record
`{target_claim, requirement_ids, requirements: {kind: requirement}}` in current task review
material. `settings_source_ref` selects `{claims, budget, claim_limit}` in current reviewed
settings. These snapshots bind every decision, method, member order, mapping, unit,
threshold, action and scope. Reviewers must determine whether these decisions faithfully
cover the original task; mechanical selector checks cannot authenticate invented reviews
or establish the truth of the claim. Do not rewrite task sources to hide an obligation.

An omitted analysis has `method: null`, empty `member_ids`, and null metric/factor/bounds/
comparison/structural_review. A required analysis includes `primary` in its finite member
list and explicit output-port mapping for every other participant. Its final/minimum/maximum
metric must already be declared in each frozen E protocol. Minimum and maximum describe
actual saved samples; they are not continuous extrema.

## Available analyses

- `sensitivity / external_input_oat`: two to sixteen different constant levels of one
  approved external input. Keep the current C/D model, all parameters and conditions,
  solver, interval, other inputs and output configuration exact. `factor.levels` follows
  `member_ids`. Compute `(metric_member-metric_primary)/(input_member-input_primary)`;
  the primary finite difference is null. Declare slope bounds with literal unit
  `output_unit/input_unit`. Relative metric differences are null when the primary metric
  is zero. These are finite differences on the reviewed catalog, not parameter
  sensitivity, a derivative or a global ranking.
- `robustness / finite_scenarios`: keep the same current approved model, parameters,
  conditions and numerical configuration; only reviewed external input waveforms differ.
  Apply the prior same-unit lower/upper bounds to every actual metric, including primary.
  All points passing supports only this finite catalog and metric.
- `solver_comparison / solver_metrics`: keep all nonnumerical execution semantics exact.
  The first implementation compares actual `ode4` and `ode45` participants, each with
  accepted H1. Compare each metric with primary using
  `abs(difference) <= absolute_tolerance + relative_tolerance * max(abs(both values))`.
  Do not pair different adaptive samples by index or infer event, integral or runtime
  performance conclusions.
- `model_comparison / structural_metrics`: compare the same project and current frozen
  Problem, common time, actual input waveform/quantity/unit, reviewed numerical settings
  and explicitly mapped output quantity/unit. Each model has its own actual C approval,
  D/E chain and accepted H1. A current C approval can cover both reviewed models when
  the implementation supports that configuration; current D may instead require
  independent single-target C/D contracts. Never bypass D's actual scope.

Structural comparison also needs one source-bound `structural_review` for each comparator.
Select current C mathematical fields relative to the selected model, for example
`[body, variables]` for a genuinely different state dimension. `model_order` requires
actual different counts of state variables. The complete source snapshot includes both
selected values, both approved conditions, difference kind, rationale, physical target
and the explicit equivalence review. Selectors must address substantive mathematical records or allowed leaves. Identifier,
requirement, provenance, parameter-value and unrelated output-relation anchors are rejected.
Obvious variable/relation renaming is removed before comparing registered anchors;
governing/constitutive comparisons require corresponding relation roles. Different
structural hashes alone do not establish mechanism or mathematical differences. Parameter values, Block names, solver choices,
variable renaming and equivalent reformulations are insufficient. Registered anchors and
an actual material-difference review do not amount to an automatic symbolic equivalence
proof or physical validation.

Morris, Sobol, PRCC, continuous/correlated uncertainty, parameter or initial-condition
mutation, automatic boundary search, arbitrary residual/conservation execution, events,
continuous peaks, integral error and performance claims remain deferred. Required work
outside these methods blocks the affected acceptance.

## Produce and independently consume evidence

Review the current complete semantic digest using an independent exact source quote.
The review record uses `verification_semantic_sha256`, project identity, reviewer and
`action=review`. H review is distinct from actual Human Model Approval. Validators and
routing never write review decisions, approve models, freeze protocols or update state.

```text
python scripts/validate_model_verification.py '<contract>' --project-root '<root>' --require-reviewed
python scripts/run_model_verification.py '<contract>' --project-root '<root>' --output-dir '<new-directory>'
python scripts/validate_model_verification_receipt.py '<new-directory>/model-verification-receipt.json' --project-root '<root>'
```

The producer saves full contract bytes and snapshot, input manifest, current safety
sources, every finite metric and disposition in a new project-owned directory. The
consumer revalidates all H1/E history and raw MAT/JSON/CSV evidence, checks exact source
and input identities and independently recomputes the H2 result. Read budgets reject
oversized inputs and results; they never truncate samples or erase a failed point.
Each historical D/E operation may retain its exact original A/D/E qualification evidence
outside the project, including only its explicitly bound profiles/receipts and contained
qualification artifacts. Task, review and business numeric files remain inside the project;
external task or numeric artifacts are rejected. All permitted external qualification files
are included in the same byte budget and before/after hashes. Inputs and the H receipt's
own input/result/receipt artifacts are hashed before and after assessment. Preserve technical failures and old runs.

`valid` denotes technically complete, mechanically consistent evidence. All required
analyses completing yields `model_verification_decided`. All supporting the scoped claims
with current H1 yields `model_verified` and `claim_supported`. A legal metric crossing an
H2 threshold preserves valid, decided evidence with the predeclared `modify | reject`,
`impact_scope`, `required_action` and `return_stage`; it does not become model verified.
H2 claim bounds are distinct from E admissibility bounds. Missing evidence, invalid E,
failed H1 or source changes cannot yield a support decision.

Only an explicit caller may record `MODEL_VERIFICATION_DECIDED` or `MODEL_VERIFIED`
after checking the current evidence and its scope. This module never writes project state
or primary-run anchors. No H2 outcome grants I validation or J paper acceptance.
