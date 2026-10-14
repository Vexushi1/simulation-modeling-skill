# Numerical verification of recorded evidence

Read [the H1 contract](../core/numerical_verification_contract.yaml), full plan §12.16–12.21 and the current approved C/D/E chain. Standalone H1 consumes three distinct, independently frozen E protocols and their complete actual receipts. It does not execute MATLAB, approve a model, freeze a protocol or write state. New runs require their own current execution qualifications. The independent H trial operation uses the same pure numerical evaluator after its own native consumer establishes the approved baseline, permitted hypothetical point, states, restoration and execution-time A/E/H qualifications.

## Declare refinement and trajectory scope

Use [the draft](../templates/contracts/numerical_verification.yaml). Keep approved model/SLX, parameters, initial/boundary conditions, time, input waveforms, outputs, admission metrics, seed and warning policy unchanged between the three numerical levels. Only the chosen numerical refinement fields may change. Protocol source/review identities and solver explanation text can differ.

- `ode4_step_refinement` uses exactly h, h/2 and h/4. Every output and state must retain its complete actual integer grid, including in reconstructed mode. Missing native grid points never become acceptable by interpolation. Inputs are constant or continuous PWL with breakpoints aligned to the coarse grid.
- `ode45_tolerance_refinement` and `ode15s_tolerance_refinement` divide both RelTol and AbsTol by 10 and 100 while keeping all other solver settings fixed. No fixed discretization order is claimed for tolerance refinement.
- `scope: actual_points` retains the original complete coarse grid or two actual adaptive endpoints. Time matching uses `64 * binary64 epsilon * max(1, abs(t))`; fixed matching tolerance must be below one thirty-second of the finest step. Missing, duplicate and ambiguous actual samples block.
- `scope: pwl_trajectory` and `trajectory: {mode: pwl_union, max_gap: <prior limit>}` compare the complete recorded piecewise-linear reconstructions. Evaluate each on the union of all three native meshes. The maximum adjacent-level difference at union knots equals the supremum between those reconstructed curves on the full covered interval. Synthetic evaluations are never reported as actual native samples. No extrapolation or discarded intervals is allowed.

Each output binds its real port/variable/unit and absolute/relative tolerance, contraction limit and roundoff floor. A trial state instead binds `kind: state`, variable/unit and exact BlockPath, with no invented port; every actual trial state requires its own criteria. Standalone E receipts currently expose root outputs; use approved observed-state relations or the separately qualified H state interface when a check needs states.

Trial `solver_levels` contain exactly E's controlled numeric solver fields (`name,type,max_step,min_step,initial_step,rel_tol,abs_tol,fixed_step,zero_crossing`). Protocol `reason` and `classification` fields are bound in E review and do not belong in the native numeric solver object. Invalid shape or applicability blocks source preflight before execution.

D01 and D12 must both satisfy `atol + rtol * max(abs(all three compared sets))`. Above the floor D12 must contract by the prior limit; at or below it both differences must stay below the floor. Zero differences have null order. An empirical fixed-step order describes the selected recorded-point or reconstruction comparison, not a proof of the solver's formal order.

Legacy contracts retain their original limits. Extended policies replace the 30-second/two-output limit with source-declared file, sample, union-knot, AST, check and computation budgets. The absolute sample cap is 12001 per series and there is no truncation. Unrepresentable time axes, overflow and exhausted budgets remain incomplete.

## Bind observations and typed mathematics

`observables` entries contain `id`, `kind`, `unit`, `dimensions` and the applicable variable/port/BlockPath. Kinds are `output`, `state`, `input`, `parameter` and `time`. Bind every non-time variable to current C and all root/state/parameter identities to their actual approved/native mappings. Parameter entries also require the exact `code_name` in current D parameter provenance. An output-state equivalence is an explicit current C relation included in the check's relation anchors; the evaluator never guesses a hidden state.

Dimensions use integer exponents of `mass,length,time,current,temperature,amount,luminous_intensity`. Supported SI and prefix unit products/divisions/powers are checked against dimensions and converted to canonical SI during expression arithmetic. A custom observation unit requires an explicit reviewed `canonical_unit` and `scale`; optional `offset` supports an affine conversion. Recognized conversions cannot contradict their physical scale. Values and thresholds in a check are reported in that check's unit. Unknown units and unbound conversions block mathematical checks.

AST nodes have exact fields:

```yaml
# Leaves
{op: variable, id: y}
{op: constant, value: 1.0, unit: m/s, dimensions: {length: 1, time: -1}}
{op: derivative, id: y, scheme: central}
{op: integral, id: y, start: 0.0}
# Unary and binary examples
{op: neg, args: [{op: variable, id: y}]}
{op: sub, args: [{op: variable, id: y}, {op: variable, id: reference}]}
{op: pow, args: [{op: variable, id: dimensionless}], exponent: 2}
```

Other supported operations are add/mul/div/min/max/abs/sqrt/exp/log/sin/cos. Transcendental arguments are dimensionless. No string, callback or arbitrary code is executed. Finite-difference derivatives are explicitly approximate: central uses the nonuniform three-point stencil at interior native knots and one-sided endpoints, while an explicitly forward/backward stencil blocks when its required endpoint neighbour is missing. Between knots it differentiates the declared PWL segment. Integrals use exact segment integration of the recorded reconstruction. Every traversed expression and integration axis counts toward the work budget.

Every check binds `id,kind,window,source_ids,relation_ids,unit,dimensions`. All referenced C variables must be covered by current relation anchors. All five obligations declare `required` or `not_applicable`, reasons and sources. Required checks must execute; `check_ids`, if present, match the complete requested set. Neither absent checks nor obsolete `deferred` decisions establish acceptance.

