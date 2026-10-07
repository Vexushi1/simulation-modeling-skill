---
name: simulation-modeling-skill
description: Competition-oriented simulation modeling workflow for MATLAB R2025b and Simulink. Use for simulation problem audit, dynamic/physical/hybrid model design, Simulink/Simscape/Stateflow implementation planning, parameter identification and calibration, simulation experiment design, optimization, numerical verification, sensitivity/robustness, multi-model comparison, V&V, scientific evidence and paper handoff.
metadata:
  version: "0.1.0"
  primary_runtime: "MATLAB R2025b"
---

# Simulation Modeling Skill

## Mission

Turn a simulation-modeling problem into a reproducible evidence chain:

```text
PROBLEM
→ REQUIREMENT FREEZE
→ SYSTEM / MODEL DESIGN
→ IMPLEMENTATION
→ SIMULATION PLAN
→ RUN / CALIBRATE / OPTIMIZE
→ VERIFY
→ SENSITIVITY / ROBUSTNESS / MODEL COMPARISON
→ VALIDATE
→ FIGURE / TABLE EVIDENCE
→ PAPER HANDOFF
```

This skill is competition-oriented. A model that merely runs is not considered complete.

## Runtime baseline

Before execution, read:

1. `core/environment_baseline.yaml`
2. `core/capability_taxonomy.yaml`
3. `docs/CANONICAL_ARCHITECTURE.md`

Primary target is MATLAB R2025b + Simulink.

Do not infer toolbox usability from a license flag alone.

## Upstream execution policy

Read `core/upstream_integration_policy.md`.

Prefer current official MathWorks Agentic Toolkit capabilities for low-level MATLAB/Simulink work instead of duplicating them locally.

This repository decides:

- why a capability is needed;
- when it is allowed to run;
- what evidence it must return;
- how the result changes the model or claim.

## Core workflow

### 1. Audit the problem

Do not start by dragging blocks or generating MATLAB code.

Freeze:

- study object and system boundary;
- direct and implicit objectives;
- inputs and disturbances;
- state, algebraic and decision variables;
- parameters;
- outputs and observables;
- initial and boundary conditions;
- events/switching logic;
- constraints;
- data roles;
- subproblem dependencies;
- required deliverables.

### 2. Design the mathematical/system model

Maintain explicit separation:

- Model;
- Solver;
- Validator.

For a material modeling decision, compare a classical/stable route and an improved route when meaningful.

Reject complexity without mechanism, data or computational support.

### 3. Select implementation domain

Choose from the mathematical structure, not from block availability:

- Simulink;
- Simscape;
- Stateflow;
- System Composer;
- MATLAB numerical model;
- mixed composition.

### 4. Freeze simulation protocol

Record:

- parameters and provenance;
- scenarios/inputs;
- initial/boundary conditions;
- solver;
- step/tolerance controls;
- stop conditions;
- logging;
- random seed when applicable;
- acceleration mode;
- expected evidence.

### 5. Execute, identify, calibrate or optimize

Activate only required capabilities.

Prefer non-destructive run configuration through `Simulink.SimulationInput` where appropriate.

### 6. Verify the computation

Check relevant numerical risks before interpreting plots.

Examples:

- time-step/tolerance convergence;
- solver consistency;
- conservation/invariants;
- event localization;
- algebraic-loop/stiffness diagnostics;
- residuals and feasibility;
- limiting cases.

### 7. Perform model verification

Every material result must make an explicit structural-comparison decision:

- `required`; or
- `not_applicable` with technical justification.

If required, the comparator must be mathematically/physically distinct. A new solver or parameter value is not a new model.

Also evaluate parameter sensitivity, scenario robustness and solver/algorithm robustness when they target material claims.

### 8. Validate

Assess whether the model is adequate for the intended real/target system and claim.

Use reference/experimental data, accepted benchmarks, tests, coverage, analytic cases or physical constraints as available.

### 9. Build evidence

Figures/tables must answer a model, solver, robustness or validation question.

Do not create decorative analysis merely to increase figure count.

### 10. Paper delivery

This repository produces simulation-specific writing evidence and claim boundaries.

When a mature general competition-paper writer is available, prefer delegation to `Vexushi1/mathmodel-skill` rather than maintaining a second full paper-writing authority here.

## Current bootstrap status

v0.1.0 contains foundation contracts only.

Implementation phases and release gates are defined in `docs/V1_IMPLEMENTATION_ROADMAP.md`.

Do not treat unimplemented phases as completed capabilities.
