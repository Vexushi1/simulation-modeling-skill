# Repository instructions

Read [docs/V1_FULL_IMPLEMENTATION_PLAN.md](docs/V1_FULL_IMPLEMENTATION_PLAN.md), [DEVELOPMENT_GOVERNANCE.md](DEVELOPMENT_GOVERNANCE.md), and affected contracts before changing behavior. For runtime work, begin with [core/bootstrap.yaml](core/bootstrap.yaml).

Work on an independent phase/topic branch and PR. Amend the plan first when its semantics need correction. Routine work already authorized within the current phase does not require renewed approval. Development gates do not approve a user's model or advance a project state.

Version 0.4.0 implements Phase D mapping, parameter binding, and qualified core Simulink construction on the merged A/B/C infrastructure. Simscape/Stateflow/System Composer construction and Phases E–K remain deferred. Do not activate them, create placeholder business files, or count their target states as implemented. Keep the entry point short and detailed rules in their authorities.

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
python scripts/probe_environment.py --matlab-executable '<path>' --output-dir '<new dir>' --include-statistics
```

Replace the path placeholders with the chosen MATLAB executable and unused evidence directory. Omit `--include-statistics` when the request requires only core operations. Preserve failed probe evidence as well as successes; never overwrite earlier runs.

Qualification belongs to the tested operation, inputs, runtime identity, source version, and execution channel. License flags, library loading, generic Skill validation, and Python fixture checks do not establish business simulation or end-to-end qualification. `selected` belongs to the route, not the probe profile.

Report tests, actual MATLAB calls, CI, independent review, merge, and release distinctly. Use the full plan's Phase D exit checks and include Scope, Authority Changes, Behavior Changes, Evidence, Compatibility, Stale Impact, and Deferred in its PR. Preserve Phase A/B qualification and audit behavior; synthetic C fixtures qualify infrastructure, not an actual model approval or physical result. Do not infer finer-grained source invalidation than the current conservative binding implements.

## Phase D implementation discipline

Read modules/03_domain_mapping.md and core/domain_mapping.schema.yaml, core/parameter_provenance.schema.yaml, core/implementation_assurance_contract.yaml before constructing their templates or invoking mutation. Validate the current C approval; preserve exact typed values/units/provenance and unknowns. Text mapping does not require a runtime profile. The local constructor supports only explicitly reviewed Inport/Outport/Constant/Gain/Sum/Integrator graphs, model-file workspace parameters, structured approved conditions, and structural settings. Arbitrary expressions/callbacks, masks, external references/dictionaries and other domains are outside its native qualification. Do not infer mathematical equivalence from structural readback.

New construction requires current independent A and D profiles. Inspect the producer CLI help, use a new output directory, and qualify actual create/connect/assign/update/save/close/reload/readback. Do not overwrite models, close other models, or modify global paths/base workspace. Preserve failed evidence. Historical structure validation consumes execution-time qualifications and current semantic/source/SLX identities without granting a new run. Only explicit callers write mapping receipt bindings or IMPLEMENTATION_READY. Implementation scope checks B/C/D and leaves runtime unassessed; problem/model scopes leave D unassessed. Business simulation remains forbidden until E.

Run all A/B/C regressions and D mapping/parameter/native/router/state/stale/adapter checks, original-input independent behavior testing, final-commit review, Windows/Ubuntu CI, merge and post-merge readback. Preserve the seven A source-identity files and B schema/validator. Synthetic qualification approves no actual project.