- **Residual:** an `expression` for algebraic/differential finite-difference residual, or `mode: integral` with `state/rhs` (equivalently inventory/flux). Integrated defect is `x(t)-x(t0)-integral(f)` and avoids inventing a true derivative.
- **Constraint:** expression, `relation: eq|le|ge` and explicit threshold. Evaluate equality magnitude or the appropriate one-sided violation.
- **Conservation:** inventory and net source/boundary flux expressions. Inspect all prefix balance defects and segment interior extrema, not only the final cancellation.
- **Drift:** expression and optional reference, an amount tolerance plus `drift_tolerance` and `rate_unit`. Subtract the initial detrended value and calculate the time-weighted continuous PWL slope. Adaptive observation density does not alter the weighting. Intended forcing needs the correct reference/balance law.
- **Event localization:** expression, threshold, direction, expected_count, matching (`first` or `all`), time/value tolerances and maximum bracket width. Preserve crossings and every referenced observable's actual indexed sample brackets across all three levels. `reconstructed_zero` describes the event-function reconstruction, including union points interpolated from other actual axes; it never asserts native event detection. Both reconstruction and actual observable support must satisfy the prior bracket width. Boundary events require an explicit rule. Zero platforms, unresolved contacts, insufficient separation or localization width are incomplete; wrong count or time agreement is a criterion failure. Contact mode only reports resolved recorded contacts, not a continuous tangency proof. Solver StopEvent remains termination metadata.

Non-event checks require prior positive `absolute_tolerance`, nonnegative `relative_tolerance` and reference `scale`. Apply every criterion to all three levels, including the coarse primary. Optional check convergence requires its own contraction and floor. Derived expression quantities are reconstructed from evaluations on complete observation-union knots; nonlinear expressions are not thereby proved between the underlying continuous signal values.

## Preserve continuous claim limits

Default conclusions concern the recorded points or complete declared reconstruction. PWL extrema and integrals do not prove the continuous solution's true peak, integral or exact event time. A requested full-window `continuous_scope.target: underlying_continuous` requires complete PWL trajectory refinement and a complete source-bound reviewed envelope; endpoint agreement cannot become a full-window conclusion:

```yaml
continuous_scope:
  target: underlying_continuous
  source_ids: [analytic_proof]
  reason: Conditional on the reviewed bounds and their stated assumptions.
  envelope:
    kind: reviewed_uniform_bound
    window: [0.0, 1.0]
    proof_source_ids: [analytic_proof]
    output_bounds:
      - {variable_id: y, unit: m, levels: [0.0001, 0.00001, 0.000001]}
    check_bounds:
      - {id: balance, unit: m, levels: [0.0001, 0.00001, 0.000001]}
```

Bind every output/check, three levels, unit, full window and proof source to the complete H review. Check primary bounds and differences plus their bound allowances against unchanged criteria. Event bounds are **time** bounds in seconds; a function-amplitude bound alone cannot supply one. The independently reviewed proof must justify its transversality/monotonicity assumptions or directly justify the time bound. Drift additionally needs `rate_unit` and three `rate_levels`. Acceptance states `conditional_on_reviewed_uniform_envelope`; it never means the evaluator automatically proved source mathematics. Missing or inapplicable evidence remains incomplete.

## Shared computation and historical evidence

```python
from numerical_obligations import evaluate_trial_numeric, validate_trial_numeric_policy
from numerical_math_common import evaluate_metric

# levels: three {run_spec, outputs, states} native records; no file I/O here.
# context: current C variables/relations and exact D parameter_bindings.
result = evaluate_trial_numeric(levels, numeric_policy, context)
metric = evaluate_metric({'statistic': 'integral', 'output_port': 1, 'unit': 'm*s'},
                         levels[0], context=context, numeric_policy=numeric_policy)
```

`numeric_context_from_documents(model, selection, parameters)` selects already validated documents without I/O. Trial policy also binds three exact `solver_levels`; it may not change any physical run_spec field between levels. Metrics include final/minimum/maximum/peak/peak_time/integral/absolute_integral/squared_integral and event/check metrics. Integral labels are `<output unit>*s` or `(<output unit>)^2*s`. Peak time and event time use seconds; event count uses `1`. Nonunique peak time and undefined event occurrence remain undefined, never zero. Derived metric definitions must exactly bind an executed current H1 check, its kind, result unit and window.

All policy settings, obligations, complete expressions, units, envelopes, budgets and limits are captured by `settings_snapshot`. Preserve independent review, exact typed values, source identities, all transitive read budgets and before/after SHA. A legitimate failed criterion retains complete rejection evidence. Technical/mathematical incompleteness retains its explanation and cannot set numerically_verified.

```text
python scripts/validate_numerical_verification.py '<contract>' --project-root '<root>' --require-reviewed
python scripts/run_numerical_verification.py '<contract>' --project-root '<root>' --receipt '<primary>' --receipt '<level1>' --receipt '<level2>' --output-dir '<new directory>'
python scripts/validate_numerical_verification_receipt.py '<receipt>' --project-root '<root>'
```

Historical consumers independently validate original native E MAT/JSON/CSV, current source/model/protocol bytes and each execution-time qualification. Current TTL affects new execution, not unchanged history. Task/model/review/numeric files stay project-contained; only specifically typed original execution qualifications retain authorized external paths. Filename resemblance or task assertions grant no qualification role. Source object/array rules, unique keys, finite values, cycle rejection and exact result recomputation remain unchanged.

Only an explicit authorized caller records NUMERICALLY_VERIFIED and its scope. H1 grants no reality validation, publication acceptance or automatic model approval.
