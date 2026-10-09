# Simulation Modeling Skill

Competition simulation methodology and evidence orchestration for **MATLAB R2025b + Simulink 25.2**.

Version **0.7.0** adds reviewed finite serial scenario, factorial and categorical catalog experiments to A–F. Every selected draw executes a complete independently frozen E protocol in a fresh directory. Local checks, actual MATLAB qualification, CI, independent review, merge and release are separate results recorded in the relevant development PR.

## Current behavior

Start from [SKILL.md](SKILL.md) and [core/bootstrap.yaml](core/bootstrap.yaml). Active routes support environment inspection and assurance, [problem audit](modules/01_problem_audit.md), [text model design](modules/02_model_design.md), [approved mapping and core construction](modules/03_domain_mapping.md), [frozen protocols and core simulation](modules/04_simulation_protocol.md), bounded [parameter studies](modules/05_identification_calibration_optimization.md) and [finite serial experiments](modules/06_experiment_design.md). Advanced domains, numerical V&V and paper workflows in Phases H–K remain deferred. General parameter overrides, continuous Monte Carlo, LHS and parallel simulation remain deferred.

Problem audit binds the original materials and review text, maps literal requirements, records variable and data roles, and checks the question dependency graph. The [Problem Contract](core/problem_contract.schema.yaml) distinguishes a legal draft, an audit-complete result, readiness to freeze, and a frozen contract with a current review decision. Text review and validation need no MATLAB profile. A freeze decision follows the actual task authorization and resolution of critical ambiguities; it does not require separate repeated approval of every question. Validators and the resolver do not freeze a contract or write project state.

Problem evidence depends on its current sources and review decision. Source changes invalidate its actual dependents; runtime expiry does not expire unchanged task meaning. A frozen problem does not approve a model or grant numerical execution.

The [Model Contract](core/model_contract.schema.yaml) binds the current frozen Problem, design sources, mathematical structures, contextual fidelity, 0..N justified alternatives, four structural reviews, nine challenges, and an Approval Brief. Shared models can cover several questions. Unknown parameter values remain unknown; future estimation and validation plans do not become completed numerical evidence.

The [Model Approval contract](core/model_approval_contract.yaml) requires an actual human decision on the current design and Brief, with current project/Problem/design bindings and a matching locked specification. Structural model IDs are separate from full-design digests: changing a solver or parameter value does not create another mathematical model, but can invalidate the prior design approval. A legal draft, a complete proposal, completed challenges, readiness, and actual approval are distinct checks. Validators verify recorded consistency without proving mathematical truth or authenticating an invented human action.

Structural digests identify registered expressions and do not prove symbolic equivalence. Equivalent rewritten equations or renamed variables can change a digest; a meaningful structural comparator still requires review of actual mechanisms, abstraction, or mathematical differences.

Text design requires no runtime profile. Model-scoped state validation checks B/C and reports environment readiness as unassessed; problem-scoped validation does not assess the model. Validators and routing never write approvals, locked specifications, or state. Model approval is required for formal D mapping but does not qualify native mutation or numerical execution. Simscape/Stateflow/System Composer construction and Phases H–K remain deferred.

Phase C conservatively binds the entire Problem and its current source evidence. Changed statements, attachments, Briefs, decisions, or locked files invalidate the relevant bindings and accepted dependents. It does not claim fine-grained source impact analysis. Runtime expiry alone does not invalidate unchanged text design.

The [environment baseline](core/environment_baseline.yaml) declares the strong runtime target and candidate products. Current availability comes from a repository probe, with each operation's inputs, assertions, runtime, channel, raw report, receipt, logs, and process result. A product inventory or license flag is insufficient. Loading the Simulink library does not qualify a business simulation.

Probe only the operations needed for the request. Statistics and Machine Learning Toolbox is a normal optional candidate; successful current probes can qualify its tested operations. Optional failures are reported with a fallback and do not block a route that requires only the qualified core operations.

For local development commands and a fresh qualification run, see [AGENTS.md](AGENTS.md). Install the Python tooling dependencies from [requirements.txt](requirements.txt) in the chosen development environment. A MATLAB batch probe is transparent about its execution channel and does not establish an MCP connection.

## Authority and development

The [full implementation plan](docs/V1_FULL_IMPLEMENTATION_PLAN.md) is the sole detailed development authority. The [roadmap](docs/V1_IMPLEMENTATION_ROADMAP.md) summarizes it; the [canonical architecture](docs/CANONICAL_ARCHITECTURE.md) explains ownership and target layers. Read the full plan, [governance](DEVELOPMENT_GOVERNANCE.md), and affected contracts before changing active behavior.

Development Phase A–K gates are distinct from a user's project states. Phase A/B/C are merged; each new runtime request still requires appropriate current operation evidence. D's exit requires mapping/parameter checks, native operation qualification, route/state/source/stale/adapter/authority checks, all earlier regressions, independent original-material review, final CI, merge, and post-merge read-back. Passing repository fixtures does not freeze another task or approve its model. Later phases cannot be activated because they appear in the taxonomy or target architecture.

