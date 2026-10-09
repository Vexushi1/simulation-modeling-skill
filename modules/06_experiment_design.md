# Finite serial experiments

Read the current B/C/D evidence and independently frozen E protocols first. This
module reviews a finite catalog and executes its members through the existing E
runner. It never substitutes a new parameter value into an approved C/D/E model.

Use `core/experiment_design.schema.yaml` and
`templates/experiment/experiment_design.yaml`. An incomplete draft is inspectable,
but cannot grant execution. Bind factor levels, categorical probabilities and
the complete sampling/event/budget settings to actual project source records.
Review the semantic digest using a separately recorded, exact decision quote.
All members must share the approved model and configuration. Only declared
constant external input factor values may differ. New parameters require a new
C approval, D implementation and E protocol.

The implemented methods are `scenario_matrix`, `full_factorial` and
`monte_carlo_catalog`. Full factorial means an ordered Cartesian catalog of one
or two factors with two to four levels each. Monte Carlo means fixed-size iid
categorical selection over this finite catalog, with at most 16 draws. Record
the probability role and its source; a declared design law is not evidence of a
real-world frequency. Continuous distributions, LHS, correlated sampling,
parallelism and adaptive stopping remain deferred.

Inspect with `resolve_runtime.py --intent experiment_design --experiment-design
PATH`. Review a complete, source-bound design before requesting
`--intent experiment_campaign`. Supply current A, E and G profiles. G qualifies
only sample generation; actual execution also requires A core and each required
operation, the E `ode4` operation and every member's current frozen protocol.
List actual statistics dependencies using `--require-operation`; the overall A
core result cannot stand in for `fitlm`, `lhsdesign` or `normcdf` results.

`run_experiment.py` validates the entire catalog before creating a new campaign
directory. It uses a local `RandStream('mt19937ar', 'Seed', seed)` without changing
the caller's global stream. It preserves uniforms, draw indices and order;
repeated selections receive independent E attempts, directories and receipts.
Execution is serial. The first technical failure, timeout, source drift,
admissibility failure or budget failure stops execution and preserves a partial
ledger. Remaining draws are unattempted and the complete summary is absent.

E metric admissibility and the G event threshold serve different purposes. A
valid draw that exceeds the event threshold remains in the denominator. Only a
complete fixed-size campaign may report statistics. Monte Carlo reports `k/n`
and a nominal 95% Wilson interval. This interval describes the declared iid
categorical experiment and does not establish precision, convergence, physical
validity or reliability. Zero events in 16 draws still has an upper Wilson bound
of about 0.194. Scenario matrices and grids receive no Monte Carlo interval.

Use `validate_experiment_receipt.py` to independently read every E receipt and
raw metric before `campaign_review`. Optional state anchors are
`experiment_design`, `campaign` and `experiment_environment`; stages are
`EXPERIMENT_DESIGN_REVIEWED` and `CAMPAIGN_COMPLETE`. Historical execution checks
qualification TTL at execution time while always checking current source bytes.
This branch does not write project state, primary-run anchors or model files.
H numerical verification, I physical validation and accepted-paper claims remain
separate gates.
