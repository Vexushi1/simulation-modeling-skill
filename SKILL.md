---
name: simulation-modeling-skill
description: Audit simulation competition statements, attachments, requirements, data roles, and question dependencies, and inspect or assure the MATLAB R2025b and Simulink environment. Use for a traceable Problem Contract, source-bound review decisions, current capability evidence, and implemented or deferred routes. Model design, simulation, verification, and paper workflows remain deferred.
metadata:
  version: "0.2.0"
  primary_runtime: "MATLAB R2025b"
---

# Simulation Modeling Skill

## Start from the trusted root

Read [core/bootstrap.yaml](core/bootstrap.yaml) first. Follow its references to the router, module manifest, required contracts, project state, and output rules. Load the resources selected by the current route.

For repository changes, first read [the full implementation plan](docs/V1_FULL_IMPLEMENTATION_PLAN.md), [development governance](DEVELOPMENT_GOVERNANCE.md), and the affected contracts. The [roadmap](docs/V1_IMPLEMENTATION_ROADMAP.md) is a summary of that plan.

## Current scope

Version 0.2.0 adds Phase B problem-audit infrastructure to the merged Phase A environment infrastructure. Local checks, independent review, CI, merge, and release are separate evidence recorded in the relevant development PR; a version label does not establish qualification.

For problem audit, read [modules/01_problem_audit.md](modules/01_problem_audit.md) and the Problem Contract schema before using its draft template. Text audit and read-only validation require no environment profile. Preserve original material identities, literal coverage, requirements, roles, dependencies, and critical ambiguities. Freeze requires a current source-bound review decision under the actual task authorization; resolve necessary material decisions without demanding approval for every question. Repository development authorization does not approve a real task or its model.

Environment inspection needs no profile. Assurance requires current evidence for the requested operations. Resolver and validator results never advance project state automatically. Phases C–K remain deferred; return their router prerequisites and next development phase without activating future modules or upstream skills.

## Use evidence within its scope

- Baseline products are candidates. Installation, a license test, or a resolvable function path does not prove that an operation is callable or qualified.
- Qualification applies to the exact operation, inputs, runtime identity, and execution channel recorded by the repository probe. Simulink library loading does not qualify simulation execution or a Toolkit composition.
- Validate current profile, raw report, receipt, source hashes, and process evidence against the runtime assurance contract before granting an assurance route. Use a new output directory for every probe. Runtime freshness controls runtime use; it does not expire unchanged problem meaning.
- Select only operations required by the current route. `selected` belongs to that route decision and is not written back to the probe profile.
- Report missing, failed, stale, or deferred capabilities with their prescribed fallback. Resolver output does not update project state automatically.

The v1 target is a traceable problem-to-model-to-evidence workflow. Its detailed semantics and gates live in the full plan. This repository owns competition methodology and evidence; future low-level execution prefers official MathWorks Toolkits under [the integration policy](core/upstream_integration_policy.md). Full paper composition can be delegated to `Vexushi1/mathmodel-skill` when a qualified handoff is available; that repository is not a core runtime dependency.
