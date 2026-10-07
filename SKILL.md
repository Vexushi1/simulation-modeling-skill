---
name: simulation-modeling-skill
description: Inspect and assure the MATLAB R2025b and Simulink environment for competition simulation modeling. Use for runtime preparation, current capability evidence, and routing simulation requests to implemented or deferred capabilities. Business modeling, simulation, verification, and paper workflows remain deferred until their development phases pass.
metadata:
  version: "0.1.1"
  primary_runtime: "MATLAB R2025b"
---

# Simulation Modeling Skill

## Start from the trusted root

Read [core/bootstrap.yaml](core/bootstrap.yaml) first. Follow its references to the runtime assurance, capability profile, router, module manifest, project state, and output contracts. These contracts define the active Phase A behavior.

For repository changes, first read [the full implementation plan](docs/V1_FULL_IMPLEMENTATION_PLAN.md), [development governance](DEVELOPMENT_GOVERNANCE.md), and the affected contracts. The [roadmap](docs/V1_IMPLEMENTATION_ROADMAP.md) is a summary of that plan.

## Current scope

Version 0.1.1 implements Phase A infrastructure and remains unreleased, pending independent PR qualification and review. It provides environment inspection and assurance for MATLAB R2025b + Simulink 25.2. Read-only inspection does not require an existing profile and cannot advance project state.

Phases B–K are deferred. For problem audit, model design, implementation, business simulation, identification, verification, validation, figures, or paper delivery, return the deferred route, reason, prerequisites, and next development phase from the router. Do not activate future modules or upstream skills to bypass that result.

## Use evidence within its scope

- Baseline products are candidates. Installation, a license test, or a resolvable function path does not prove that an operation is callable or qualified.
- Qualification applies to the exact operation, inputs, runtime identity, and execution channel recorded by the repository probe. Simulink library loading does not qualify simulation execution or a Toolkit composition.
- Validate current profile, raw report, receipt, source hashes, and process evidence against the runtime assurance contract before granting an assurance route. Use a new output directory for every probe.
- Select only operations required by the current route. `selected` belongs to that route decision and is not written back to the probe profile.
- Report missing, failed, stale, or deferred capabilities with their prescribed fallback. Resolver output does not update project state automatically.

The v1 target is a traceable problem-to-model-to-evidence workflow. Its detailed semantics and gates live in the full plan. This repository owns competition methodology and evidence; future low-level execution prefers official MathWorks Toolkits under [the integration policy](core/upstream_integration_policy.md). Full paper composition can be delegated to `Vexushi1/mathmodel-skill` when a qualified handoff is available; that repository is not a core runtime dependency.
