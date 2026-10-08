# Approved model to engineering implementation

Read [the mapping schema](../core/domain_mapping.schema.yaml), [the parameter schema](../core/parameter_provenance.schema.yaml), [the implementation assurance contract](../core/implementation_assurance_contract.yaml), and the current C contract before constructing files from their templates. The full plan §8.7 controls this phase. This module consumes a current human-approved model; repository development permission does not supply that decision.

## Begin with the current approved design

Validate the actual Model Contract with `--require-approved`. Bind the project, current C bytes and semantic identity, selected designs/main models, parameters, and original source identities. Preserve C's conservative whole-Problem binding. If C approval is missing or stale, prepare the missing reviewable C materials and obtain the actual decision before formal D mapping or model mutation.

Keep mathematical model identity separate from block names, layout, implementation paths, solver choices, and generated SLX identity. Do not evaluate C's free-text mathematical relations or convert them automatically into executable MATLAB expressions. An explicit reviewed block graph is necessary for the local constructor.

Choose Simulink signal flow, a Simscape conservation network, Stateflow event/mode logic, System Composer architecture, MATLAB algorithm components, or a justified combination according to the approved semantics. Record alternatives and why the choice is suitable. Domain suitability does not establish callable or qualified operation availability. The [MathWorks adapter](../adapters/mathworks/simulink_agentic_toolkit.md) records pinned resources and qualification boundaries.

The current local native constructor supports one explicitly mapped Simulink target with Inport, Outport, Constant, Gain, Sum, and Integrator blocks. Other blocks, Simscape/Stateflow/System Composer construction, custom masks/callbacks, MATLAB Function code, model references, external dictionaries, and arbitrary expressions require their own reviewed implementation and qualification. Record an explicit missing gate; do not change the mathematical model or chosen domain to fit this constructor.

## Register parameters before binding blocks

Read the current C parameter registry. For every implementation parameter, preserve its design/model/variable reference, symbol, exact typed value or unknown `null`, unit, provenance role, and current source references. Register a separate legal MATLAB `code_name`, owner, and model-file workspace scope. Parameter provenance roles describe origins rather than a universal confidence ranking.

Keep uncertainty unknown unless supported, and record tunability with a reason based on the actual project. Do not invent zero uncertainty, a default tunability flag, estimated/calibrated values, or convenient 0/1 constants. D performs no identification, calibration, or optimization. Changes to an approved C parameter require the appropriate C review and approval, followed by updated D bindings.

Native Constant/Gain values must bind registered parameters. Integrator initial conditions and other approved condition values must reference an explicit structured location in the current C initial/boundary-condition value. Do not parse a textual formula, insert an unapproved initial condition, or let an implicit block default introduce mathematics. Structural settings such as port indices and reviewed Sum signs remain separate from physical parameters.

Unknown parameters may remain in a complete text mapping. A parameter needed by the selected constructor must be resolved before `build_ready`. Legal values, exact names and scopes, supported scalar types, finite values, and source freshness are checked separately. A registered unit or `Simulink.Parameter.Unit` does not prove signal/interface dimensional consistency; review dimensions, scales, and absolute-temperature versus temperature-difference meanings explicitly.

## Trace and review the engineering graph

Trace each selected main model's relations, variables, inputs/outputs, initial/boundary conditions, and events to the necessary components and connections, or give a specific justified disposition. One relation can map to several blocks; one block can serve several relations. Shared models across questions and 0..N necessary components are allowed. Explain instrumentation and logging components that do not represent equations.

Use a task-appropriate hierarchy. Inputs, plant, controller, disturbances, sensors, constraints, metrics, and logging are recommendations, not mandatory empty subsystems. Block feedback is permitted when the approved model requires it; the source/evidence dependency graph remains acyclic. A Simscape acausal network or DAE cannot be rejected merely because it is not a directed acyclic signal graph.

