# Repository instructions

Read [docs/V1_FULL_IMPLEMENTATION_PLAN.md](docs/V1_FULL_IMPLEMENTATION_PLAN.md), [DEVELOPMENT_GOVERNANCE.md](DEVELOPMENT_GOVERNANCE.md), and affected contracts before changing behavior. For runtime work, begin with [core/bootstrap.yaml](core/bootstrap.yaml).

Work on an independent phase/topic branch and PR. Amend the plan first when its semantics need correction. Routine work already authorized within the current phase does not require renewed approval. Development gates do not approve a user's model or advance a project state.

Version 0.2.0 is Phase B implementation and review, based on the merged Phase A infrastructure. Environment assurance and problem audit are implemented; Phases C–K remain deferred. Do not activate them, create placeholder business files, or count their target states as implemented. Keep the entry point short and detailed rules in their authorities.

Read [modules/01_problem_audit.md](modules/01_problem_audit.md) and [core/problem_contract.schema.yaml](core/problem_contract.schema.yaml) before constructing a Problem Contract or using its template. Preserve original material and review identities, facts, references, data ranges, and task ambiguities. A freeze is an actual source-bound review decision under the task authorization, not an automatic validator result. Resolve necessary missing facts or choices without requiring approval for every question. Continued repository development authorization supplies neither a real task's answers nor its Model Approval.

Text audit and read-only validation need no environment profile. Problem-scoped state checks must report their scope and leave environment readiness unassessed. Runtime freshness still controls runtime routes. Validators and the resolver never write state; explicit caller updates must bind the current contract and project identity.

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

Run a fresh local R2025b qualification probe in a new output directory:

```text
python scripts/probe_environment.py --matlab-executable '<path>' --output-dir '<new dir>' --include-statistics
```

Replace the path placeholders with the chosen MATLAB executable and unused evidence directory. Omit `--include-statistics` when the request requires only core operations. Preserve failed probe evidence as well as successes; never overwrite earlier runs.

Qualification belongs to the tested operation, inputs, runtime identity, source version, and execution channel. License flags, library loading, generic Skill validation, and Python fixture checks do not establish business simulation or end-to-end qualification. `selected` belongs to the route, not the probe profile.

Report tests, actual MATLAB calls, CI, independent review, merge, and release distinctly. Use the full plan's Phase B exit checks and include Scope, Authority Changes, Behavior Changes, Evidence, Compatibility, Stale Impact, and Deferred in its PR. Preserve Phase A's probe and operation qualification behavior; Phase B fixtures qualify the audit infrastructure, not an actual competition model.
