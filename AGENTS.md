# Repository instructions

Read [docs/V1_FULL_IMPLEMENTATION_PLAN.md](docs/V1_FULL_IMPLEMENTATION_PLAN.md), [DEVELOPMENT_GOVERNANCE.md](DEVELOPMENT_GOVERNANCE.md), and affected contracts before changing behavior. For runtime work, begin with [core/bootstrap.yaml](core/bootstrap.yaml).

Work on an independent phase/topic branch and PR. Amend the plan first when its semantics need correction. Routine work already authorized within the current phase does not require renewed approval. Development gates do not approve a user's model or advance a project state.

Version 0.8.0 implements bounded F trials, finite serial G catalogs and finite H historical numerical/model verification on A–E. Simscape/Stateflow/System Composer construction, advanced H methods and Phases I–K remain deferred. Do not activate them, create placeholder business files, or count their target states as implemented. Keep the entry point short and detailed rules in their authorities.

Read [modules/01_problem_audit.md](modules/01_problem_audit.md) and [core/problem_contract.schema.yaml](core/problem_contract.schema.yaml) before constructing a Problem Contract or using its template. Preserve original material and review identities, facts, references, data ranges, and task ambiguities. A freeze is an actual source-bound review decision under the task authorization, not an automatic validator result. Resolve necessary missing facts or choices without requiring approval for every question. Continued repository development authorization supplies neither a real task's answers nor its Model Approval.

Text audit and read-only validation need no environment profile. Problem-scoped state checks must report their scope and leave environment readiness unassessed. Runtime freshness still controls runtime routes. Validators and the resolver never write state; explicit caller updates must bind the current contract and project identity.

Read [modules/02_model_design.md](modules/02_model_design.md), [core/model_contract.schema.yaml](core/model_contract.schema.yaml), and [core/model_approval_contract.yaml](core/model_approval_contract.yaml) before using the model or Approval Brief templates. The design route requires a current frozen Problem. Keep structure, solver, and validator distinct; preserve unknown parameter values and review all structural checks and challenges. Model identities and complete design digests serve different purposes. Write and bind the Brief before computing the complete design digest; do not put that digest back in the Brief.

Actual Human Model Approval requires a person's explicit decision on the current design and Brief. Repository authorization, a synthetic test record, or an agent recommendation does not supply it. Complete reviewable materials before asking for an actual task's approval. Only an authorized explicit caller records the real decision and matching locked specification. Validators and routing never create either file or approve a model. Model-scoped checks validate B/C and leave environment unassessed; problem scope leaves models unassessed and cannot establish overall MODEL_APPROVED validity. Model approval does not grant numerical execution.

Run the repository checks from the repository root after installing `requirements.txt` in the selected Python environment:

```text
python scripts/lint_skill.py
python scripts/generate_indexes.py --check
python -m pytest
```

Run a read-only Problem Contract check against the actual project files:

```text
python scripts/validate_problem_contract.py '<contract-path>' --project-root '<project-root>'
python scripts/validate_problem_contract.py '<contract-path>' --project-root '<project-root>' --require-frozen
```

The second command requires an existing current freeze decision; it does not freeze the contract. These checks and the `problem_audit` route do not invoke MATLAB.

Run read-only Model Contract checks against the actual project files:

```text
python scripts/validate_model_contract.py '<contract-path>' --project-root '<project-root>'
python scripts/validate_model_contract.py '<contract-path>' --project-root '<project-root>' --require-proposed
python scripts/validate_model_contract.py '<contract-path>' --project-root '<project-root>' --require-challenged
python scripts/validate_model_contract.py '<contract-path>' --project-root '<project-root>' --require-approved
```

Required gates check the current proposal, challenges, or actual bound approval; they do not promote a draft or produce evidence. C text validation invokes no MATLAB and performs no parameter estimation or numerical validation. Exact source/reference checks and actor/action records do not prove physical validity or authenticate a fabricated human record. Changes to a solver or parameter value preserve structural model identity but can invalidate the full design approval. C conservatively binds the entire Problem, its source evidence, the Brief, human decision, and locked file.

Structural identity hashes registered representations without proving symbolic equivalence. Renaming variables or rewriting equivalent expressions can change a digest; do not claim a meaningful structural comparator solely from different hashes. The later comparison review must establish actual mechanism, abstraction, or mathematical differences.

Run a fresh local R2025b qualification probe in a new output directory:

```text
python scripts/probe_environment.py --matlab-executable '<path>' --output-dir '<new dir>'
```

Replace the path placeholders with the chosen MATLAB executable and unused evidence directory. `--include-statistics` only expands optional diagnostics, so a failed statistical operation can coexist with core success. For each actually needed statistics.fitlm/lhsdesign/normcdf use repeated `--require-operation` and inspect its qualified result; see [operation qualification](docs/OPERATION_QUALIFICATION.md). Preserve failed probe evidence as well as successes; never overwrite earlier runs.

Qualification belongs to the tested operation, inputs, runtime identity, source version, and execution channel. License flags, library loading, generic Skill validation, and Python fixture checks do not establish business simulation or end-to-end qualification. `selected` belongs to the route, not the probe profile.