## v1 target and integrations

The target workflow continues from text model design and approval to implementation, simulation protocols, identification or optimization when needed, experiments, numerical verification, model comparison decisions, validation and scientific evidence for paper handoff. A–G infrastructure is active in 0.7.0 within the declared method boundaries; numerical V&V and subsequent stages remain planned.

This repository owns competition methodology, routing, evidence, and claim boundaries. Execution adapters prefer `matlab/simulink-agentic-toolkit` and `matlab/matlab-agentic-toolkit`, subject to operation and composition qualification. `Vexushi1/mathmodel-skill` is a methodology and paper-writing reference, not a core runtime dependency. Integration ownership and admission rules live in [core/upstream_integration_policy.md](core/upstream_integration_policy.md).

## Approved-model mapping and core construction

Read [the D module](modules/03_domain_mapping.md), [mapping schema](core/domain_mapping.schema.yaml), [parameter schema](core/parameter_provenance.schema.yaml), and [implementation assurance contract](core/implementation_assurance_contract.yaml). Current C human approval is required for formal mapping. Exact approved values/units/provenance are preserved, with unknown parameters blocking only native operations that need them. Mapping and parameter validators remain read-only.

The local constructor accepts explicit reviewed Inport/Outport/Constant/Gain/Sum/Integrator instructions and model-file workspace bindings. New construction requires current A and independent D operation profiles and produces actual saved/reopened SLX and structure receipts. Library loading and installed toolboxes do not qualify it. Other blocks and Simscape/Stateflow/System Composer construction require future operation qualifications. Historical structure freshness binds actual sources, input semantics, producer code and model bytes; current environment TTL controls new execution.

An explicit caller alone can bind successful receipts and set IMPLEMENTATION_READY. Implementation-scoped state checks B/C/D while leaving current runtime unassessed. Structural consistency grants no simulation, mathematical equivalence, physical validity, or numerical V&V. The [MathWorks adapter](adapters/mathworks/simulink_agentic_toolkit.md) records pinned official resource compatibility without claiming they are installed.

## Frozen protocols and reviewed primary runs

Read [the E module](modules/04_simulation_protocol.md), [protocol schema](core/simulation_protocol.schema.yaml) and [simulation assurance](core/simulation_assurance_contract.yaml). Only a complete current frozen protocol with valid B/C/D bindings and current same-runtime A/E qualification can run. Parameters and approved initial/boundary conditions remain exact; scenario inputs bind reviewed structured sources. Each solver is qualified independently. Process exit 0 cannot replace complete finite outputs, expected termination, warnings review and prior metrics. Actual MAT v7, JSON and CSV numeric fields are cross-checked. Only explicit callers register receipts and PRIMARY_RUN_COMPLETE; numerical verification and real-system validation remain later gates.

`--include-statistics` expands optional diagnostics; it does not make Statistics operations mandatory. If a model needs fitlm, lhsdesign or normcdf, explicitly require the corresponding operation and inspect its actual result. E propagates its frozen protocol requirements into execution gates. See [operation qualification commands and result interpretation](docs/OPERATION_QUALIFICATION.md).

## Phase F — Optional reviewed parameter studies

The detailed Authority is the full plan §10.8–10.13. Read [the F module](modules/05_identification_calibration_optimization.md). A source-bound study records the selected current approved C mathematics, parameter provenance, numeric bounds and initialization sources, observation roles and half-open train/holdout ranges where applicable, loss, budgets, warning and acceptance rules. A separate semantic review authorizes bounded candidate trials. Unknown C values remain null; given/derived constants cannot silently become search variables.

Three operations are conditional: dense uniformly sampled SISO ARX [1 1 1] with one-step holdout prediction; bounded single-gain Simulink least squares with an actual owned model per objective evaluation; and bounded one/two-variable positive quadratic SQP with explicit linear inequalities. New execution requires current same-runtime A/F operation evidence and the union of actual required A operations. Gain trials also require current E ode4 evidence. Neither toolbox installation nor core environment success qualifies a method. Pure design optimization invents no observations or holdout data.

The separate trial ledger, raw/process evidence and cross-checked MAT/JSON candidate outputs establish a candidate within the reviewed criteria. They never overwrite C/D/E evidence, advance state, adopt parameters or prove physical validity or a general global optimum. Adoption returns to new actual C human approval, then new D/E evidence and later H verification. PARAMETER_STUDY_REVIEWED and PARAMETER_CANDIDATE_COMPLETE form an optional branch; the `parameter_study` scope assesses B/C/F history without current runtime or D/E readiness. Earlier partial scopes leave F unassessed. Repository qualification, independent review, CI and merge remain separate development evidence.
