# R2025b finite catalog adapter

This adapter uses actual MATLAB batch execution. It does not install or qualify
the upstream MCP Toolkits. Every frozen catalog member uses the existing public
E runner, its individual qualified solver and its own complete numeric receipt.
G's independent qualification covers sample generation only.

The finite categorical sampler uses the R2025b
[`RandStream`](https://www.mathworks.com/help/releases/R2025b/matlab/ref/randstream.html)
constructor with an explicit `mt19937ar` seed and
[`rand(stream,n,1)`](https://www.mathworks.com/help/releases/R2025b/matlab/ref/double.rand.html).
It does not set the caller's global stream. Qualification separately exercises
owned temporary caller overrides and verifies their final restoration, including
State, NormalTransform, Antithetic and FullPrecision. State words are serialized
as unsigned decimal integers using
[`sprintf('%u',...)`](https://www.mathworks.com/help/releases/R2025b/matlab/ref/string.sprintf.html).

Numeric MAT inputs and outputs are real double columns; deterministic uniforms
are `0 x 1`. JSON record arrays preserve empty, singleton and multiple records.
The independent consumer checks storage class, complex flags, dimensions and
actual values across MAT/JSON/raw, then recomputes catalog selection and summary.
Unsupported or damaged MAT decoders yield a recorded invalid result. Native
process failures and partially generated outputs retain their original bytes and
failed receipt wherever storage permits sealing it.

Continuous sampling, `lhsdesign`, correlated laws, `parsim` and acceleration are
deferred. A task that independently requires `fitlm`, `lhsdesign` or `normcdf`
must explicitly require and inspect the corresponding A operation. Successful
core qualification alone does not validate optional Statistics operations.
