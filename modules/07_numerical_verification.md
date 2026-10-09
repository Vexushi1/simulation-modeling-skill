# Finite numerical verification

Read [the shared schema](../core/verification.schema.yaml) and [H1 contract](../core/numerical_verification_contract.yaml). Start from [the unknown draft](../templates/contracts/numerical_verification.yaml). H is a pure Python consumer of existing frozen E history; it supplies no MATLAB qualification or native runner. New simulations use the existing E/G gates and fresh independent frozen protocols.

Bind source text, current approved C relations and D parameters to typed references. Supported references are constant/affine static output and scalar `x'=-a*x+b*u, y=x` with constant input and `a>=0`, including the linear `a=0` limit. No arbitrary expression evaluation, inferred parameter, fitting to observed outputs, or invented initial condition is allowed. Reference values and unit mappings must agree with the approved six-block implementation graph. Record exact source IDs, relation IDs, parameter/input/state IDs, approved initial selector and finite prior `atol`/`rtol`. Every material output needs a reference. The error denominator `atol+rtol*abs(reference)` must be strictly positive; this checks only actual recorded samples.

Optional step refinement consumes exactly three independent frozen ode4 E runs at `h,h/2,h/4`. Each run also needs its analytic reference. Only fixed step may differ; parameters, initial/boundary conditions, physical inputs, time, seed, outputs, admission metrics, warning policy and other solver fields remain equal. Integer duration/step alignment is required. Compare terminal differences under a prior criterion; zero/plateau differences provide no convergence-order estimate. This finite check does not prove a global error bound.

Review source-bound derivation, thresholds and requirements before changing status to reviewed. Required unsupported analysis blocks completion. A successful E admission metric is distinct from an H error criterion. Technical failure preserves completed/failed/not-attempted ledger entries and has no complete summary. Numerical success establishes neither physical validity nor a real Human Model Approval.

```text
python scripts/validate_numerical_verification.py '<plan>' --project-root '<root>' --require-reviewed
python scripts/run_numerical_verification.py '<plan>' --project-root '<root>' --output-dir '<fresh directory>'
python scripts/validate_verification_receipt.py '<receipt>' --project-root '<root>' --kind H1
python scripts/resolve_runtime.py --intent numerical_verification --verification-plan '<plan>'
```

The producer binds the plan text/snapshot, actual run ledger, numeric table and complete shared source closure. The receipt consumer recomputes from original MAT/JSON/CSV via the E consumer and rejects changed or rehashed summaries. H1 limits: at most 16 actual E receipts, two signals and 301 samples per signal, each input file 16 MiB, total bound-data reading 64 MiB and completion time 120 seconds. Byte charges use on-disk sizes and do not guarantee decompressed or peak memory. Time checks are cooperative: a blocking E/SciPy call cannot be interrupted, and completion is rejected after an overrun returns. Required strict interruptible deadlines or decompressed-memory guarantees are unsupported and block completion. Nested H1 consumption counts toward H2 budgets. History uses execution-time qualification plus current source/file identity, leaving current runtime TTL unassessed. The resolver selects no native operations and writes no state. An explicit caller may bind current passing primary H1 as `numerical_verification`; `NUMERICALLY_VERIFIED` refers only to that primary and recorded finite evidence.

Without state, receipt routing reuses the consumer's verified captured project root. A nested plan-only route accepts `--verification-project-root '<root>'` (library `verification_project_root`). State, explicit and captured roots must agree; routing never rebases relative bindings under another project. A passing H1 ledger preserves reviewed typed reference selectors and approved numeric origins for H2; constant/equilibrium references remain valid numerical checks.

See [convergence evidence](../packs/evidence/convergence.md). Conservation, events, general analytic functions and other advanced H1 methods remain deferred; tasks requiring them cannot be marked complete.
