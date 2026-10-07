# Simulation Modeling Skill

Competition simulation methodology and evidence orchestration for **MATLAB R2025b + Simulink 25.2**.

Version **0.3.0** adds Phase C text model design, challenge, and human approval checks to the merged Phase A/B infrastructure. Local checks, CI, independent review, merge, and release are separate results recorded in the relevant development PR.

## Current behavior

Start from [SKILL.md](SKILL.md) and [core/bootstrap.yaml](core/bootstrap.yaml). Active routes support environment inspection and assurance, [problem audit](modules/01_problem_audit.md), and [text model design](modules/02_model_design.md). Implementation, simulation, numerical verification, and paper workflows in Phases D–K remain deferred.

Problem audit binds the original materials and review text, maps literal requirements, records variable and data roles, and checks the question dependency graph. The [Problem Contract](core/problem_contract.schema.yaml) distinguishes a legal draft, an audit-complete result, readiness to freeze, and a frozen contract with a current review decision. Text review and validation need no MATLAB profile. A freeze decision follows the actual task authorization and resolution of critical ambiguities; it does not require separate repeated approval of every question. Validators and the resolver do not freeze a contract or write project state.

Problem evidence depends on its current sources and review decision. Source changes invalidate its actual dependents; runtime expiry does not expire unchanged task meaning. A frozen problem does not approve a model or grant numerical execution.

The [Model Contract](core/model_contract.schema.yaml) binds the current frozen Problem, design sources, mathematical structures, contextual fidelity, 0..N justified alternatives, four structural reviews, nine challenges, and an Approval Brief. Shared models can cover several questions. Unknown parameter values remain unknown; future estimation and validation plans do not become completed numerical evidence.

The [Model Approval contract](core/model_approval_contract.yaml) requires an actual human decision on the current design and Brief, with current project/Problem/design bindings and a matching locked specification. Structural model IDs are separate from full-design digests: changing a solver or parameter value does not create another mathematical model, but can invalidate the prior design approval. A legal draft, a complete proposal, completed challenges, readiness, and actual approval are distinct checks. Validators verify recorded consistency without proving mathematical truth or authenticating an invented human action.

Structural digests identify registered expressions and do not prove symbolic equivalence. Equivalent rewritten equations or renamed variables can change a digest; a meaningful structural comparator still requires review of actual mechanisms, abstraction, or mathematical differences.

Text design requires no runtime profile. Model-scoped state validation checks B/C and reports environment readiness as unassessed; problem-scoped validation does not assess the model. Validators and routing never write approvals, locked specifications, or state. Model approval does not activate Phases D–K or qualify numerical execution.

Phase C conservatively binds the entire Problem and its current source evidence. Changed statements, attachments, Briefs, decisions, or locked files invalidate the relevant bindings and accepted dependents. It does not claim fine-grained source impact analysis. Runtime expiry alone does not invalidate unchanged text design.

The [environment baseline](core/environment_baseline.yaml) declares the strong runtime target and candidate products. Current availability comes from a repository probe, with each operation's inputs, assertions, runtime, channel, raw report, receipt, logs, and process result. A product inventory or license flag is insufficient. Loading the Simulink library does not qualify a business simulation.

Probe only the operations needed for the request. Statistics and Machine Learning Toolbox is a normal optional candidate; successful current probes can qualify its tested operations. Optional failures are reported with a fallback and do not block a route that requires only the qualified core operations.

For local development commands and a fresh qualification run, see [AGENTS.md](AGENTS.md). Install the Python tooling dependencies from [requirements.txt](requirements.txt) in the chosen development environment. A MATLAB batch probe is transparent about its execution channel and does not establish an MCP connection.

## Authority and development

The [full implementation plan](docs/V1_FULL_IMPLEMENTATION_PLAN.md) is the sole detailed development authority. The [roadmap](docs/V1_IMPLEMENTATION_ROADMAP.md) summarizes it; the [canonical architecture](docs/CANONICAL_ARCHITECTURE.md) explains ownership and target layers. Read the full plan, [governance](DEVELOPMENT_GOVERNANCE.md), and affected contracts before changing active behavior.

Development Phase A–K gates are distinct from a user's project states. Phase A/B's merged qualification is recorded in the full plan; each new runtime request still requires appropriate current operation evidence. Phase C's exit requires its contract, human approval binding, route/state, source/stale, and authority/index checks, followed by independent original-material review, final CI, merge, and post-merge read-back. Passing repository fixtures does not freeze another task or approve its model. Later phases cannot be activated because they appear in the taxonomy or target architecture.

## v1 target and integrations

The target workflow continues from text model design and approval to implementation, simulation protocols, identification or optimization when needed, numerical verification, model comparison decisions, validation, and scientific evidence for paper handoff. The stages after model approval are planned, not active in 0.3.0.

This repository owns competition methodology, routing, evidence, and claim boundaries. Future execution adapters prefer `matlab/simulink-agentic-toolkit` and `matlab/matlab-agentic-toolkit`, subject to operation and composition qualification. `Vexushi1/mathmodel-skill` is a methodology and paper-writing reference, not a core runtime dependency. Integration ownership and admission rules live in [core/upstream_integration_policy.md](core/upstream_integration_policy.md).
