# Three-level refinement agreement

The [H1 module](../../modules/07_numerical_verification.md) controls this bounded evidence pack. For ode4, compare actual samples at every primary integer-grid point across h, h/2 and h/4. For ode45, compare only actual start/stop samples across simultaneous RelTol/AbsTol tightening by 10 and 100. Keep every physical/model/input setting fixed.

Declare mixed absolute/relative limits, contraction and a roundoff floor before reading results. Check the coarse primary's difference as well as the two fine levels. Preserve failed criteria and technical failure distinctly. Finite agreement and an empirical step order are not a true error bound, a general order proof or physical validation. Necessary residual, conservation, constraint, event or drift checks outside this implementation remain blockers.
