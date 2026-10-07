# v1.0.0 Implementation Roadmap

> Canonical phased plan. Each phase uses a dedicated branch/PR and must pass repository checks before merge.

## Phase A — Foundation & runtime baseline

Deliver:

- canonical architecture;
- R2025b environment baseline;
- capability taxonomy;
- upstream integration policy;
- repository governance;
- initial indices and lint rules.

Exit criteria:

- no ambiguous runtime target;
- installed/licensed/callable are separated;
- Statistics and Machine Learning Toolbox contradiction is explicitly quarantined;
- official-vs-local authority boundary is explicit.

## Phase B — Simulation problem audit

Build the simulation-specific equivalent of rigorous word-by-word problem audit.

Deliver:

- requirement map;
- system boundary contract;
- variable-role taxonomy;
- initial/boundary/event condition schema;
- data-role schema;
- subproblem dependency DAG;
- frozen problem contract.

## Phase C — Model design & fidelity selection

Deliver:

- model route comparison protocol;
- mechanism closure;
- fidelity ladder;
- state-space / ODE / DAE / discrete / hybrid / event / Simscape selection rules;
- identifiability and observability considerations;
- model approval brief.

## Phase D — Mathematical model → Simulink mapping

Deliver:

- adapter for official Simulink Agentic Toolkit;
- block/domain mapping rules;
- Simulink vs Simscape vs Stateflow decision rules;
- model hierarchy policy;
- reusable model-building handoff contract.

## Phase E — Solver & simulation execution

Deliver:

- solver classification;
- fixed/variable-step selection;
- stiffness/event/algebraic-loop handling;
- SimulationInput/SimulationOutput workflow;
- data logging;
- acceleration modes;
- reproducible run receipt.

## Phase F — Identification, calibration & optimization

Deliver:

- parameter provenance;
- system identification route;
- calibration route;
- Optimization / Global Optimization route;
- Simulink Design Optimization route;
- objective and constraint evidence;
- parameter identifiability checks.

## Phase G — Simulation experiment design

Deliver:

- parameter sweep;
- DOE;
- Monte Carlo;
- scenario campaigns;
- parallel `parsim`;
- `batchsim` policy;
- random-seed governance;
- output reduction and storage rules.

## Phase H — Numerical verification & model verification

Deliver:

- step/tolerance/convergence checks;
- solver cross-check;
- conservation/invariant checks;
- parameter sensitivity;
- uncertainty/robustness;
- stress scenarios;
- structural multi-model comparison;
- failure-boundary analysis.

This phase makes multi-model comparison a first-class review decision.

## Phase I — V&V and safety-oriented validation

Deliver conditional routes for:

- Simulink Test;
- Simulink Coverage;
- Simulink Design Verifier;
- Simulink Check / Model Advisor;
- Simulink Fault Analyzer;
- requirements traceability;
- analytic/reference/experimental validation.

## Phase J — Scientific figures & paper evidence

Deliver:

- evidence workbook/result schema;
- figure admission rules;
- simulation figure recipes;
- result-to-claim trace;
- paper handoff contract;
- adapter to `mathmodel-skill` paper-writing capability.

## Phase K — Full audit & R2025b qualification

Deliver:

- end-to-end representative cases;
- semantic drift audit;
- route completeness audit;
- dependency audit;
- upstream compatibility audit;
- Windows R2025b qualification checklist;
- release candidate.

## v1.0.0 release gate

The release is blocked unless:

1. all required phases are merged;
2. all active paths are indexed;
3. no stale version/path references remain;
4. each material workflow has a fallback/failure policy;
5. representative problems can produce reproducible model, results, verification evidence and paper handoff;
6. the release baseline remains MATLAB R2025b.
