# Canonical Architecture — Simulation Modeling Skill

> Status: bootstrap authority draft  
> Primary runtime baseline: MATLAB R2025b + Simulink  
> Target: competition-oriented simulation modeling with engineering-grade reproducibility and paper-ready evidence.

## 1. Scope

This repository is a **simulation-modeling methodology and orchestration layer**.

It owns:

1. problem and requirement audit for simulation tasks;
2. system boundary, state/parameter/input/output abstraction;
3. model-family and fidelity selection;
4. mathematical model to Simulink/Simscape/Stateflow mapping;
5. solver and simulation experiment design;
6. parameter identification, calibration and optimization;
7. numerical verification, sensitivity, robustness, uncertainty and multi-model comparison;
8. verification & validation;
9. scientific evidence packaging;
10. simulation-specific paper/report delivery.

It does not attempt to reimplement every MATLAB/Simulink API as a local skill.

## 2. Runtime target

The project has one strong runtime baseline:

- MATLAB: **R2025b**
- Simulink: **R2025b**
- Platform-specific behavior must be discovered at runtime rather than inferred from documentation alone.

Older MATLAB releases are not a release target for v1.0. Upstream MathWorks skills may support older releases, but this repository optimizes behavior, examples and validation for R2025b.

## 3. Layered architecture

### Layer A — Runtime & capability assurance

Before model design:

- confirm MATLAB release;
- detect installed products;
- distinguish installed product, licensed product and actually callable capability;
- record unavailable or contradictory capabilities;
- freeze the project backend and capability profile.

### Layer B — Problem audit & requirement freeze

Adapt the strongest methodology from `mathmodel-skill/modules/01_problem_audit.md` to simulation-specific semantics.

Every subproblem defines:

- physical/system object;
- simulation purpose;
- input, disturbance, state, algebraic, parameter and output variables;
- initial and boundary conditions;
- event/switching logic;
- required fidelity;
- observable/calibration/validation data roles;
- explicit and mechanism-derived constraints;
- expected paper/result deliverables;
- cross-question dependencies.

No Simulink implementation begins while a material ambiguity changes model structure, state definition, constraints, boundary conditions or final claims.

### Layer C — System & model design

Maintain strict role separation:

- **Model**: mathematical/physical representation;
- **Solver**: numerical integration, optimization or search method;
- **Validator**: independent evidence used to assess the model/solution.

For each material subproblem, compare at least:

1. a conservative/classical model route;
2. an improved or cross-domain route when evidence and computational budget support it.

Model selection must justify:

- required mechanisms;
- fidelity level;
- identifiability;
- data support;
- computational feasibility;
- expected failure modes.

### Layer D — Execution adapter

Use upstream capabilities instead of copying their implementation rules.

Primary upstream:

- `matlab/simulink-agentic-toolkit`
- `matlab/matlab-agentic-toolkit`

Supplementary specialized skills may be used after explicit compatibility review.

The local repository owns routing and competition methodology; upstream skills own low-level implementation behavior such as model editing, simulation, testing and supported toolbox workflows.

### Layer E — Simulation experiment design

Every nontrivial simulation records:

- model/version identity;
- parameter set;
- input/scenario identity;
- initial/boundary conditions;
- solver family and configuration;
- tolerances and step controls;
- stop conditions;
- logging specification;
- random seed when applicable;
- acceleration mode;
- hardware/runtime metadata when performance is claimed.

Prefer `Simulink.SimulationInput` for non-destructive per-run configuration.

### Layer F — Calibration, identification & optimization

Depending on the task:

- direct physical parameter calculation;
- system identification;
- least-squares / constrained estimation;
- Simulink Design Optimization;
- local/global optimization;
- surrogate or multi-objective optimization;
- calibration against experiment or reference data.

Parameter provenance must distinguish:

- given;
- derived;
- identified;
- calibrated;
- optimized;
- assumed.

### Layer G — Model verification

Model verification is a first-class module.

It covers five independent questions:

1. **numerical validity** — convergence, tolerance, discretization, solver behavior;
2. **parameter robustness** — sensitivity and uncertainty;
3. **scenario robustness** — disturbances, boundary cases, stress conditions;
4. **structural robustness** — materially different model formulations;
5. **algorithm/solver robustness** — different valid numerical methods on the same mathematical model.

Multi-model comparison is a mandatory **review decision**, not a mandatory wasteful second model. Every material result must explicitly record either:

- `required`: execute a meaningful structural comparator; or
- `not_applicable`: give a technical reason why a second model would not test a material claim.

A changed solver is not a changed model. A changed parameter value is not a changed model. A structural comparator must change mathematical structure, mechanism, abstraction or fidelity while preserving a common evaluation target.

### Layer H — Verification & validation

Separate:

- verification: did we solve/build the intended model correctly?
- validation: is the model adequate for the real/target system and intended claims?

Evidence may include:

- analytic limiting cases;
- conservation/invariant checks;
- dimensional consistency;
- benchmark model comparison;
- experimental/reference data;
- subsystem tests;
- Simulink Test;
- coverage;
- Design Verifier;
- fault injection;
- physical plausibility constraints.

### Layer I — Evidence & visualization

Figures are evidence, not decoration.

Plots must be sourced from accepted simulation/analysis outputs and should support a concrete claim such as:

- transient response;
- phase/state trajectory;
- convergence;
- residual/error;
- sensitivity;
- uncertainty distribution;
- Pareto/frontier;
- threshold/event;
- model comparison;
- solver profile;
- parameter identifiability;
- validation agreement.

### Layer J — Paper/report delivery

This repository owns the simulation-specific evidence contract:

`MODEL → SIMULATION SETUP → SOLVE/RUN → RESULT → VERIFY → VALIDATE → CLAIM`

The mature general paper-writing authority remains in `Vexushi1/mathmodel-skill`.

Default strategy:

1. this repository produces a simulation evidence package and writing handoff;
2. if `mathmodel-skill` paper-writing capability is available, delegate full paper composition to it;
3. do not clone the whole paper-writing subsystem into this repository by default;
4. vendor a controlled snapshot only if independent operation becomes a hard requirement.

## 4. Key invariants

- Problem semantics cannot be rewritten to fit convenient Simulink blocks.
- Simulink block names are implementation details, not mathematical model names.
- Solver names cannot replace model identity.
- A successful simulation is not validation.
- A visually plausible waveform is not numerical verification.
- Sensitivity analysis cannot substitute for structural model comparison.
- Structural comparison cannot substitute for experimental/reference validation.
- Performance claims require reproducible runtime context.
- Paper claims cannot exceed accepted evidence.

## 5. Upstream strategy

### Official first

Prefer MathWorks official Agentic Toolkits whenever they provide the required capability.

### No blind vendoring

Do not bulk-copy upstream `SKILL.md` files. This avoids:

- semantic drift;
- duplicate routing;
- stale API guidance;
- license ambiguity;
- maintenance duplication.

### Adapter model

Local adapters may specify:

- trigger conditions;
- required inputs;
- compatibility checks;
- expected outputs;
- evidence handoff;
- fallback route.

They should not duplicate upstream implementation instructions unless a verified gap requires a local extension.

## 6. Release goal

v1.0.0 is reached only when:

- R2025b baseline is executable and validated;
- routing covers the main simulation competition task classes;
- a model can progress from audited problem to validated paper evidence;
- failure and fallback behavior are explicit;
- representative end-to-end regression cases pass;
- repository semantics and version references are internally consistent.
