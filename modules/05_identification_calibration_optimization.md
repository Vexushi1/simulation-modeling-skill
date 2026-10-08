# Conditional parameter studies

Read [the study schema](../core/parameter_study.schema.yaml), [the assurance contract](../core/parameter_study_assurance_contract.yaml), and the selected task pack before preparing a study. Current frozen B and actually approved C are necessary. Approved unknown parameters can enter F before D construction or an E primary run; retain their null values and existing source roles. Repository development authorization and a study review do not supply a real person's Model Approval.

Select exactly the implemented method needed by the task:

- [Parameter identification](../packs/task/parameter_identification.md): fixed SISO ARX `[1 1 1]`.
- [Calibration](../packs/task/calibration.md): one bounded scalar Simulink gain.
- [Optimization](../packs/task/optimization.md): a one/two dimensional explicit normalized-square objective with finite linear inequalities.

These are limited candidate operations. Dynamic/high-order/nonlinear identification, arbitrary model calibration, global/multiobjective/surrogate algorithms and G–K remain deferred. Record an unneeded analysis with its technical reason and claim limits instead of fabricating results.

## Prepare and review

Use [the unknown draft](../templates/contracts/parameter_study.yaml), bind the current C file, then select its current main model, relation and variable IDs. Register exact source path/SHA values already present in C; data sources also match B identities and original data-use ranges. Parameter symbols and units match C exactly. The selected C parameters must have the relevant identified/calibrated/optimized or assumed role and a research plan; given/derived parameters cannot become convenient fit/design variables. A trial initial guess is separately sourced and never written into C.

The validator accepts incomplete legal drafts and reports their missing gates. It checks explicit finite budgets, prior criteria, weights, bounds, numerical sources and supported mathematical formulas. It reads declared CSV rows as supplied, preserving sequence and lag rows without interpolation, cleaning, random splits or guessed units. Equal-byte copies do not create a new holdout. Neither a declared split nor a low loss authenticates real measurement, identifiability of an arbitrary model or statistical independence.

All three initial kernels require the selected C body's initial and boundary conditions to be explicitly `not_applicable`. Gain and quadratic objectives have no state; ARX evaluates predictions conditioned on measured lags. Specified or unknown conditions remain legal draft information and block trial readiness. These kernels cannot silently omit, replace or invent an additional approved condition protocol.

Run the read-only consumer from the repository root:

```text
python scripts/validate_parameter_study.py '<study>' --project-root '<project>'
python scripts/validate_parameter_study.py '<study>' --project-root '<project>' --require-reviewed
```

Complete the study before recording its independent source-bound review. Compute `semantic_digest` over the study excluding `status` and `review_record`; it still includes current C, every source, the numerical selections and all criteria. A separate review record uses `schema_version: 1`, the same `project_id`, `study_semantic_sha256`, and a file-bound decision with Unicode `start`/`end`, exact `quote`, `reviewed_by` and `action: review`. Its quote contains exactly one line each `project_id=...`, `study_semantic_sha256=...`, `reviewed_by=...`, `action=review`. An authorized explicit caller binds that record and sets reviewed status. Validators and routes never generate decisions or advance state.

`study_ready` describes complete source-backed settings; `reviewed` additionally checks the recorded review; `trial_execution_ready` combines those text gates. It does not assess current runtime or grant an unqualified operation. New execution additionally requires current same-host/runtime/channel A and the specific independent F operation; gain calibration also requires current E `ode4`. Actual A requirements are the union of method, study and caller. Optional `--include-statistics` core success cannot establish an explicitly needed statistics function.

## Evidence and final adoption

Use a new output directory for each qualification or project invocation. Preserve every actual objective call, candidate, raw process log, failure, incomplete output and termination. Receipts bind MAT v7 and independently checked numeric JSON evidence. Process completion, operation qualification, convergence, feasibility, prior criteria and candidate completion are distinct. Holdout evaluation occurs after candidate selection and cannot alter fitting or optimization settings.

All F outputs remain trial/candidate evidence. Only an explicit caller records PARAMETER_STUDY_REVIEWED or PARAMETER_CANDIDATE_COMPLETE after current checks. An accepted-trial artifact means the caller has reviewed that analysis evidence; it grants no primary simulation, numerical verification, real-system validation, global optimality or publication acceptance.

To adopt a candidate, prepare a new C design and Brief with its actual provenance/evidence, obtain a new real human decision and matching locked specification, then update D, freeze a final E protocol and rerun. Changing parameter values can preserve structural identity while invalidating full C approval. Keep previous models and failed evidence. Successful F optimization cannot approve that final model or bypass the later numerical checks.
