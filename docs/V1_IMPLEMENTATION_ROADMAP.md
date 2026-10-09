# v1.0.0 Implementation Roadmap

> Summary of [V1_FULL_IMPLEMENTATION_PLAN.md](V1_FULL_IMPLEMENTATION_PLAN.md), the sole detailed implementation authority. Version 0.8.0 adds finite historical Phase H verification to A–G. Other D domains, general parameter sweeps, continuous Monte Carlo, LHS, parallelism and advanced H and Phases I–K remain deferred; qualification and merge evidence are recorded separately in the development PR.

## Phase A — Runtime, governance, and trusted root

Phase A implements bootstrap and core contracts, operation-specific capability evidence, inspection and assurance routing, project state validation, output receipts, reproducible indexes, lint, tests, and static CI. Its PRs are merged, with final-source qualification and post-merge read-back recorded in the full plan §0.4. Baseline products are candidates; Statistics and Machine Learning Toolbox has no permanent historical quarantine.

Environment evidence comes from a current repository probe. Its scope covers MATLAB basic calls, Simulink library loading, and optional Statistics minimum operations. It does not qualify business simulation, Toolkit composition, or end-to-end modeling. `selected` is a route decision; deferred capabilities cannot be activated.

The four exit gates are:

- `runtime_assured = true`;
- `authority_graph_valid = true`;
- `capability_profile_current = true`;
- `router_smoke_test = passed`.

These development exit gates do not grant permanent runtime readiness. Each runtime route still validates its current operation evidence and source identity. Preserve the Phase A behavior while adding later phases; a local test success, draft PR, or capability declaration alone does not establish formal completion of a later stage.

## Phase B — Problem audit and requirement freeze

The merged Phase B adds the [problem-audit module](../modules/01_problem_audit.md), [Problem Contract schema](../core/problem_contract.schema.yaml), draft template, validator, and source-backed fixtures, and connects them to bootstrap, router, state, output, lint, and indexes. It leaves Phase A's probe and qualification contracts unchanged. Final-source and post-merge CI, independent review, and original-material trial evidence are recorded in the full plan.

Audit binds original materials and review text, literal coverage and requirement references, question facts, variable/data roles and ranges, an acyclic question dependency graph, and critical ambiguities. B freezes supplied task meaning; model-dependent choices and formal model approval belong to Phase C. Text review and read-only validation can start from `NEW` without a capability profile.

The validator distinguishes legal structure, applicable validity, audit completion, readiness to freeze, and a frozen contract with a current review decision. Freeze records the semantic digest and exact source-bound decision. Use existing task authorization when sufficient, and obtain necessary missing material decisions; no repeated per-question approval is required. Repository development authorization does not freeze a real task or approve its model. Validators and the resolver never perform an automatic state transition.

The five development exit checks in the full plan §6.10 are:

- `problem_contract_checks = passed`;
- `problem_audit_route_smoke = passed`;
- `project_state_problem_binding = passed`;
- `source_and_stale_checks = passed`;
- `authority_and_indexes = passed`.

Verify legal draft, audited, and frozen paths as well as changed or missing materials, invalid offsets/references/coverage, unverified extraction, inconsistent roles/ranges, invalid dependencies, unresolved critical ambiguities, mismatching decisions or project identities, path escapes, and stale dependents. Confirm that environment expiry does not block unchanged text audit and routes never write state. Run the Phase A regressions and independent original-material review. Phase C now consumes the frozen Problem separately; other D domains and Phases E–K remain deferred.

Passing synthetic fixtures qualifies the B infrastructure's behavior. Formal development completion separately requires independent PR review, final-source CI, merge, and read-back. A user's project must independently meet its actual Problem Contract Gate. Problem evidence tracks material and decision changes; runtime TTL alone does not expire unchanged problem meaning.

## Phase C — Model design, challenge, and human approval

The current implementation adds the [model-design module](../modules/02_model_design.md), [Model Contract schema](../core/model_contract.schema.yaml), [Model Approval contract](../core/model_approval_contract.yaml), legal draft and Brief templates, read-only validator, source-backed fixtures, and the corresponding route/state/output/index consumers. It preserves A/B behavior and implements no business model file, solver execution, parameter estimation, simulation, or V&V.

The design route requires a current frozen Problem and no runtime profile. Cover its questions and relevant requirements with minimally sufficient primary structures and 0..N useful alternatives; models may be shared across questions. Register objects/boundaries, variables/units, mathematical relations, mechanisms/assumptions, contextual F0–F4 fidelity, known/unknown parameters with proposed provenance, solver risks and validator plans. Fidelity is not a universal quality ranking, and benchmark/reference is an evidence role.

