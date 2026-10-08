# Finite normalized-square SQP design optimization

Use operation `optimization.quadratic_sqp` for one or two current C optimized/assumed parameter variables with a research plan. Supply finite bounds and a feasible initial guess, each bound to a current structured C source. Pure design optimization has no invented observations: data is empty; input selection, sample_time, identifiability, training/holdout RMSE, condition criterion and simulation_timeout remain null.

Declare one ordered objective term per parameter: its current variable ID/unit, finite center, positive weight and scale, numerical source reference and actual task meaning. The source selection contains matching typed `center`, `weight`, `scale`, `unit`. The approved C objective is dimensionless and must match the restricted generated formula exactly after whitespace removal. Numbers use JSON spelling, including intentional integer/float distinctions:

```text
J=1.0*((x-(2.0))/(1.0))^2+1.0*((z-(2.0))/(1.0))^2
```

The center and scale have the selected parameter's unit. This is a declared normalized-square objective, not an arbitrary expression parser. The task meaning and reviewed C unit analysis remain necessary; exact formula matching does not prove physical appropriateness.

Each linear inequality has a finite coefficient row in parameter order, a finite rhs, its current C constraint relation ID and a structured source containing identical `coefficients` and `rhs`. Bind all constraint IDs in exact declared order. The supported relation spelling is:

```text
1.0*(x)+1.0*(z)<=3.0
```

An empty constraint array is valid. Additional C governing/constraint behavior is outside this kernel. Record a positive prior feasibility tolerance, finite process/iteration/evaluation budgets and warning policy. Actual `fmincon` serial SQP is separately qualified; function resolution, A core success and an installed Optimization Toolbox grant no F operation permission.

Capture actual objective calls, parameters, objective values, exitflag, termination, first-order optimality and evaluation counts. Independently recompute the chosen objective and bound/linear feasibility before candidate completion. Nonconvergence, infeasibility and budget exhaustion remain explicit failed/incomplete evidence. Local algorithm convergence does not itself prove global optimality; no Pareto, surrogate, global or multiobjective route is enabled.

Report the design candidate's value and scope limits. Its parameters enter the final model only through a new C review and real approval, updated D/E final evidence and later verification.
