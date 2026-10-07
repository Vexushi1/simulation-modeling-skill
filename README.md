# Simulation Modeling Skill

Agent skill system for competition-oriented simulation modeling with **MATLAB R2025b** and **Simulink** as the primary runtime baseline.

## Project goal

Build a rigorous end-to-end simulation-modeling workflow that separates:

- problem interpretation and requirement freezing;
- mechanism/system abstraction and mathematical model design;
- MATLAB/Simulink/Simscape implementation;
- parameter identification, calibration and optimization;
- simulation experiment design, parallel sweeps and Monte Carlo studies;
- numerical verification, sensitivity, robustness and multi-model comparison;
- verification & validation;
- scientific visualization and paper evidence delivery.

## Architecture principle

This repository owns the **competition methodology, routing, evidence contracts and simulation-specific delivery logic**.

It does **not** duplicate upstream MathWorks Agentic Toolkit skills when an official skill already provides the execution capability. Instead, this project defines when and why those capabilities should be invoked.

The mature methodology and paper-writing rules in `Vexushi1/mathmodel-skill` are treated as design references. The simulation repository remains independently evolvable and does not require the math-modeling repository as a core runtime dependency.

## Runtime baseline

- Primary target: MATLAB R2025b
- Primary simulation backend: Simulink
- Optional capability backends: Simscape, Stateflow, System Identification, Optimization, Parallel Computing, Simulink Test and related products
- Statistics and Machine Learning Toolbox must not be assumed available unless runtime capability checks confirm its callable installation.

## Status

Repository bootstrap in progress. The canonical architecture and phased implementation plan will live under `docs/`.
