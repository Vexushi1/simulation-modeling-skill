# MathWorks adapter boundary

The official [Simulink Agentic Toolkit](https://github.com/matlab/simulink-agentic-toolkit/tree/c58e6aec7b904769ae43536e169d747feda95416) is pinned to release commit `c58e6aec7b904769ae43536e169d747feda95416` (`2026.10.a`). `upstream_pin.yaml` records exact skill, manifest, reference, tool-registration and license hashes from a live read-back on 2026-10-08. The companion MATLAB Toolkit commit is also pinned. These references do not establish a local installation.

`skill_mapping.yaml` maps actual upstream skill names to approved C needs. Local contracts retain mathematical identity, traceability and parameter provenance. The adapter supplies reference pointers and compatibility requirements; it does not execute upstream instructions, install toolboxes, change global MATLAB paths, or grant simulation permission.

The upstream skill manifests declare R2023a or later. R2025b lies in that range, but toolkit MCP tools still require operation-specific tests on the actual channel and installed resources. The active local fallback uses the independently qualified batch operation `simulink.core_build_structure`, with six controlled block types and save/reopen/update/readback assertions. A `simulink.library_load` result proves only the Phase A operation. Simscape, Stateflow, System Composer, other blocks, hierarchy builders and simulation remain deferred.

Upstream [license](https://github.com/matlab/simulink-agentic-toolkit/blob/c58e6aec7b904769ae43536e169d747feda95416/LICENSE.md) terms limit use to MathWorks offerings and require notices when redistributing. This adapter contains metadata and links; it vendors no upstream implementation.
