# Upstream Integration Policy

## 1. Authorities

### Execution authority

Prefer current official MathWorks projects:

- `matlab/simulink-agentic-toolkit`
- `matlab/matlab-agentic-toolkit`

They provide low-level MATLAB/Simulink execution knowledge and MCP-backed capabilities.

### Competition methodology authority

This repository is authoritative for:

- task interpretation;
- simulation-model selection;
- fidelity decisions;
- evidence requirements;
- model verification strategy;
- competition delivery sequencing.

### General paper-writing authority

`Vexushi1/mathmodel-skill` remains the preferred external authority for complete competition-paper composition while this repository owns simulation-specific evidence and handoff.

## 2. Integration modes

Allowed:

- invoke upstream skill by name/capability;
- adapt upstream outputs into local evidence contracts;
- define preconditions and postconditions around upstream execution;
- add local gap-filling extensions when verified necessary.

Avoid by default:

- copying an entire upstream skill tree;
- modifying vendored official text in place;
- creating a second local API guide for the same MathWorks capability;
- mixing two MCP servers that expose overlapping mutation tools without a declared authority.

## 3. Third-party skills

Third-party skills are optional extensions.

Before admission, record:

- repository and commit/tag;
- license;
- supported MATLAB release;
- dependency/toolbox requirements;
- overlap with official capabilities;
- unique value;
- security/mutation surface;
- fallback if absent.

A third-party skill is not admitted merely because it has more tools.

## 4. Paper-writing integration

Default mode: `delegate`.

The simulation repository produces:

- problem/model summary;
- variable and parameter registry;
- final mathematical model;
- simulation configuration;
- numerical verification;
- sensitivity/robustness/model-comparison evidence;
- validation evidence;
- accepted figures/tables;
- claim boundaries.

The paper-writing skill consumes those artifacts.

No full paper-writing clone is maintained here unless an explicit independence requirement is approved in a later phase.

## 5. Drift control

For every upstream dependency, future implementation must support:

- pinned compatibility metadata;
- periodic compatibility review;
- local adapter tests;
- explicit handling of renamed/deprecated upstream skills;
- no silent fallback to stale copied guidance.