Perform four structural reviews and nine challenges with explicit reviewed/pending/blocked/not_applicable statuses and reasons. The validator distinguishes legal structure, applicable validity, proposal completion, completed challenges, readiness for approval, and actual approval. A completed challenge can retain material blockers but cannot be ready or approved until they are resolved. Proposed tests are not completed numerical evidence.

Structural model identities exclude solver/validator/implementation choices and parameter sources/current values. The full design digest binds all design content, the current Problem and sources, and the Brief while excluding only status and approval references. Write the Brief before computing that digest; the Brief can cite independent structural identities without embedding the digest that includes its own SHA.

These structural digests identify registered expressions without proving symbolic equivalence. Renaming variables or rewriting equivalent relations can change a digest; actual mechanism, abstraction, or mathematical differences still require review before declaring a structural comparator.

Actual Human Model Approval must concern the current design and Brief. Bind the project, Problem, full digest, current human decision and action, and matching complete locked specification. Existing approvals apply only while all those identities remain current. A development request, synthetic record, agent recommendation, approved flag, or empty lock cannot substitute for a real decision. Validators and routing never create decisions, locks, or state.

The five development exit checks in the full plan §7.9 are:

- `model_contract_checks = passed`;
- `model_approval_binding = passed`;
- `model_route_and_state = passed`;
- `source_and_stale_checks = passed`;
- `authority_and_indexes = passed`.

Verify legal drafts, complete proposals, challenged and approved paths, multi-question/shared models, zero and useful alternatives, unresolved structural/challenge blockers, current human approval and rejection, stale sources/Briefs/decisions/locks, identity separation, path/reference failures, project/status mismatches, explicit validation scopes, no automatic writes, and still-deferred domain/E–K routes. Run all A/B regressions, independent raw-input behavior review, exact-final-source PR review, Windows/Ubuntu CI, merge, and post-merge read-back separately.

`MODEL_PROPOSED`, `MODEL_CHALLENGED`, and `MODEL_APPROVED` require the matching contract status and current frozen Problem. Model scope checks B/C while leaving runtime readiness unassessed; problem scope leaves C unassessed and cannot establish overall MODEL_APPROVED validity. C conservatively binds the entire Problem and its current sources, so any changed attachment can invalidate that binding; fine-grained source impact remains future work. Runtime expiry does not expire unchanged text design. Synthetic fixtures prove infrastructure behavior, not a real model approval, mathematical/physical validity, statistical independence, or numerical execution qualification.

## Phase D — Mapping, parameters and qualified structure

The full plan §8.7 requires current C human approval, explicit domain/trace/review decisions, exact typed parameter bindings and preserved unknowns. Mapping completion is distinct from native build readiness and actual structure readiness. The local baseline executes explicitly reviewed Inport/Outport/Constant/Gain/Sum/Integrator graphs with model-file workspace bindings. Other blocks and Simscape/Stateflow/System Composer operations remain unqualified for construction. No free-text mathematical code generation or estimation is performed.

New mutation requires current A plus independent D profile evidence. The native probe exercises two different structures and a controlled failure; the producer binds input snapshots/semantic identity, current C and parameters, actual source/runtime/channel/process, saved/reopened SLX bytes, assertions and receipt. Historical readiness checks retain execution-time qualification and current dependencies without using current TTL to expire unchanged structures. Only explicit callers record receipts or IMPLEMENTATION_READY; implementation partial scope leaves current runtime unassessed. No simulation or physical/numerical validity claim follows.

Exit checks: domain_mapping_checks, parameter_binding_checks, native_simulink_structure_qualification, mapping_route_and_state, source_and_stale_checks, upstream_compatibility_and_authority, authority_and_indexes, all A/B/C regressions, independent original-input behavior testing and exact-commit review, Windows/Ubuntu CI, merge and post-merge readback.

## Advanced methods and later phases — deferred

| Phase | Planned scope |
|---|---|
| G advanced | General parameter sweeps, continuous uncertainty sampling, LHS and parallel simulation |
| H advanced | General analytic/conservation/event checks, continuous uncertainty and global sensitivity, and whole-trajectory comparison |
| I | Verification and claim-scoped validation, including applicable test and safety tools |
| J | Accepted figures, result-to-claim trace, evidence package, and paper handoff |
| K | Full semantic audit, representative R2025b end-to-end qualification, and release review |

Develop phases in the full plan's order and refine each phase's executable gates before starting it. This development sequence is separate from a single project's runtime state: identification, optimization, and advanced analyses are conditional on the task and material claims, with technical decisions and limitations recorded. Alternative model routes have no fixed count; structural comparison retains its `required` / `not_applicable` decision.

