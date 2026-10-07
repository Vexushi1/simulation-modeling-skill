# v1.0.0 Implementation Roadmap

> Summary of [V1_FULL_IMPLEMENTATION_PLAN.md](V1_FULL_IMPLEMENTATION_PLAN.md), the sole detailed implementation authority. Version 0.2.0 implements Phase B problem-audit infrastructure on the merged Phase A base. Phases C–K remain deferred; qualification and merge evidence are recorded separately in the development PR.

## Phase A — Runtime, governance, and trusted root

Phase A implements bootstrap and core contracts, operation-specific capability evidence, inspection and assurance routing, project state validation, output receipts, reproducible indexes, lint, tests, and static CI. Its PRs are merged, with final-source qualification and post-merge read-back recorded in the full plan §0.4. Baseline products are candidates; Statistics and Machine Learning Toolbox has no permanent historical quarantine.

Environment evidence comes from a current repository probe. Its scope covers MATLAB basic calls, Simulink library loading, and optional Statistics minimum operations. It does not qualify business simulation, Toolkit composition, or end-to-end modeling. `selected` is a route decision; deferred capabilities cannot be activated.

The four exit gates are:

- `runtime_assured = true`;
- `authority_graph_valid = true`;
- `capability_profile_current = true`;
- `router_smoke_test = passed`.

These development exit gates do not grant permanent runtime readiness. Each runtime route still validates its current operation evidence and source identity. Preserve the Phase A behavior while adding Phase B; a local test success, draft PR, or capability declaration alone does not establish formal completion of a later stage.

## Phase B — Problem audit and requirement freeze

The current implementation adds the [problem-audit module](../modules/01_problem_audit.md), [Problem Contract schema](../core/problem_contract.schema.yaml), draft template, validator, and source-backed fixtures, and connects them to bootstrap, router, state, output, lint, and indexes. It leaves Phase A's probe and qualification contracts unchanged.

Audit binds original materials and review text, literal coverage and requirement references, question facts, variable/data roles and ranges, an acyclic question dependency graph, and critical ambiguities. B freezes supplied task meaning; model-dependent choices and formal model approval belong to Phase C. Text review and read-only validation can start from `NEW` without a capability profile.

The validator distinguishes legal structure, applicable validity, audit completion, readiness to freeze, and a frozen contract with a current review decision. Freeze records the semantic digest and exact source-bound decision. Use existing task authorization when sufficient, and obtain necessary missing material decisions; no repeated per-question approval is required. Repository development authorization does not freeze a real task or approve its model. Validators and the resolver never perform an automatic state transition.

The five development exit checks in the full plan §6.10 are:

- `problem_contract_checks = passed`;
- `problem_audit_route_smoke = passed`;
- `project_state_problem_binding = passed`;
- `source_and_stale_checks = passed`;
- `authority_and_indexes = passed`.

Verify legal draft, audited, and frozen paths as well as changed or missing materials, invalid offsets/references/coverage, unverified extraction, inconsistent roles/ranges, invalid dependencies, unresolved critical ambiguities, mismatching decisions or project identities, path escapes, and stale dependents. Confirm that environment expiry does not block unchanged text audit, routes never write state, and C–K remain deferred. Run the Phase A regressions and independent original-material review.

Passing synthetic fixtures qualifies the B infrastructure's behavior. Formal development completion separately requires independent PR review, final-source CI, merge, and read-back. A user's project must independently meet its actual Problem Contract Gate. Problem evidence tracks material and decision changes; runtime TTL alone does not expire unchanged problem meaning.

## Later phases — deferred

| Phase | Planned scope |
|---|---|
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

The v1.0.0 gate remains the full plan's release definition: all phases qualified and merged, complete active indexes and CI, current upstream compatibility, representative R2025b runtime evidence, accepted evidence and claim boundaries, and verified paper handoff. Version 0.2.0 does not claim that release gate.
