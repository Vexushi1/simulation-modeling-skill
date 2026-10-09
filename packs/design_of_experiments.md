# Catalog design

Use the [experiment module](../modules/06_experiment_design.md) and current G
schema. Declare one or two external constant input factors, their units, source
selectors and finite levels. Freeze each E member independently. Scenario
matrix rows follow catalog order. A full-factorial catalog must equal the
ordered Cartesian product, with no missing or duplicate combinations.

All members share approved B/C/D evidence, exact parameters, initial and boundary
conditions, time, solver, logging, internal seed, metric definitions and warning
policy. Only the declared external factor values vary. Each campaign is bounded
to 16 draws, normal serial `ode4`, a 30-second simulation span, at most 3000 fixed
steps and two outputs. Each input has at most 301 samples and all inputs at most
602 samples, checked before sampling or simulation. Explicit process, campaign and artifact budgets
apply. Budget exhaustion preserves partial evidence and permits no complete
statistical conclusion. A new model parameter or solver requires a new upstream
contract rather than an experiment override.
