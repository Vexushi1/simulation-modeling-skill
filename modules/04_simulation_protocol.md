# Simulation protocol and primary execution

Read [the protocol schema](../core/simulation_protocol.schema.yaml) and [simulation assurance contract](../core/simulation_assurance_contract.yaml) after the current approved C design and D mapping/structure have been validated. This module runs one reviewed scalar core Simulink target in normal serial mode. It does not implement calibration, campaigns, solver comparison or numerical V&V.

## Review before freezing

Use [the draft template](../templates/contracts/simulation_protocol.yaml). Bind current B/C/D files, parameters, actual saved SLX and structure receipt through the ready mapping. Select the target and approved design/model explicitly. Preserve exact approved parameters, units, initial and boundary conditions; unknown necessary information blocks execution. A new scenario can specify an approved external input through source-bound structured data and requirement references. It cannot invent missing physical parameters or replace approved conditions.

Record finite start/stop times, each input port's variable/unit/time/value/interpolation and source selector, each output port's approved observable, solver/classification/reason/risks, applicable steps and tolerances, logging, seed, metrics with prior limits and warning policy. No free-text expression is executed. Real-time, code generation, DAE/complex events, multirate, Simscape/Stateflow, acceleration, Fast Restart and parallel operation remain deferred. Missing root outputs cannot create a primary result.

Negative finite start times are allowed. Fixed-step starts must align with the reviewed step so the engine cannot silently shift the scenario. Variable-step `MinStep` must be a finite positive number, consistent with `InitialStep` and `MaxStep`; zero is invalid under the [R2025b API](https://www.mathworks.com/help/releases/R2025b/simulink/gui/minstepsize.html). This scope requires explicit numeric settings rather than automatic values.

Only an explicit authorized caller performs the actual protocol review and writes its independent source-bound freeze decision. Validators and routing never manufacture decisions or promote states. E review is separate from C human model approval, which must remain current. Solver changes inside E do not rewrite C; changing C solver plans, Briefs, parameters or design bytes still invalidates its full approval.

```text
python scripts/validate_simulation_protocol.py '<protocol>' --project-root '<root>'
python scripts/validate_simulation_protocol.py '<protocol>' --project-root '<root>' --require-frozen
python scripts/resolve_runtime.py --intent simulation_protocol --protocol '<protocol>'
```

## Qualify the required operations

Library loading and D construction do not qualify simulation. Obtain current A and independent E evidence for the same installation and host. The E profile reports qualified solvers individually; overall qualification does not imply every solver has passed. New execution must select the frozen protocol's qualified solver. No automatic solver or mathematical-method substitution occurs.

Protocol `required_A_operations` and caller requirements are combined, never silently dropped. `--include-statistics` only expands optional diagnostics. If a task needs `fitlm`, `lhsdesign` or `normcdf`, explicitly require the corresponding operation and inspect its result. See [operation qualification](../docs/OPERATION_QUALIFICATION.md). A passed core environment is insufficient for a failed or missing required operation.

```text
python scripts/probe_simulation.py --matlab-executable '<R2025b executable>' --environment-profile '<current A profile>' --output-dir '<new qualification directory>'
python scripts/resolve_runtime.py --intent simulation_execution --protocol '<frozen protocol>' --profile '<current A profile>' --simulation-profile '<current E profile>'
```

## Execute and review the actual result

```text
python scripts/run_simulation.py '<frozen protocol>' --project-root '<root>' --matlab-executable '<R2025b executable>' --environment-profile '<current A profile>' --simulation-profile '<current E profile>' --output-dir '<new project run directory>'
python scripts/validate_simulation_receipt.py '<actual receipt>' --project-root '<root>'
python scripts/resolve_runtime.py --intent solver_diagnostics --protocol '<frozen protocol>' --run-receipt '<actual receipt>'
```

Use a new directory for every invocation. The producer copies and owns the model for this run, applies reviewed settings through `SimulationInput`, binds exact parameters in the model workspace, reconstructs Dataset inputs, and reads root `yout` Dataset outputs. It does not save changes to the approved SLX, add To Workspace blocks, mutate the base workspace, or close another model. Original contract/SLX bytes must remain unchanged. Internal `logsout` and SDI extensions are deferred.

Keep full configured API parameters separate from actual public solver metadata. R2025b does not expose every tolerance as independent runtime readback. Sampling intervals are not claims about all internal solver steps. Preserve requested settings, observed solver/termination metadata, warnings and errors together.

The actual terminal time comes from saved `SimulationOutput.tout` and required output coverage. Configured `StopTime` cannot substitute for it. Save returned native MAT data before postprocessing; check public solver name/type/step and both warning diagnostics and `lastwarn` under the frozen warning policy.

Freeze `logging.sample_time: 0` explicitly. The runtime applies continuous sampling to each root Outport through `SimulationInput`, checks the applied settings and restores the original port settings. This records constant outputs throughout the interval as actual native samples; it never copies a single recorded value onto a fabricated time axis.

The receipt binds original inputs and sources, execution-time A/E qualifications, process/raw/log evidence and actual MAT v7, JSON and CSV outputs. Numeric fields are independently read across all three formats. The consumer rechecks output identities, finite ordered samples, full time coverage, termination and predeclared metrics. Exit 0, a returned `SimulationOutput`, a nonempty file or plausible waveform is insufficient. Unexpected early stop, errors, required missing data or failed criteria cannot establish `PRIMARY_RUN_COMPLETE`; failure/timeout/partial evidence is retained.

After actual review, an explicit caller can register successful receipt/output bindings and set `PRIMARY_RUN_COMPLETE`. This state is a completed reviewed run awaiting later verification. It does not establish numerical convergence, model truth, real-system validity or accepted publication claims.

`--scope simulation` checks B/C/D/E and historical runs, with current environment readiness unassessed. Earlier partial scopes leave E unassessed; default `all` additionally checks bound current environment profiles. Current TTL expiry blocks new execution but does not expire unchanged historical execution-time qualification. Protocol/input/parameter/SLX/source/output changes make their actual dependents stale. Preserve history and repair the responsible upstream contract rather than rewriting an old receipt.