Report tests, actual MATLAB calls, CI, independent review, merge, and release distinctly. Use the full plan's Phase E exit checks and include Scope, Authority Changes, Behavior Changes, Evidence, Compatibility, Stale Impact, and Deferred in its PR. Preserve Phase A/B qualification and audit behavior; synthetic C fixtures qualify infrastructure, not an actual model approval or physical result. Do not infer finer-grained source invalidation than the current conservative binding implements.

## Phase D implementation discipline

Read modules/03_domain_mapping.md and core/domain_mapping.schema.yaml, core/parameter_provenance.schema.yaml, core/implementation_assurance_contract.yaml before constructing their templates or invoking mutation. Validate the current C approval; preserve exact typed values/units/provenance and unknowns. Text mapping does not require a runtime profile. The local constructor supports only explicitly reviewed Inport/Outport/Constant/Gain/Sum/Integrator graphs, model-file workspace parameters, structured approved conditions, and structural settings. Arbitrary expressions/callbacks, masks, external references/dictionaries and other domains are outside its native qualification. Do not infer mathematical equivalence from structural readback.

New construction requires current independent A and D profiles. Inspect the producer CLI help, use a new output directory, and qualify actual create/connect/assign/update/save/close/reload/readback. Do not overwrite models, close other models, or modify global paths/base workspace. Preserve failed evidence. Historical structure validation consumes execution-time qualifications and current semantic/source/SLX identities without granting a new run. Only explicit callers write mapping receipt bindings or IMPLEMENTATION_READY. Implementation scope checks B/C/D and leaves runtime unassessed; problem/model scopes leave D unassessed. Business simulation remains forbidden until E.

Run all A/B/C regressions and D mapping/parameter/native/router/state/stale/adapter checks, original-input independent behavior testing, final-commit review, Windows/Ubuntu CI, merge and post-merge readback. Preserve the seven A source-identity files and B schema/validator. Synthetic qualification approves no actual project.

## Phase E execution discipline

Read modules/04_simulation_protocol.md and both E contracts first. Preserve all seven A source identities, B schema/validator and all nineteen D source-bound files when extending E. Protocol/source review is separate from real C human approval. E-only solver/tolerance choices do not rewrite C; changing full C bytes still invalidates its approval. Never invent needed parameters or override approved conditions. New execution consumes current same-host/runtime A/E evidence, the chosen qualified solver and the union of protocol/caller required operations; core success alone is insufficient.

Use new directories, owned model copies, SimulationInput and Dataset root outputs. Verify actual public solver/termination metadata separately from configured parameters. Preserve failures and partial data, and independently read MAT/JSON/CSV numeric evidence. Historical E receipts bind execution-time qualification; current TTL only controls new execution. Simulation scope assesses B/C/D/E without current environment readiness; earlier scopes leave E unassessed. Only callers record freeze/primary-run states. Successful execution grants no numerical verification, validation or publication acceptance.

E exit requires real variable/fixed solver, no-input/static, feedback/passthrough and multiple-output cases, controlled errors and early stop, all A–D regressions, independent original-input behavior and exact-head review, Windows/Ubuntu CI, merge and postmerge readback. Preserve all failures; never replace current-source qualification with an earlier green run.

For F, read [modules/05_identification_calibration_optimization.md](modules/05_identification_calibration_optimization.md) and its contracts. Review the bounded standalone study against current B/C approval. ARX [1 1 1], single-gain Simulink calibration and one/two-variable quadratic SQP are conditionally available only with their actual operation qualification. Observed-data identification may precede D/E. Trials preserve approved parameters, models and state. Candidate adoption requires a new actual C approval, new D/E evidence and later H verification; a successful optimizer exit or training fit alone establishes no accepted primary result. The optional `parameter_study` state scope validates B/C/F history without current runtime permission.

For G, read [modules/06_experiment_design.md](modules/06_experiment_design.md), its schema and assurance contract. Only scenario_matrix, complete finite full_factorial and fixed-n categorical monte_carlo_catalog are available; every member needs its own current frozen E protocol. Change only reviewed external input factors; keep approved parameters, model and state. Sampling qualification covers sample_plan only. Each draw runs a new E attempt serially, including repeats. Require the actual A operation union and separate current E/G qualifications before every member; historical consumers reconstruct those execution-time gates and exact bindings. Preserve failures and unattempted rows without a complete summary. Event counts are separate from E admissibility; nominal 95 percent Wilson intervals apply only to complete fixed-n categorical MC, with no physical validity claim. Review routes and scoped state checks remain read-only. E/F/G safety source identities are conservatively closed together; requalify all affected operations after critical source changes.

For H, read [modules/07_numerical_verification.md](modules/07_numerical_verification.md), [modules/08_model_verification.md](modules/08_model_verification.md), the shared verification schema and H contracts before preparing plans or consuming receipts. Preserve source-bound reference/threshold/domain reviews, exact independent frozen numerical deltas, per-actual-run H1 coverage, structural required/technical-NA decisions and blocked partial evidence. H is historical pure Python analysis with no native qualification, automatic state/model adoption or physical-validity claim. H scopes leave current runtime unassessed; earlier scopes leave H unassessed. Keep E/F/G/H shared source closure identical, including actual shared router/state/H dependencies; preserve protected A/B/D bytes and all old evidence. Final qualification and actual attempts must use final source identities.
