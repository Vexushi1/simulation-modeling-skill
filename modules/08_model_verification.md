# Model claim assessment and complete analysis studies

Read [the H2 contract](../core/model_verification_contract.yaml), [H1](07_numerical_verification.md),
current C approvals, D implementations, independently frozen E protocols and the full plan
§12.16–12.21. H2 computes evidence in Python and consumes separately qualified H trial
studies. This receipt grants no MATLAB operation,
real-system validation, publication acceptance, automatic model approval or state transition.

## Review a claim and its required analyses

Start with [the draft template](../templates/contracts/model_verification.yaml). Bind the
current accepted primary H1 receipt as `primary_numerical_receipt`. Register other H1
receipts in `members`; `primary` is reserved. Every participant must have its own current
accepted H1 and complete source-bound E evidence. Historical analysis leaves current
runtime readiness unassessed, while each E receipt retains its execution-time A/E gates.
Ordinary new simulations use the E producer. Alternative-world trial studies use
the independent `h.analysis_trials` qualification and producer. The original approved
model, primary E protocol/receipt and primary H1 anchors remain immutable.

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

Advanced analyses use `claims[].study_requirements`. Every record declares `id`, `method`,
`requirement: required | not_required`, technical `reason`, and `study_contract` / `study_receipt`
path/SHA bindings (both null when omitted). If this field is present, the obligation source
also contains `study_requirements: [{id, method, requirement, reason}]`. The full settings
source binds the complete references as well. Register every method materially needed by
the claim; one completed study does not cover other required methods. Older finite contracts
without this field retain their original behavior. A required missing study blocks H2.

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
  Compare at least two actual `ode4`, `ode45`, or `ode15s` participants, each with
  accepted H1. Compare each metric with primary using
  `abs(difference) <= absolute_tolerance + relative_tolerance * max(abs(both values))`.
  Do not pair different adaptive samples by index. Source-bound metrics also include
  peak/peak time, piecewise-linear integrals, events and registered residual/constraint/
  conservation/drift checks through the common H1 metric evaluator. Scope and undefined
  event/check outcomes follow that evaluator. Runtime conclusions require a separate
  `runtime_comparison` study and verified actual timing metadata.
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

## Source-required studies

The study contract freezes ordered factors, reviewed trial permission/domain, actual
parameter/Integrator/external-input locators, settings, deterministic design and roles,
metric, numerical policy, inference, prior criterion and claim scope. Each original base
and every actual point must retain current numerical acceptance. A study cannot substitute
a hypothetical trial for the original primary H1. Changing a parameter or initial condition
requires the explicit reviewed alternative-world permission and qualified trial engine;
it never changes approved C parameters or the original D/E execution.

Implemented sensitivity study methods:

- `local_derivative` and `parameter_oat`: source-declared central h and h/2, or predeclared
  second-order forward/backward boundary stencils. Report both derivatives, literal physical
  units and the prior two-scale agreement. This is a finite-difference approximation, not
  proof of differentiability.
- `normalized_sensitivity`: the same stencil with `relative_elasticity`, using actual
  factor/output baselines, or positive `reference_scales`. A zero relative reference is
  undefined; there is no epsilon substitution.
- `morris`: even grid, registered Delta and complete ordered random trajectories. Report
  signed mu, mu-star and sample sigma in normalized coordinates and physical-unit mu.
  Sigma reflects nonlinear, interaction and numerical variation together.
- `sobol`: frozen independent A/B and AB blocks, optional BA blocks for second order.
  Report pooled-center Saltelli S1, Jansen ST and optional S2 under the reviewed independent
  product law. Finite negative or greater-than-one estimates remain untrimmed. Zero sample
  variance is undefined and does not prove population constancy.
- `variance_based`: the complete independent weighted Cartesian design and all ANOVA
  subsets. Report variance closure and main/total indices for this exact finite discrete
  law. Conditional effects and variances are computed in centered coordinates, preserving
  large common response offsets. Fixed machine-roundoff guards check product weights,
  reconstruction, orthogonality and variance closure; unresolved decomposition is undefined.
  Zero-probability rows remain required native evidence.
- `prcc`: average ranks including ties, fixed-tolerance projection onto intercept and other
  factor ranks, then correlation of the residuals. Rank-deficient controls retain a diagnosed
  unique-span association while suppressing standard inference. Zero residual variance is
  undefined. Correlated inputs are permitted; the result is conditional rank association,
  with no causal or Sobol variance interpretation. The Gaussian-copula covariance factor
  must reconstruct the exact reviewed correlation matrix within a fixed machine-roundoff
  bound before sampling; source tolerance can only tighten that bound. Genuine singular
  support is retained, while an indefinite law is rejected rather than repaired.

Other complete study methods are `independent_mc`, `gaussian_joint_mc`, `gaussian_copula_mc`,
`initial_condition_catalog`, `initial_condition_grid`, `joint_stress_catalog`, `stress_grid`,
`scenario_response`, `failure_boundary`, and `runtime_comparison`. Their own reviewed
design, actual execution and independent study receipt govern their conclusions. A finite
continuous-law sample or boundary bracket never proves behavior throughout the full domain.
Classic Sobol and product ANOVA reject correlated-factor interpretations.

Sampling uses a registered seed and PCG64 design, not an unspecified random generator or
a claim of quasi-Monte Carlo Sobol sequence qualification. Normal-law draws outside the
reviewed execution domain fail explicitly; they are never clipped or silently redrawn.
Optional percentile bootstrap resamples whole Morris trajectories, paired Sobol blocks or
complete PRCC rows. It performs no new native calls and records every degenerate replicate.
An interval computed from mathematically valid replicates is labeled conditional if any
replicate is undefined; it cannot be called unconditional nominal coverage. Exact finite
ANOVA and deterministic local stencils do not acquire bootstrap intervals.

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
and input identities, independently consumes every source-required complete study, and
recomputes the H2 result. Public `study_reports` and each claim's `study_decisions` bind
current study contract/semantic/receipt identities and distinguish completion, definition
and threshold acceptance. Read budgets reject
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
Critical undefined statistics or numerical checks and incomplete required studies block
the decision. A technically complete, defined study failing its prior claim criterion
preserves valid H2 evidence with the declared modify/reject action.

Only an explicit caller may record `MODEL_VERIFICATION_DECIDED` or `MODEL_VERIFIED`
after checking the current evidence and its scope. This module never writes project state
or primary-run anchors. No H2 outcome grants I validation or J paper acceptance.
