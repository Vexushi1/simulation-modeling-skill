---
name: simulation-modeling-skill
description: Audit simulation tasks, design and challenge models, prepare human approval, map approved models and run qualified core Simulink models on MATLAB R2025b. Review bounded parameter studies and finite experiments. Verify numerical trajectories, residuals, constraints, conservation, events and drift; assess sensitivity, continuous or correlated uncertainty, stress, initial-condition robustness, failure brackets and solver or structural comparisons with source-bound receipts. Real-system validation, advanced construction domains and paper delivery remain deferred.
metadata:
  version: "0.9.0"
  primary_runtime: "MATLAB R2025b"
---

# Simulation Modeling Skill

## Start from the trusted root

Read [core/bootstrap.yaml](core/bootstrap.yaml) first. Follow its references to the router, module manifest, required contracts, project state, and output rules. Load the resources selected by the current route.

For repository changes, first read [the full implementation plan](docs/V1_FULL_IMPLEMENTATION_PLAN.md), [development governance](DEVELOPMENT_GOVERNANCE.md), and the affected contracts. The [roadmap](docs/V1_IMPLEMENTATION_ROADMAP.md) is a summary of that plan.

## Current scope

Version 0.9.0 implements the remaining Phase H analysis families under the full plan's feasibility amendments. Local checks, actual MATLAB qualification, independent review, CI, merge and release are separate evidence recorded in the development PR; a version label does not establish qualification.

For problem audit, read [modules/01_problem_audit.md](modules/01_problem_audit.md) and the Problem Contract schema before using its draft template. Text audit and read-only validation require no environment profile. Preserve original material identities, literal coverage, requirements, roles, dependencies, and critical ambiguities. Freeze requires a current source-bound review decision under the actual task authorization; resolve necessary material decisions without demanding approval for every question. Repository development authorization does not approve a real task or its model.

For model design, read [modules/02_model_design.md](modules/02_model_design.md), the Model Contract schema, and the Model Approval contract before using their templates. The design route requires a current frozen Problem Contract and no environment profile. Review the minimally sufficient mathematical structure, contextual fidelity, 0..N useful alternatives, four structural reviews, and nine challenges. Known facts and unknown parameters remain distinct. Prepare a concrete Brief before obtaining an actual human decision; development authorization or an agent recommendation cannot replace that approval.

Structural model identity excludes solver and parameter-value changes; the complete design digest includes the current Brief and design basis, so those changes can still invalidate approval. Validators check recorded consistency and cannot prove mathematical truth or authenticate invented human evidence.

Structural digests identify the registered expression, without proving symbolic equivalence. A changed digest alone does not establish a meaningful structural comparator.

Environment inspection needs no profile. Assurance requires current evidence for the requested operations. Resolver and validator results never write contracts, approvals, locks, or project state. For D, read [modules/03_domain_mapping.md](modules/03_domain_mapping.md) and its schemas before constructing a mapping or parameter file. Formal mapping requires current C human approval and no profile. Unknown values remain unknown. Native construction requires current A and independent D operation evidence; library loading is insufficient. The bounded builder consumes explicit reviewed instructions for six core block types and produces actual save/reopen/structure receipts in a new directory. Check the separate implementation execution permission. Simscape/Stateflow/System Composer construction and Phases I–K remain deferred; return their missing gates. Model approval alone grants no numerical execution.

## Use evidence within its scope

- Baseline products are candidates. Installation, a license test, or a resolvable function path does not prove that an operation is callable or qualified.
- Qualification applies to the exact operation, inputs, runtime identity, and execution channel recorded by the repository probe. Simulink library loading does not qualify simulation execution or a Toolkit composition.
- Validate current profile, raw report, receipt, source hashes, and process evidence against the runtime assurance contract before granting an assurance route. Use a new output directory for every probe. Runtime freshness controls runtime use; it does not expire unchanged problem, text-model, or mapping meaning. New model mutation requires current profiles; historical structures retain their bound execution-time evidence.
- Select only operations required by the current route. `selected` belongs to that route decision and is not written back to the probe profile. `--include-statistics` runs optional diagnostics; it does not make the three operations mandatory. Explicitly require the actual needed `statistics.fitlm`, `statistics.lhsdesign` or `statistics.normcdf` and check each qualification. See [operation qualification](docs/OPERATION_QUALIFICATION.md).
- Report missing, failed, stale, or deferred capabilities with their prescribed fallback. Resolver output does not update project state automatically.

The v1 target is a traceable problem-to-model-to-evidence workflow. Its detailed semantics and gates live in the full plan. This repository owns competition methodology and evidence; low-level execution prefers official MathWorks Toolkits under [the integration policy](core/upstream_integration_policy.md). Full paper composition can be delegated to `Vexushi1/mathmodel-skill` when a qualified handoff is available; that repository is not a core runtime dependency.

For E, read [modules/04_simulation_protocol.md](modules/04_simulation_protocol.md) and its contracts. Review and freeze the source-bound protocol against current B/C/D evidence. New execution requires current same-runtime A/E profiles, every actual required operation and the individually qualified solver. Preserve original files, review the actual termination and MAT/JSON/CSV outputs, and register state only through an explicit caller. A completed primary run awaits numerical verification; it establishes no physical or publication claim.

For F, read [modules/05_identification_calibration_optimization.md](modules/05_identification_calibration_optimization.md) and its contracts. Review the bounded standalone study against current B/C approval. ARX [1 1 1], single-gain Simulink calibration and one/two-variable quadratic SQP are conditionally available only with their actual operation qualification. Observed-data identification may precede D/E. Trials preserve approved parameters, models and state. Candidate adoption requires a new actual C approval, new D/E evidence and later H verification; a successful optimizer exit or training fit alone establishes no accepted primary result. The optional `parameter_study` state scope validates B/C/F history without current runtime permission.

## Finite experiments

Read [modules/06_experiment_design.md](modules/06_experiment_design.md). Use `experiment_design` for read-only review, `experiment_campaign` for qualified serial execution and `campaign_review` for independent receipt readback. Bind factors, ordered probabilities and settings to source declarations. Every draw uses an independently frozen E member and a fresh E receipt. Stop on a technical failure and preserve partial evidence. Complete fixed-size Monte Carlo statistics are conditional on the declared finite law. Continuous/correlated and parameter/IC studies use the separate H chain; LHS and parallel execution remain deferred.

## Numerical and model evidence

Read [modules/07_numerical_verification.md](modules/07_numerical_verification.md) and [modules/08_model_verification.md](modules/08_model_verification.md), their contracts and full plan §12.16–12.21. H1 supports actual `ode4`, `ode45` and `ode15s` three-level refinement, declared PWL trajectories and source-bound residual, constraint, conservation, event and drift checks. H2 requires accepted primary H1 and complete numeric evidence for source-required sensitivity, uncertainty, stress/IC, boundary, solver and structural studies. Missing or undefined required evidence blocks support; legitimate thresholds can modify/reject claims. Keep reconstruction and statistical scope explicit.

H hypothetical parameter/IC trials require a separately reviewed domain and current same-runtime A/E/H operation qualification for each case. Apply temporary SimulationInput overlays to owned model copies, preserve all original approval/protocol/primary/state bytes, and independently read actual state, timing and numeric evidence. Write only new evidence directories. Validators, routers and producers never generate model approvals, adopt trial values or advance project state. Historical assessment leaves current runtime readiness unassessed while retaining execution-time qualification and current source identities.
