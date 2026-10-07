# v1.0.0 Implementation Roadmap

> Summary of [V1_FULL_IMPLEMENTATION_PLAN.md](V1_FULL_IMPLEMENTATION_PLAN.md), the sole detailed implementation authority. Version 0.1.1 implements Phase A infrastructure and is pending independent PR qualification; Phases B–K remain deferred.

## Phase A — Runtime, governance, and trusted root

Build bootstrap and core contracts, operation-specific capability evidence, inspection and assurance routing, project state validation, output receipts, reproducible indexes, lint, tests, and static CI. Baseline products are candidates; Statistics and Machine Learning Toolbox has no permanent historical quarantine.

Environment evidence comes from a current repository probe. Its scope covers MATLAB basic calls, Simulink library loading, and optional Statistics minimum operations. It does not qualify business simulation, Toolkit composition, or end-to-end modeling. `selected` is a route decision; deferred capabilities cannot be activated.

The four exit gates are:

- `runtime_assured = true`;
- `authority_graph_valid = true`;
- `capability_profile_current = true`;
- `router_smoke_test = passed`.

Use evidence from the final source version. Formal stage completion also requires independent PR review, corresponding CI, and post-merge read-back. Declare any unmerged bootstrap dependency in a stacked Phase A PR. A local test success, draft PR, or capability declaration does not complete this gate.

## Later phases — deferred

| Phase | Planned scope |
|---|---|
| B | Simulation requirement audit, system boundaries, data roles, dependency DAG, and frozen Problem Contract |
| C | Model and fidelity selection, supported alternative routes, challenge, and human model approval |
| D | Approved mathematical model mapping and qualified official execution adapters |
| E | Solver decisions, frozen simulation protocol, reproducible execution, and run receipts |
| F | Parameter provenance, identification, calibration, and optimization when required |
| G | Experiment design, campaigns, uncertainty sampling, and parallel simulation |
| H | Primary numerical verification, sensitivity/robustness decisions, and structural/solver comparison |
| I | Verification and claim-scoped validation, including applicable test and safety tools |
| J | Accepted figures, result-to-claim trace, evidence package, and paper handoff |
| K | Full semantic audit, representative R2025b end-to-end qualification, and release review |

Develop phases in the full plan's order and refine each phase's executable gates before starting it. This development sequence is separate from a single project's runtime state: identification, optimization, and advanced analyses are conditional on the task and material claims, with technical decisions and limitations recorded. Alternative model routes have no fixed count; structural comparison retains its `required` / `not_applicable` decision.

## Release

The v1.0.0 gate remains the full plan's release definition: all phases qualified and merged, complete active indexes and CI, current upstream compatibility, representative R2025b runtime evidence, accepted evidence and claim boundaries, and verified paper handoff. Version 0.1.1 does not claim that release gate.
