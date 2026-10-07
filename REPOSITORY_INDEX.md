# Repository Index

## Active entry points

| File | Role |
|---|---|
| `SKILL.md` | root skill entry and current workflow contract |
| `manifest.yaml` | repository version/runtime/upstream metadata |
| `docs/CANONICAL_ARCHITECTURE.md` | architecture authority |
| `docs/V1_IMPLEMENTATION_ROADMAP.md` | phased v1.0 implementation plan |
| `core/environment_baseline.yaml` | MATLAB R2025b and local capability baseline |
| `core/capability_taxonomy.yaml` | simulation objective/model/capability taxonomy |
| `core/upstream_integration_policy.md` | upstream MathWorks and paper-writing integration policy |
| `DEVELOPMENT_GOVERNANCE.md` | repository modification rules |

## Current state

Version: `0.1.0-bootstrap`

Implemented:

- repository foundation;
- strong MATLAB R2025b baseline;
- capability semantics;
- upstream ownership boundaries;
- v1.0 phased roadmap;
- root workflow skeleton.

Not yet implemented:

- Phase B+ executable workflow modules;
- runtime router;
- adapters;
- evidence schemas;
- tests/lint;
- end-to-end R2025b qualification.

## Design references

The project may study and adapt methodology from `Vexushi1/mathmodel-skill`, especially problem audit, model/solver/validator separation, result verification and paper evidence discipline.

It must not create a core runtime dependency on that repository.

Complete paper composition should be delegated to the mature math-modeling writing capability when available; this repository will provide simulation-specific evidence and handoff contracts.
