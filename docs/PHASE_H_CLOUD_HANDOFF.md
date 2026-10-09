# Phase H cloud handoff

Work on `phase-h/verification-evidence`, never directly on `main`. The reviewed
implementation baseline is commit `fdd09cb3f5c37da5a8454ecfbf767d9da4fd4011`, tree
`5eee6fa6a5e12f5043c46775b25e067a7d5905fc`. The plan-first §12.19 commit is
`21c6e6de93c3f410748f7356f1626f811841c03a`, tree
`df469a88fefe935146b1c9970e785987c941d7e6`. Root supplies the exact independently
reviewed handoff commit/tree with the cloud task; verify that pin and these
ancestors before editing. This document and the plan do not verify behavior.

Read `AGENTS.md`, `DEVELOPMENT_GOVERNANCE.md`, `core/bootstrap.yaml`, Full Plan
§§12.9–12.19, both H contracts, shared verification schema and modules 07/08.
The latest plan controls the pending fix. User authorization covers bounded H,
not I–K, deployment, release/tag/install, real human Model Approval, physical
validation, automatic model adoption or project state promotion.

## Execution boundary

On 2026-10-09 two actual desktop `codex cloud exec` attempts exited 1 with
`no cloud environments are available for this workspace`; authenticated
environment lists returned HTTP 200 with no entries. No task was submitted.
The user sees the cloud “Start a new task” interface; that observation does not
establish submission, access to this branch or MATLAB availability.

In an actual managed cloud task, first read the available
`cloud-environment:cloud-environment-runtime` skill and inspect the real
environment, policies, checkout and installed tools. Record facts, not assumed
Windows paths. Run one job at a time, constrain work to two logical CPUs when
supported, and set OMP/MKL/OpenBLAS/NumExpr numerical threads to 1. Use Python
`-B`/UTF-8; preserve complete command, exit, logs, XML and exact source identity.
Wait for unrelated computations to finish; do not kill unknown processes.

Cloud can implement and test the Python fix first. Actual MATLAB work requires
genuinely available R2025b/Simulink 25.2, required products, executable identity
and fresh same-host/runtime operation qualification. Windows profiles/receipts
cannot qualify a different cloud host. If unavailable, leave native gates
pending for the desktop serial queue; do not simulate their completion.

## Historical evidence and current blocker

These are inspected **historical Windows results at fdd09cb**, not results of
this document, a future source fix or cloud execution:

- Final full suite: 1404 passed, actual exit 0, XML failures/errors/skipped 0.
- E/F/G native qualification: 9/11/18 cases passed, equal 103-file source closure.
  Legacy positive regressions and controlled negatives completed; independent
  original G raw audit passed on 15 distinct E attempts, preserving 67 originals.
- Independent H v3: two actual D builds, eight E runs (five direct plus three
  complete G members), one G campaign, three passing H1 receipts covering 4/1/3
  E runs. Raw mathematical audit and technical negative controls remain pending.
- H2 is technically blocked, not a completed business reject: six E ledger
  rows and three recomputed H1 receipts precede the G preflight failure;
  summary is null and evidence/decision/model_verified are false.

Independent read-only trace delegated the existing `Budget.charge` on every
call: 2384 attempted charges reached 67,131,394 B against 67,108,864 B (64 MiB).
Only 280 distinct physical files totalled 5,865,416 B. The 1,091,595 B Simulink
library and E qualification metadata were charged 14 times. `charge` hashes
from disk on each call; `read` then parses from disk again. Failure occurs in
`campaign_response` → `preflight_campaign` after repeated nested H1/E closures.
All 292 v3 files and source bytes remained unchanged in the diagnosis.

Desktop evidence is outside this repository and unavailable in a normal cloud
clone: `outputs/phase-h-implementation` contains the trace, failed H2, full logs,
original sealed materials and independent oracle. The facts here are context,
not replacement raw receipts or an oracle. Obtain the authorized originals for
any later original-task audit; do not fabricate, rebase or restamp old native
history. Preserve legacy1840, H v1 full99/v2 full268/v3 full292 and each original
21-file/5-mathematics-file set on the desktop.

## Original mathematics and unchanged criteria

This is **SYNTHETIC INFRASTRUCTURE ONLY**, with no measured data or real human
approval. Dynamic model: `x'=-a*x+b*u`, `y=x`; `a=0.8 1/s`,
`b=1.3 K/(s*V)`, `x(-1.5 s)=-2.4 K`, interval `[-1.5,1.5] s`, nominal constant
`u=1.7 V`. K denotes temperature difference. Independently approved static
model: `y=g*u`, `g=b/a=1.625 K/V`, no state; it removes relaxation/storage
and initial-state memory under the same physical input/time/output mapping.

