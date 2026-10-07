# Repository Development Governance

## Development authority

Explicit user instructions define the authorized scope. [docs/V1_FULL_IMPLEMENTATION_PLAN.md](docs/V1_FULL_IMPLEMENTATION_PLAN.md) is the detailed implementation authority; [the roadmap](docs/V1_IMPLEMENTATION_ROADMAP.md) is its summary. The architecture and affected core contracts must agree with the plan.

When a structural problem requires a plan change, record the reason and amend the plan before its consumers. Read the current plan and affected contracts before changing active files. Existing authorization covers routine work within the approved phase; repository rules do not create a repeated approval requirement.

## Execution authority

For an implemented operation, the precedence is:

1. explicit competition/user requirements and applicable approved project decisions;
2. repository core contracts;
3. implemented module or adapter;
4. upstream official execution skill;
5. admitted optional third-party extension;
6. examples and templates.

Lower levels cannot rewrite a higher-level semantic decision. Planned project contracts and deferred modules do not grant execution authority. Navigation links may be bidirectional; Authority priority and runtime dependencies are separately recorded and must remain acyclic.

## Change and stage discipline

- Do not perform feature work directly on `main`; use one phase or topic per branch/PR.
- Follow Phase A–K development gates. Refine each later phase's checks before implementing it. A stacked Phase A PR must declare its unmerged bootstrap dependency.
- Do not confuse a repository development gate with approval or acceptance of a user's model or project results.
- Keep deferred capabilities explicit. Do not create empty business modules or templates to satisfy path checks.
- Every PR states Scope, Authority Changes, Behavior Changes, Evidence, Compatibility, Stale Impact, and Deferred.
- Generate indexes from active repository files and check their reproducibility.

## Compatibility and evidence

The strong target is MATLAB R2025b and Simulink 25.2. Verify recommended APIs against that target; R2026a-only behavior cannot enter the active path without an R2025b equivalent. An upstream release declaration is compatibility metadata, not local combination qualification.

Capability evidence is operation-specific. Inventory, license tests, function resolution, successful calls, qualified assertions, and route selection remain distinct. The runtime assurance contract controls identity, freshness, receipt bindings, and failure behavior; no document can upgrade a hand-written success flag into qualification.

Define the affected contracts, evidence, tests, and stale propagation for changed behavior. Invalidate only dependent artefacts and preserve historical evidence. Report local checks, actual MATLAB execution, CI, PR review, merge, and release separately. Commands for repository checks are in [AGENTS.md](AGENTS.md).

## Semantic invariants

- Model identity is separate from solver and implementation block identity.
- A parameter sweep is not a robustness proof without its perturbation domain, metric, criterion, and claim.
- A successful run or plausible waveform does not establish numerical verification or real-system validity.
- Planned analyses remain conditional on the task and material claims; decisions and limitations must be recorded.