## Release

The v1.0.0 gate remains the full plan's release definition: all phases qualified and merged, complete active indexes and CI, current upstream compatibility, representative R2025b runtime evidence, accepted evidence and claim boundaries, and verified paper handoff. Version 0.4.0 does not claim that release gate.

## Phase E — Frozen protocols and qualified execution

The full plan §9.9 is the detailed Authority. Version 0.5.0 adds a source-bound draft/frozen protocol, independent A/E operation and individual solver qualification, normal serial scalar core execution, actual Dataset root outputs, cross-format MAT/JSON/CSV numeric receipts and SIMULATION_PROTOCOL_FROZEN/PRIMARY_RUN_COMPLETE. Original C/D evidence and all nineteen D source identities remain unchanged. Optional Statistics diagnostics are distinct from explicit operation requirements.

E success does not grant numerical V&V or publication claims. Read-only consumers never freeze or update state. Historical qualification and current TTL are separate. Exit requires real R2025b positive/negative/cardinality cases, all prior regressions, independent behavior/final-source review, dual-platform CI, merge and readback. Advanced solver/domain, general G workflows, advanced H and I–K remain deferred.

## Phase F — Optional reviewed parameter studies

The detailed Authority is the full plan §10.8–10.13. Read [the F module](../modules/05_identification_calibration_optimization.md). A source-bound study records the selected current approved C mathematics, parameter provenance, numeric bounds and initialization sources, observation roles and half-open train/holdout ranges where applicable, loss, budgets, warning and acceptance rules. A separate semantic review authorizes bounded candidate trials. Unknown C values remain null; given/derived constants cannot silently become search variables.

Three operations are conditional: dense uniformly sampled SISO ARX [1 1 1] with one-step holdout prediction; bounded single-gain Simulink least squares with an actual owned model per objective evaluation; and bounded one/two-variable positive quadratic SQP with explicit linear inequalities. New execution requires current same-runtime A/F operation evidence and the union of actual required A operations. Gain trials also require current E ode4 evidence. Neither toolbox installation nor core environment success qualifies a method. Pure design optimization invents no observations or holdout data.

The separate trial ledger, raw/process evidence and cross-checked MAT/JSON candidate outputs establish a candidate within the reviewed criteria. They never overwrite C/D/E evidence, advance state, adopt parameters or prove physical validity or a general global optimum. Adoption returns to new actual C human approval, then new D/E evidence and later H verification. PARAMETER_STUDY_REVIEWED and PARAMETER_CANDIDATE_COMPLETE form an optional branch; the `parameter_study` scope assesses B/C/F history without current runtime or D/E readiness. Earlier partial scopes leave F unassessed. Repository qualification, independent review, CI and merge remain separate development evidence.

## Phase G — Optional finite serial catalog experiments

The detailed Authority is the full plan §11.7–11.12. Read [the G module](../modules/06_experiment_design.md). The implemented surface is scenario matrices, complete one/two-factor finite grids and fixed-size iid categorical Monte Carlo over independently frozen E protocols. Factors, ordered probability meanings, seed, event and budgets are source-bound and independently reviewed. Each draw executes through E in a fresh directory, serially. A/E/G qualifications remain independent and required operations propagate individually.

Only complete fixed-size campaigns may summarize every actual admissible draw. Technical failure, source drift or budget exhaustion preserves a partial ledger with no complete summary. Event samples remain in the denominator; nominal Wilson intervals are conditional on the declared finite iid law. General parameter changes, continuous sampling, LHS, parallelism, numerical verification and physical validation remain separate or deferred gates. Exit requires real sample qualification and campaigns, independent original-input and final-head review, all prior regressions, Windows/Ubuntu CI, merge and readback. Current runtime expiry blocks new execution while immutable historical source/evidence identities remain required.

## Phase H — Finite historical verification

[H1](../modules/07_numerical_verification.md) implements source-bound static/scalar first-order references and conditional three-layer ode4 refinement. [H2](../modules/08_model_verification.md) implements complete finite G response/catalog robustness and terminal continuous-solver/material static/first-order comparison. Each actual E receipt needs recomputed passing H1; each material claim needs a reviewed structural required/technical-NA decision. Required unsupported analyses block completion. Completed reject/modify decisions remain distinct from supported claims. Native execution uses existing E/G gates; H routes and consumers are pure Python, read only and never promote state. Version metadata alone proves no qualification, independent actual behavior, CI, merge or release; these exits are recorded separately under plan §§12.9–12.14.
