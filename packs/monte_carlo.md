# Finite categorical Monte Carlo

Use a reviewed finite E catalog and fixed `n <= 16`. Bind a finite nonnegative
probability vector whose accurate sum is exactly one to its source; never
normalize it silently. Declare whether it is given, assumed or a design law.
Use an explicit uint32 seed and local MATLAB `mt19937ar` stream. Save the actual
uniforms and inverse-CDF selections; preserve repetitions and order. A zero
probability member is never selected, including at uniform zero.

The G seed changes catalog selection only. It does not create independent
internal stochastic replications inside each E model. The initial branch does
not support continuous distributions, correlation, LHS, parallel workers or
adaptive convergence.

Declare the metric event comparison and threshold before review, separately from
E admissibility. Keep valid event samples in the denominator. Technical failures
stop the campaign and yield no complete summary. Complete campaigns report event
count `k`, fixed `n`, `k/n`, mean/min/max and the predeclared nominal 95% Wilson
interval using `z = 1.959963984540054`. The interval is conditional on the declared
iid categorical law and cannot establish physical validity or an acceptable
failure rate. Do not infer reliability from zero events in a small sample.
