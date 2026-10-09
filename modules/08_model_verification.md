# Finite model claim decisions

Read [the shared schema](../core/verification.schema.yaml), [H2 contract](../core/model_verification_contract.yaml) and [H1 module](07_numerical_verification.md), then use [the H2 draft](../templates/contracts/model_verification.yaml). H2 consumes recomputed passing H1 coverage for the primary and every actual E receipt it uses. Coverage matches exact receipt SHA and runID, including independent Monte Carlo repeats. A primary H1 cannot cover another member.

Freeze each target claim, finite domain, observable/unit, terminal criterion/direction/threshold, failure disposition (`modify` or `reject`), impact, required action and return stage. Each material claim needs a source-reviewed structural-comparison decision with all six trigger flags. Any true trigger requires a supported structural comparator; a limited first implementation does not justify default `not_applicable`. Unsupported required work blocks completion. Review binds the semantic digest, source derivation, domain and criteria.

Supported methods:

- `scenario_response` describes complete finite G history, including only actual categorical Monte Carlo draws when declared. It supplies no parameter derivative or global sensitivity.
- `finite_domain_robustness` requires an entire frozen scenario/factorial catalog. Monte Carlo draws cannot establish full catalog coverage or continuous-domain robustness.
- `solver_final_comparison` compares actual observed continuous solvers among qualified ode4/ode45/ode15s on independent E runs. Declare the numerical fields allowed to differ; every other protocol field and physical condition remains equal. A generic discrete solver does not meet this method.
- `structural_final_comparison` is limited to a source-reviewed static versus scalar first-order mechanism pair. Each model has its own approved C/D/E/H1 chain under the common frozen B basis. Map physical inputs, time, observable and units explicitly; different states are acknowledged. Different hashes, renaming, parameter/solver changes or equivalent reformulations alone do not prove structural difference.

Each G ledger row must appear in the exact order with passing H1 coverage; no omission, deduplication, penalty replacement or shrinking the domain after seeing results. E/H1 technical or admission failure yields blocked partial evidence and no complete support summary. A legitimate H1-passing business criterion failure can yield complete `modify`/`reject` evidence with open actions. `MODEL_VERIFICATION_DECIDED` records that decision; `MODEL_VERIFIED` additionally requires support for every required claim with no open required actions. No model adoption, C approval, state update or real-world validity is automatic.

```text
python scripts/validate_model_verification.py '<plan>' --project-root '<root>' --require-reviewed
python scripts/run_model_verification.py '<plan>' --project-root '<root>' --output-dir '<fresh directory>'
python scripts/validate_verification_receipt.py '<receipt>' --project-root '<root>' --kind H2
python scripts/resolve_runtime.py --intent model_verification_review --verification-receipt '<receipt>'
```

H2 limits: two models, 16 finite scenarios and 32 actual E receipts including nested H1 and repeated draws. H1 file/sample/read/time limits apply to the complete nested analysis. All receipts are recomputed under current source identities and execution-time qualification, without requiring current runtime readiness. The H2 bundle enumerates its independent member bindings; only its primary maps to state B/C/D/E anchors. State consumers check stale dependencies and exact bytes, and never promote state.

See [finite sensitivity/robustness](../packs/evidence/sensitivity.md), [model comparison](../packs/evidence/model_comparison.md) and [solver comparison](../packs/evidence/solver_comparison.md). Morris/Sobol/PRCC/OAT, parameter/initial-condition uncertainty, continuous domains, failure boundaries and peak/integral/event/whole-trajectory comparisons remain candidate/deferred. I–K remain deferred.
