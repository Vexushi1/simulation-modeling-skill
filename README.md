# Simulation Modeling Skill

Competition simulation methodology and evidence orchestration for **MATLAB R2025b + Simulink 25.2**.

Version **0.1.1** is an unreleased Phase A infrastructure implementation. Independent PR review, CI, merge, and release are separate qualification steps; this status does not claim they have completed.

## Current behavior

Start from [SKILL.md](SKILL.md) and [core/bootstrap.yaml](core/bootstrap.yaml). Phase A supports read-only environment inspection and evidence-based environment assurance. Business modeling and simulation workflows in Phases B–K remain deferred, and the router cannot activate their missing modules or upstream skills.

The [environment baseline](core/environment_baseline.yaml) declares the strong runtime target and candidate products. Current availability comes from a repository probe, with each operation's inputs, assertions, runtime, channel, raw report, receipt, logs, and process result. A product inventory or license flag is insufficient. Loading the Simulink library does not qualify a business simulation.

Probe only the operations needed for the request. Statistics and Machine Learning Toolbox is a normal optional candidate; successful current probes can qualify its tested operations. Optional failures are reported with a fallback and do not block a route that requires only the qualified core operations.

For local development commands and a fresh qualification run, see [AGENTS.md](AGENTS.md). Install the Python tooling dependencies from [requirements.txt](requirements.txt) in the chosen development environment. A MATLAB batch probe is transparent about its execution channel and does not establish an MCP connection.

## Authority and development

The [full implementation plan](docs/V1_FULL_IMPLEMENTATION_PLAN.md) is the sole detailed development authority. The [roadmap](docs/V1_IMPLEMENTATION_ROADMAP.md) summarizes it; the [canonical architecture](docs/CANONICAL_ARCHITECTURE.md) explains ownership and target layers. Read the full plan, [governance](DEVELOPMENT_GOVERNANCE.md), and affected contracts before changing active behavior.

Development Phase A–K gates are distinct from a user's project states. Formal Phase A completion requires its four gates, evidence from the final source version, independent PR review, CI, and post-merge read-back. Later phases cannot be declared implemented because they appear in the taxonomy or target architecture.

## v1 target and integrations

The target workflow covers requirement freezing, system and model design, implementation, simulation protocols, identification or optimization when needed, numerical verification, model comparison decisions, validation, and scientific evidence for paper handoff. Those business capabilities are planned, not active in 0.1.1.

This repository owns competition methodology, routing, evidence, and claim boundaries. Future execution adapters prefer `matlab/simulink-agentic-toolkit` and `matlab/matlab-agentic-toolkit`, subject to operation and composition qualification. `Vexushi1/mathmodel-skill` is a methodology and paper-writing reference, not a core runtime dependency. Integration ownership and admission rules live in [core/upstream_integration_policy.md](core/upstream_integration_policy.md).
