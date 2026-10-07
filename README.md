# Simulation Modeling Skill

Competition simulation methodology and evidence orchestration for **MATLAB R2025b + Simulink 25.2**.

Version **0.2.0** adds Phase B problem-audit infrastructure to the merged Phase A environment infrastructure. Local checks, CI, independent review, merge, and release are separate results recorded in the relevant development PR.

## Current behavior

Start from [SKILL.md](SKILL.md) and [core/bootstrap.yaml](core/bootstrap.yaml). Active routes support environment inspection and assurance, and [problem audit](modules/01_problem_audit.md). Model design and the implementation, simulation, verification, and paper workflows in Phases C–K remain deferred.

Problem audit binds the original materials and review text, maps literal requirements, records variable and data roles, and checks the question dependency graph. The [Problem Contract](core/problem_contract.schema.yaml) distinguishes a legal draft, an audit-complete result, readiness to freeze, and a frozen contract with a current review decision. Text review and validation need no MATLAB profile. A freeze decision follows the actual task authorization and resolution of critical ambiguities; it does not require separate repeated approval of every question. Validators and the resolver do not freeze a contract or write project state.

Problem evidence depends on its current sources and review decision. Source changes invalidate its actual dependents; runtime expiry does not expire unchanged task meaning. A frozen problem does not approve a model or grant numerical execution.

The [environment baseline](core/environment_baseline.yaml) declares the strong runtime target and candidate products. Current availability comes from a repository probe, with each operation's inputs, assertions, runtime, channel, raw report, receipt, logs, and process result. A product inventory or license flag is insufficient. Loading the Simulink library does not qualify a business simulation.

Probe only the operations needed for the request. Statistics and Machine Learning Toolbox is a normal optional candidate; successful current probes can qualify its tested operations. Optional failures are reported with a fallback and do not block a route that requires only the qualified core operations.

For local development commands and a fresh qualification run, see [AGENTS.md](AGENTS.md). Install the Python tooling dependencies from [requirements.txt](requirements.txt) in the chosen development environment. A MATLAB batch probe is transparent about its execution channel and does not establish an MCP connection.

## Authority and development

The [full implementation plan](docs/V1_FULL_IMPLEMENTATION_PLAN.md) is the sole detailed development authority. The [roadmap](docs/V1_IMPLEMENTATION_ROADMAP.md) summarizes it; the [canonical architecture](docs/CANONICAL_ARCHITECTURE.md) explains ownership and target layers. Read the full plan, [governance](DEVELOPMENT_GOVERNANCE.md), and affected contracts before changing active behavior.

Development Phase A–K gates are distinct from a user's project states. Phase A's merged qualification is recorded in the full plan; each new runtime request still requires appropriate current operation evidence. Phase B's exit requires its contract, route, state-binding, source/stale, and authority/index checks, followed by independent review, final CI, and post-merge read-back. Passing repository fixtures does not freeze another task or approve its model. Later phases cannot be activated because they appear in the taxonomy or target architecture.

## v1 target and integrations

The target workflow continues from requirement freezing to system and model design, implementation, simulation protocols, identification or optimization when needed, numerical verification, model comparison decisions, validation, and scientific evidence for paper handoff. The stages after problem audit are planned, not active in 0.2.0.

This repository owns competition methodology, routing, evidence, and claim boundaries. Future execution adapters prefer `matlab/simulink-agentic-toolkit` and `matlab/matlab-agentic-toolkit`, subject to operation and composition qualification. `Vexushi1/mathmodel-skill` is a methodology and paper-writing reference, not a core runtime dependency. Integration ownership and admission rules live in [core/upstream_integration_policy.md](core/upstream_integration_policy.md).
