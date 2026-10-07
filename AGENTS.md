# Repository instructions

Read [docs/V1_FULL_IMPLEMENTATION_PLAN.md](docs/V1_FULL_IMPLEMENTATION_PLAN.md), [DEVELOPMENT_GOVERNANCE.md](DEVELOPMENT_GOVERNANCE.md), and affected contracts before changing behavior. For runtime work, begin with [core/bootstrap.yaml](core/bootstrap.yaml).

Work on an independent phase/topic branch and PR. Amend the plan first when its semantics need correction. Routine work already authorized within the current phase does not require renewed approval. Development gates do not approve a user's model or advance a project state.

Version 0.1.1 is Phase A infrastructure, pending independent PR qualification. Phases B–K are deferred. Do not activate them, create placeholder business files, or count their target states as implemented. Keep the entry point short and detailed rules in their authorities.

Run the repository checks from the repository root after installing `requirements.txt` in the selected Python environment:

```text
python scripts/lint_skill.py
python scripts/generate_indexes.py --check
python -m pytest
```

Run a fresh local R2025b qualification probe in a new output directory:

```text
python scripts/probe_environment.py --matlab-executable '<path>' --output-dir '<new dir>' --include-statistics
```

Replace the path placeholders with the chosen MATLAB executable and unused evidence directory. Omit `--include-statistics` when the request requires only core operations. Preserve failed probe evidence as well as successes; never overwrite earlier runs.

Qualification belongs to the tested operation, inputs, runtime identity, source version, and execution channel. License flags, library loading, generic Skill validation, and Python fixture checks do not establish business simulation or end-to-end qualification. `selected` belongs to the route, not the probe profile.

Report tests, actual MATLAB calls, CI, independent review, merge, and release distinctly. A Phase A PR must identify its bootstrap dependency when stacked and include the plan's Scope, Authority Changes, Behavior Changes, Evidence, Compatibility, Stale Impact, and Deferred fields.
