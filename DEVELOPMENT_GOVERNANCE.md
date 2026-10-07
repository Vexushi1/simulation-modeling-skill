# Repository Development Governance

## Change discipline

- Do not make feature work directly on `main`.
- Use one topic per branch/PR.
- Read current architecture, roadmap and affected contracts before modifying active files.
- Prefer a small authoritative source over duplicated hard rules.
- Generated indexes must be reproducible from active files once generators are introduced.

## Authority precedence

1. explicit competition/user requirement;
2. repository core contracts;
3. active module/adapter;
4. upstream official skill;
5. optional third-party extension;
6. examples/templates.

Lower levels may not override a higher-level semantic decision.

## Compatibility discipline

The v1.0 target is MATLAB R2025b.

- New APIs must be verified against R2025b.
- R2026a-only behavior must not enter the active path without an R2025b fallback.
- An upstream skill supporting `>=R2023a` does not automatically prove every local composition works on R2025b; local integration still requires qualification.

## Evidence discipline

A change that affects model selection, solver behavior, result interpretation, verification or paper claims must define:

- affected contract;
- expected evidence;
- stale/redo behavior;
- test or review path.

## No semantic shortcuts

- Do not call a solver a model.
- Do not call a parameter sweep a robustness proof without a declared range/claim.
- Do not call two solver settings two models.
- Do not call visual agreement validation.
- Do not claim a toolbox available when only a license flag is present.