| Frozen check | Original setting or criterion |
| --- | --- |
| Three separate ode4 protocols | h = 0.75, 0.375, 0.1875 s; 4, 8, 16 intervals |
| H1 absolute sample errors | coarse 0.01 K; medium 0.001 K; fine/catalog 0.0001 K; ode45 1e-6 K; static 1e-12 K; rtol=0 |
| ode45 protocol | max_step=0.1875 s, min_step=1e-8 s, initial_step=0.02 s, rel_tol=1e-9, abs_tol=1e-10 K |
| Refinement and actual ode4/ode45 terminal difference | each ≤0.004 K |
| Dynamic/static terminal difference | ≤0.3 K; required mechanism comparison |
| Complete ordered input catalog | u = [-0.4, 1.7, 3.2] V; ode4 h=0.1875 s; unchanged a,b,x0 |
| Scenario / finite robustness terminal thresholds | every y≤5 K / every y≤4 K |
| Separate E admissibility | terminal y in [-10,10] K |

Independent reference is `b*u/a+(x0-b*u/a)*exp(-a*(t-t0))`; the pre-sealed
60-digit Decimal oracle and independently derived RK4 polynomial predict
finite recorded samples. Product H values are audit subjects, not references.
Current historical terminal solver difference is 0.002011566011655308 K;
dynamic/static difference is 0.4683314340882938 K and catalog maximum is
4.510535642984567 K. Thus unchanged business criteria should yield a complete
H2 **reject** after the technical blocker is fixed, not MODEL_VERIFIED.
Withdraw unsupported claims or obtain a newly reviewed revision returning to
C; keep all members and primary artifacts. Technical E/H1 failure instead
blocks with partial evidence. Never loosen criteria, reduce domain or modify
sealed inputs/oracle to obtain support. No continuous-domain, uncertainty,
physical-validity or automatic-adoption claim is authorized.

## Pending bounded fix and gates

Implement §12.19 operation-local immutable raw-byte capture in `Budget`:
canonical paths, captured SHA/stat identities, pre-allocation per-file/total
checks, fresh strict document decoding, every first/late SHA declaration,
alias/containment guards and uncached fresh completion SHA reads. No mutable
document or validation-result cache. Route H-controlled direct document/text
reads through captured bytes. Preserve §12.17 selected-output role/shape
checks, §12.18 authenticated D archive/current roles, and complete live D/E/G/H1
historical consumers. Their extra I/O and SciPy allocations are not a measured
process-wide I/O/memory guarantee; state the narrower capture-plus-completion
budget and charge every fresh verification read honestly.

Keep 16 MiB/file, shared 64 MiB, cooperative 120 s, two signals, 301 samples and
existing run/model/scenario limits. Strict interruptible deadlines, decompressed
memory and process-total I/O guarantees remain unsupported required checks.
Protect A7/B2/D19 (23 unique files) byte-for-byte against main
`719495b745facce688810a62c2c1d3c7aea9116f`, especially `runtime_common.py`.
Keep E/F/G/H source closures equal and covering all changed safety dependencies.

Proceed serially through:

1. Bounded implementation plus small meaningful positive/negative tests for
   cache reads, caps before allocation, parser semantics/mutation isolation,
   first/late SHA conflicts, missing/growing/replaced/same-size changed files
   including restored mtime, aliases, fresh finish accounting, nested shared
   Budget/time and retained selected-output/D-role gates. Run focused and
   relevant route/state/static checks, regenerate/check indexes, and commit.
2. Exact-source/protected/original preservation proof and independent review
   before a final full suite. Read complete exit/XML/counts; no repeated full
   run without a changed source or failed/unresolved gate.
3. Fresh affected final-source E/F/G qualifications, legacy regressions, new
   original native v4 D/E/G/H1/H2 chain, independent MAT/JSON/CSV mathematical
   audit, strict H1 criterion failure and same-project partial G → H2 blocking.
   A/D reuse on the original host requires current identity/TTL checks; actual
   fitlm/lhsdesign/normcdf qualifications remain explicit, never inferred from
   `--include-statistics` overall success. No native gates can be waived for
   absent cloud MATLAB or missing original evidence.
4. Root independently integrates and reviews cloud commits/diff, performs
   final exact-head review and Windows/Ubuntu CI, then reviewed PR/merge and
   main readback/CI. Do not automatically merge from cloud, push protected main,
   deploy, tag, release or install. Return exact commits/tree, commands, actual
   results and pending limitations; Python or document checks alone are not H exit.
