# Operation qualification and Statistics requirements

An environment result passes only the operations required by that request. The two core operations are always required. A core pass does not establish that every detected Statistics operation passed.

The [runtime assurance contract](../core/runtime_assurance_contract.yaml) owns the operation inputs, assertions, identity and freshness rules. The [full implementation plan](V1_FULL_IMPLEMENTATION_PLAN.md) preserves the existing optional probe behavior and requires actual method dependencies to propagate to execution gates.

| Option | Operations probed | Operations required to pass |
| --- | --- | --- |
| No optional operation flags | MATLAB basic execution and Simulink library loading | Both core operations |
| `--include-statistics` | Core operations plus `statistics.normcdf`, `statistics.fitlm`, and `statistics.lhsdesign` | Both core operations; Statistics remains optional |
| `--require-operation statistics.fitlm` | Core operations plus the named operation | Both core operations and `statistics.fitlm` |
| Repeated `--require-operation` | Core operations plus each distinct named operation | Both core operations and every named operation |

`--require-operation` also adds its operation to the probe. It does not need `--include-statistics`. Combining the options keeps all named requirements and probes the remaining Statistics operations as optional diagnostics.

## Run a probe for the actual requirements

Use the selected MATLAB R2025b executable and a new evidence directory for every run. Preserve failed evidence and do not overwrite earlier runs.

For a task that requires only the core environment:

```text
python scripts/probe_environment.py --matlab-executable '<path>' --output-dir '<new dir>'
```

For optional Statistics diagnostics, with only the core operations required:

```text
python scripts/probe_environment.py --matlab-executable '<path>' --output-dir '<new dir>' --include-statistics
```

This diagnostic command can exit successfully when a Statistics operation fails. Inspect the individual results before using one of those operations.

If the method actually needs `fitlm`, make its operation a requirement:

```text
python scripts/probe_environment.py --matlab-executable '<path>' --output-dir '<new dir>' --require-operation statistics.fitlm
```

If the method needs all three tested Statistics operations:

```text
python scripts/probe_environment.py --matlab-executable '<path>' --output-dir '<new dir>' --require-operation statistics.fitlm --require-operation statistics.lhsdesign --require-operation statistics.normcdf
```

Require only the functions the method uses. A missing or failed required operation makes the probe result invalid and the CLI return a nonzero exit code, even when the core operations remain qualified.

## Read back the evidence and route

The result's `required_operations` must include every actual dependency. Each dependency must appear in `qualified_operations`; a successful process, installed product, license flag or resolvable function alone is insufficient. The bound `raw-probe.json` records each operation's input, `call_success`, output and error. The consumer independently checks the declared assertions, raw report, receipt, log, source identity, runtime identity, host and freshness.

`runtime_assured: true` means the core runtime is assured. It can coexist with `valid: false` when an additional required operation fails. `valid: true` from an optional diagnostic probe does not qualify a failed Statistics operation.

Read-only validation can add requirements to an existing current profile without running MATLAB or modifying the evidence:

```text
python scripts/validate_environment.py '<new dir>/profile.json' --require-operation statistics.fitlm --require-operation statistics.lhsdesign --require-operation statistics.normcdf
```

A profile that never probed a requested operation cannot satisfy that requirement. Run a new probe with the appropriate requirements; do not edit the old profile or receipt to claim a result.

For the environment assurance route, carry the same actual requirements:

```text
python scripts/resolve_runtime.py --intent assure_environment --profile '<new dir>/profile.json' --require-operation statistics.fitlm --require-operation statistics.lhsdesign --require-operation statistics.normcdf
```

The route selects its required operations and blocks an unqualified requirement. It does not write that selection into the profile or update project state. The environment assurance route grants only its declared environment scope; it does not authorize a business simulation.

A Phase E Simulation Protocol must declare its actual A-operation dependencies. Its execution gate consumes those requirements together with any explicitly requested operations. Overall core assurance cannot substitute for a declared Statistics requirement, and a fallback cannot silently change the mathematical method. Later analysis modules remain subject to their own implementation and evidence gates.

## Keep the scope of the conclusion precise

The A probes test a scalar standard normal CDF, a small dense ordinary linear regression, and a small dense Latin hypercube sample. Passing them qualifies those declared smoke calls on the recorded runtime and channel. It does not prove arbitrary inputs, all toolbox APIs, a competition model's statistical validity or the correctness of a simulation.

A failed operation is a failed recorded check, not evidence that the entire Statistics and Machine Learning Toolbox is unavailable. A successful new probe can qualify the operation again; preserve the failed history and consume the new evidence with its own identities and validity period.

The historical [PR #2 review](https://github.com/Vexushi1/simulation-modeling-skill/pull/2#discussion_r4207705109) identified the risk of treating the optional diagnostic command as a Statistics qualification gate. The compatibility decision documented here keeps that command optional and makes actual requirements explicit, as recorded in the implementation plan.

## Finite G campaigns

A reviewed G design carries the union of its own, every frozen E member's and the caller's actual A requirements. Require optional Statistics calls explicitly and inspect their individual results. G sample-plan qualification, E solver qualification and A operation qualification remain separate. Categorical sampling uses base MATLAB RandStream and does not itself require lhsdesign or normcdf. Neither a complete campaign nor a nominal Wilson interval qualifies those optional functions or physical claims.
