# Canonical Architecture — Simulation Modeling Skill

> Scope: v0.2.0 Phase B implementation, based on merged Phase A infrastructure
> Primary runtime baseline: MATLAB R2025b + Simulink  
> Target: competition-oriented simulation modeling with engineering-grade reproducibility and paper-ready evidence.

[V1_FULL_IMPLEMENTATION_PLAN.md](V1_FULL_IMPLEMENTATION_PLAN.md) is the detailed development authority. [V1_IMPLEMENTATION_ROADMAP.md](V1_IMPLEMENTATION_ROADMAP.md) summarizes it. This architecture describes the target layers; the active contracts begin at [../core/bootstrap.yaml](../core/bootstrap.yaml).

Current implementation covers environment inspection and assurance, and problem audit. Layers C–J below are deferred targets; the full plan's Phases C–K remain deferred. A declared layer, toolbox, or future project state cannot be activated by the current router. Repository development gates and a user's project states are distinct. Phase A's merged qualification is recorded in the full plan; later qualification, CI, merge, and release results are recorded separately in their development PRs.

## 1. Scope

This repository is a **simulation-modeling methodology and orchestration layer**.

The v1 target owns:

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
- Simulink version series: **25.2**
- Platform-specific behavior must be discovered at runtime rather than inferred from documentation alone.

Older MATLAB releases are not a release target for v1.0. Upstream MathWorks skills may support older releases, but this repository optimizes behavior, examples and validation for R2025b.

## 3. Layered architecture

### Layer A — Runtime & capability assurance (Phase A infrastructure)

The environment assurance route:

- confirm MATLAB release;
- detect installed products;
- distinguish declared products, inventory, license tests, resolution, callable operations, qualified operation assertions, and route selection;
- record unavailable or contradictory capabilities;
- validate current profile, receipt, raw report, process result, and source/runtime bindings against the runtime assurance contract.

The baseline declares targets and candidates, not current availability. Qualification is operation-specific and limited to the repository probe's inputs and assertions. Simulink library loading does not qualify simulation execution. Statistics is a normal optional candidate; optional failure does not invalidate a route needing only qualified core operations. The contract defines profile freshness and invalidation; historical evidence is preserved.

Read-only inspection needs no existing profile and does not advance a project state. Selected operations belong to the current route decision. The resolver never updates project state automatically. No missing downstream module or unqualified upstream composition may be activated as a fallback.

### Layer B — Problem audit & requirement freeze (Phase B infrastructure)

The active [problem-audit module](../modules/01_problem_audit.md) and [Problem Contract schema](../core/problem_contract.schema.yaml) adapt requirement review to simulation-specific semantics. A contract binds original materials and UTF-8 review text, a literal requirement map, question facts, variable/data roles, a dependency DAG, and critical ambiguities. Non-text statement extractions require a current review record.

Every subproblem explicitly identifies its original system, direct goal, and deliverables. Other required categories distinguish `specified`, `not_specified`, `not_applicable`, and `deferred`, with reasons and requirement references. Given facts cannot be deferred to bypass ambiguity. Abstraction, state representation, algebraic variables, derived parameters, and event representation that depend on model design can remain deferred to Phase C; candidate model clues do not lock a model.

Literal audit units use exact quotes and Unicode codepoint intervals, cover every non-whitespace character once, and connect requirements bidirectionally to their source and question. Variables can have related roles when that relationship is explicit. Data uses bind sources and ranges; fitting data cannot be presented as independent validation of the same range. Cross-question dependencies must reference known nodes and remain acyclic; future expected artefacts need not already exist.

The validator separately reports `schema_valid`, `valid`, `audit_complete`, `freeze_ready`, and `frozen`. A draft's legal shape does not establish audit completion. Freeze requires closed critical ambiguities and a source-bound review decision identifying the current semantic digest. The decision follows the actual task authorization and necessary material choices; repeated per-question approval is not required. Development authorization does not answer a competition task or approve its model.

The `problem_audit` route is read-only, selects no runtime operations, and can start from `NEW` without an environment profile. It cannot grant numerical execution. State recording is a separate explicit caller update: `PROBLEM_AUDITED` requires the current audit-complete contract declared `audited` or `frozen`, and `PROBLEM_FROZEN` requires the current frozen contract with matching project identity. Problem-scoped validation leaves runtime readiness unassessed.

Problem evidence and accepted dependents become stale when their actual contract, material, extraction review, or decision identities change. Environment expiry does not expire unchanged problem meaning. Mechanical coverage and traceability do not prove semantic interpretation or real-system validity. Formal model design and Simulink implementation remain deferred.

### Layer C — System & model design (deferred)

Maintain strict role separation:

- **Model**: mathematical/physical representation;
- **Solver**: numerical integration, optimization or search method;
- **Validator**: independent evidence used to assess the model/solution.

For each material subproblem, propose a minimally sufficient main route and review 0..N alternatives supported by mechanism, data, and computational budget. Classical and advanced approaches are candidate types, not a fixed quota. Record a technical reason when no useful alternative exists; the later structural-comparison decision governs actual comparator execution.

Model selection must justify:

- required mechanisms;
- fidelity level;
- identifiability;
- data support;
- computational feasibility;
- expected failure modes.

### Layer D — Execution adapter (deferred)

Use upstream capabilities instead of copying their implementation rules.

Primary upstream:

- `matlab/simulink-agentic-toolkit`
- `matlab/matlab-agentic-toolkit`

Supplementary specialized skills may be used after explicit compatibility review.

The local repository owns routing and competition methodology; upstream skills own low-level implementation behavior such as model editing, simulation, testing and supported toolbox workflows.

### Layer E — Simulation experiment design (deferred)

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

### Layer F — Calibration, identification & optimization (deferred)

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

These are provenance roles, not a universal credibility ranking. Judge suitability from the parameter's role, object, conditions, units, data quality, identifiability, uncertainty, and independent validation. Trial/calibration runs are not accepted primary evidence; final parameters require a frozen final protocol, a new run, and numerical verification.

### Layer G — Model verification (deferred)

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

### Layer H — Verification & validation (deferred)

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

Each validation decision must identify its target, independent reference, applicable conditions, metric, and claim boundary. Structural agreement, coverage, physical plausibility, and successful simulation do not automatically establish real-system validity. Task-dependent analyses require a decision and technical reason when not required, rather than fabricated evidence.

### Layer I — Evidence & visualization (deferred)

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

### Layer J — Paper/report delivery (deferred)

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
- Phase A–K gates, independent PR review, CI, and post-merge evidence are complete;
- repository semantics and version references are internally consistent.