Review semantic traceability, units/interfaces, causality/coupling, boundary/initial/event conditions, and implementation side effects. Added sampling, delay, saturation, mode switching, approximations, or converter filters can change the model and must return to C when material. A successful diagram update or structural trace does not prove mathematical equivalence, physical validity, or numerical accuracy.

The read-only validators distinguish legal schema, current binding validity, mapping completion, native `build_ready`, actual `built`, actual `structure_checked`, and `implementation_ready`. A parameter draft can report complete content, but formal mapping requires its caller-declared `bound` status. Native scalar values must preserve the approved value in the supported MATLAB double representation; unsupported large integers give a missing gate. Validators never fill a parameter, create approval, build a model, or update project state. Use the actual CLI help for optional gate flags and supply the declared project root.

```text
python scripts/validate_parameter_provenance.py '<parameter-path>' --project-root '<project-root>'
python scripts/validate_domain_mapping.py '<mapping-path>' --project-root '<project-root>'
python scripts/validate_domain_mapping.py '<mapping-path>' --project-root '<project-root>' --require-mapped
python scripts/validate_domain_mapping.py '<mapping-path>' --project-root '<project-root>' --require-ready
```

`--require-ready` consumes existing implementation evidence; it does not construct a file or promote a draft. Write and validate each contract before creating its downstream binding. The mapping semantic digest excludes only its status and implementation-receipt reference; the native producer captures the original input snapshot separately to avoid a digest cycle.

## Qualify and construct only the supported operation

Native construction requires both the current A environment evidence and the independent D implementation operation profile. A's library-load assertion is insufficient. A current D probe must exercise actual create/add/connect/assign/update/save/close/reload/readback behavior, with different controlled structures and a controlled failure. Each invocation uses a new evidence directory and reports its actual execution channel, process result, runtime/host, source and input identities, model bytes, assertions, and receipts.

Use `scripts/probe_implementation.py --help` and `scripts/run_implementation.py --help` for the exact supported arguments. Resolve the `simulink_build` route with both profiles and the current mapping. Check `implementation_execution_allowed` and its explicit scope before mutation. `business_execution_allowed` and simulation permission remain false. Domain mapping itself needs no runtime profile.

Construct in a new output directory with an owned, uniquely named model. Do not overwrite existing models or receipts, close other users' models, change global MATLAB paths, or publish parameters into the base workspace. The local constructor uses ModelFile model workspace and controlled official library blocks. Load, save, and update can execute callbacks and initialization code; they are part of the qualified mutation surface rather than a read-only file inspection.

The producer must actually save, close, reopen, update, and read back the controlled model's blocks, library origins, ports/connections, parameter references/values, workspace persistence, and condition bindings. It must compare readback with the reviewed instructions and preserve raw reports/logs and failed runs. File existence or caller-written success flags do not establish `structure_checked`.

Bind the captured input mapping, semantic digest, current C approval, parameter payload, source files, A/D profile and receipt bytes, actual runtime/process/assertions, and final SLX SHA. After successful production an explicit caller can bind the returned receipt into the mapping and validate `--require-ready`. Only that caller may register the matching project artifacts and advance to `IMPLEMENTATION_READY`. A synthetic development case qualifies the infrastructure and cannot approve another project.

## Preserve scope and freshness

Implementation-scoped state validation checks B/C/D while leaving environment readiness unassessed. Problem/model scopes leave D unassessed. The default all scope retains current environment requirements. Parameter, mapping, implementation file, structure receipt, and route artifacts have explicit consumers and dependency anchors; they cannot be interpreted as generic environment evidence.

Changing C approval, source material, parameter registry, mapping, actual model bytes, builder code, or a required dependency invalidates the corresponding D evidence and dependent artifacts. Preserve the failed and superseded history. Unchanged historical structures are read back against their bound input identities and qualification at the time of construction. Current environment expiry limits new execution, rather than expiring unchanged text mapping or silently erasing historical structure evidence.

This phase grants engineering construction within the qualified core scope. Solver protocols, simulation, numerical V&V, parameter estimation/calibration/optimization, campaigns, validation, claims, and paper delivery require later phases and their own current gates.
