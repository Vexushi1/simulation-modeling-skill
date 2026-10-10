# Numerical refinement evidence

Read [the H1 contract](../core/numerical_verification_contract.yaml) after the current approved C model, D implementation and three independently frozen E protocols. This module evaluates existing complete E receipts in Python. New E runs still require the E runner's current independent A/E qualifications. H1 does not invoke MATLAB, freeze protocols, approve models or write project state.

## Review the finite assessment

Use [the draft](../templates/contracts/numerical_verification.yaml). Bind the coarse primary protocol and two distinct ordered refinement protocols. Keep the complete C/D approval, parameters, SLX, initial/boundary conditions, time, external inputs, output mappings, logging, seed, E admission metrics and warning policy identical. Only the method's selected numerical settings may differ; protocol source/scenario/review identities and solver explanation text may differ.

`ode4_step_refinement` uses exactly h, h/2 and h/4. Declare every coarse integer time point; each actual native output must cover its own complete integer grid. Constant external inputs and continuous piecewise-linear inputs with coarse-grid breakpoints are supported. The interval is at most 30 seconds, each level at most 3000 steps and at most two outputs.

`ode45_tolerance_refinement` divides both RelTol and AbsTol by 10 and then 100, with every other execution setting unchanged. Declare start and stop only. It assesses two actual endpoint samples; it does not establish whole-trajectory refinement. H combinations with ode15s remain deferred.

Time matching uses `64 * binary64 epsilon * max(1, abs(t))`. For fixed refinement this must be strictly smaller than one eighth of the finest step. Missing, duplicate, ambiguous or unrepresentable samples block assessment. No interpolation, synthetic time axis or copied sample is allowed.

Bind the method, comparison times, output identities/units and complete criteria, all five check obligations, read budget and claim limit to a structured source snapshot. A reviewed contract requires an independent review record with the current semantic digest, project, reviewer and exact unique `action=review` context. This analysis review supplies no actual C Human Model Approval.

Residual, constraint, conservation, event localization and numerical drift require explicit source-based reasons. Their general evaluators are deferred. Any `required` or `deferred` obligation blocks numerical acceptance; lack of capability cannot justify `not_applicable`.

```text
python scripts/validate_numerical_verification.py '<contract>' --project-root '<root>' --require-reviewed
python scripts/run_numerical_verification.py '<contract>' --project-root '<root>' --receipt '<primary E receipt>' --receipt '<first refinement E receipt>' --receipt '<second refinement E receipt>' --output-dir '<new directory>'
python scripts/validate_numerical_verification_receipt.py '<numerical-verification-receipt.json>' --project-root '<root>'
```

## Read the numerical conclusion

For each output, D01 and D12 are maximum absolute adjacent-level differences at the declared common points. The shared scale is the largest absolute value across all three compared sets. Both differences must satisfy `absolute_tolerance + relative_tolerance * scale`; the coarse primary must pass too. Above the declared roundoff floor D12 must not exceed `contraction_limit * D01`. At or below the floor both differences must remain below it. All differences, scales and tolerances must be finite.

An empirical step order is reported only for two resolved nonzero differences. All-zero or floor-limited agreement has null order; tolerance refinement does not report a discretization order. These finite comparisons give empirical agreement under the declared criteria. They supply no true error bound, fourth-order proof, continuous-domain stability or physical validity.

The producer owns a new output directory. Criterion failure retains complete technically valid evidence with a reject disposition; missing/changed input or technical failure retains blocked evidence and cannot be accepted. The consumer rechecks E's complete execution-time A/E qualifications, source/model/protocol identities and MAT/JSON/CSV numbers, then recomputes H1 and compares its exact results and manifest. Current runtime TTL does not expire unchanged historical analysis, while changed safety source or bound project data makes it stale. Input and output byte/sample budgets reject excess data without truncation, and input SHA is checked again after reading.

Task sources, protocols, models, reviews, numeric outputs and H artifacts stay inside the project root. Only the original D/E request's explicitly bound execution-time A/D/E qualification profiles and receipts may keep their original external paths; their native artifacts must remain inside their qualification directories. These exact files count toward the same read budget and before/after hashes, and existing D/E consumers independently verify them. Do not copy or substitute qualification history. The final manifest includes H's own receipt, captured input, original contract and result; both file identities and safety sources are rechecked before acceptance. Source snapshots and computed results preserve exact JSON types, including integer versus float.

Only an explicit authorized caller may record `NUMERICALLY_VERIFIED`, bound to the current H1 receipt and its finite claim scope. H1 grants no H2, reality validation, evidence publication or paper acceptance.
