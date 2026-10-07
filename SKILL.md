---
name: simulation-modeling-skill
description: Audit simulation competition statements, design and challenge mathematical models, prepare human model approval materials, and inspect or assure the MATLAB R2025b and Simulink environment. Use for traceable Problem and Model Contracts, model identities, current source-bound decisions, capability evidence, and implemented or deferred routes. Implementation, simulation, numerical verification, and paper workflows remain deferred.
metadata:
  version: "0.3.0"
  primary_runtime: "MATLAB R2025b"
---

# Simulation Modeling Skill

## Start from the trusted root

Read [core/bootstrap.yaml](core/bootstrap.yaml) first. Follow its references to the router, module manifest, required contracts, project state, and output rules. Load the resources selected by the current route.

For repository changes, first read [the full implementation plan](docs/V1_FULL_IMPLEMENTATION_PLAN.md), [development governance](DEVELOPMENT_GOVERNANCE.md), and the affected contracts. The [roadmap](docs/V1_IMPLEMENTATION_ROADMAP.md) is a summary of that plan.

## Current scope

Version 0.3.0 adds Phase C text model design, challenge, and human approval checks to the merged Phase A/B infrastructure. Local checks, independent review, CI, merge, and release are separate evidence recorded in the relevant development PR; a version label does not establish qualification.

For problem audit, read [modules/01_problem_audit.md](modules/01_problem_audit.md) and the Problem Contract schema before using its draft template. Text audit and read-only validation require no environment profile. Preserve original material identities, literal coverage, requirements, roles, dependencies, and critical ambiguities. Freeze requires a current source-bound review decision under the actual task authorization; resolve necessary material decisions without demanding approval for every question. Repository development authorization does not approve a real task or its model.

For model design, read [modules/02_model_design.md](modules/02_model_design.md), the Model Contract schema, and the Model Approval contract before using their templates. The design route requires a current frozen Problem Contract and no environment profile. Review the minimally sufficient mathematical structure, contextual fidelity, 0..N useful alternatives, four structural reviews, and nine challenges. Known facts and unknown parameters remain distinct. Prepare a concrete Brief before obtaining an actual human decision; development authorization or an agent recommendation cannot replace that approval.

Structural model identity excludes solver and parameter-value changes; the complete design digest includes the current Brief and design basis, so those changes can still invalidate approval. Validators check recorded consistency and cannot prove mathematical truth or authenticate invented human evidence.

Structural digests identify the registered expression, without proving symbolic equivalence. A changed digest alone does not establish a meaningful structural comparator.

Environment inspection needs no profile. Assurance requires current evidence for the requested operations. Resolver and validator results never write contracts, approvals, locks, or project state. Phases D–K remain deferred; return their router prerequisites and next development phase without activating future modules or upstream skills. Model approval grants no numerical execution.

## Use evidence within its scope

- Baseline products are candidates. Installation, a license test, or a resolvable function path does not prove that an operation is callable or qualified.
- Qualification applies to the exact operation, inputs, runtime identity, and execution channel recorded by the repository probe. Simulink library loading does not qualify simulation execution or a Toolkit composition.
- Validate current profile, raw report, receipt, source hashes, and process evidence against the runtime assurance contract before granting an assurance route. Use a new output directory for every probe. Runtime freshness controls runtime use; it does not expire unchanged problem or text-model meaning.
- Select only operations required by the current route. `selected` belongs to that route decision and is not written back to the probe profile.
- Report missing, failed, stale, or deferred capabilities with their prescribed fallback. Resolver output does not update project state automatically.

The v1 target is a traceable problem-to-model-to-evidence workflow. Its detailed semantics and gates live in the full plan. This repository owns competition methodology and evidence; future low-level execution prefers official MathWorks Toolkits under [the integration policy](core/upstream_integration_policy.md). Full paper composition can be delegated to `Vexushi1/mathmodel-skill` when a qualified handoff is available; that repository is not a core runtime dependency.
