# Simulation Modeling Skill v1.0.0 全流程实施计划

> **文档状态：CANONICAL IMPLEMENTATION PLAN（全量实施主计划，2026-10-08 Phase F实施前审查修订）**
> 仓库：Vexushi1/simulation-modeling-skill  
> 主目标版本：v1.0.0  
> 强运行基线：MATLAB R2025b + Simulink R2025b  
> 已完成阶段：A–D；D PR #5 合并基线 `91e6e1eb357511cf53562bac2055038ad68e3617`
> 当前下一阶段：E；实施分支 `phase-e/simulation-runtime`，未通过出口前不登记为已实现
> 核心纪律：先冻结计划，再按阶段实施；任何阶段不得脱离本计划直接堆功能。

---

# 0. 文档目的与执行纪律

本文件是 simulation-modeling-skill 从当前 bootstrap 状态演进到 v1.0.0 的**唯一全流程实施蓝图**。

它不是产品介绍，也不是功能愿望清单，而是后续仓库修改的工程 Authority。所有开发工作必须能够回答：

1. 本次修改属于哪个 Phase / Work Package；
2. 修改了哪个 Authority / Contract / Module；
3. 新增或改变了什么行为；
4. 产生什么可验证证据；
5. 通过什么 Gate 才允许进入下一阶段；
6. 若失败，应回退到哪个上游阶段。

## 0.1 计划优先级

在 v1.0.0 发布前，本计划的实施优先级高于：

- 临时聊天建议；
- 单个示例代码；
- 临时目录设计；
- 第三方 Skill 自带的流程顺序；
- 为赶进度而先实现再整理的快捷方式。

若后续确需调整本计划，必须按以下顺序：

~~~text
发现结构性问题
→ 明确影响范围
→ 先修改本计划
→ 记录变更原因
→ 再修改 Skill / Contract / Script / Test
~~~

禁止先改实现，再倒推计划。

## 0.2 分支与 PR 纪律

正式实现阶段遵循：

- main 只接受已经通过对应 Gate 的阶段成果；
- 每个 Phase 使用独立分支，必要时拆分为若干同主题 PR；
- 不允许把 Phase B–K 全部堆入一个巨型 PR；
- 任一 Authority 未冻结前，不构造依赖它的下游正式 Contract；
- 修复旧 Phase 的语义问题时，必须明确 stale 传播范围；
- 每个 PR 必须说明 Scope、Authority Changes、Behavior Changes、Evidence、Compatibility、Stale Impact、Deferred。

推荐阶段分支：

~~~text
bootstrap/v0.1.0-architecture
phase-a/runtime-governance
phase-b/problem-audit
phase-c/model-design
phase-d/simulink-mapping
phase-e/simulation-runtime
phase-f/identification-calibration-optimization
phase-g/experiment-design
phase-h/model-verification
phase-i/verification-validation
phase-j/evidence-paper
phase-k/release-qualification
~~~

---

## 0.3 2026-10-07 审查修订记录

用户授权先审查计划，必要时先改计划再实施。本次保留独立仓库、R2025b、官方执行适配、证据链和 A–K 顺序，修订以下不合理或不明确的规则：

1. 分离仓库开发资格与项目运行状态，避免计划中的阶段自动变成已实现能力。
2. 将能力资格限定到具体操作，增加当前 probe、字节绑定、时效和透明执行通道，避免静态清单或库加载冒充全部仿真资格。
3. 补齐 Phase A 自举所需的 probe、schema、索引、测试依赖和 CI；未实现模块保持 deferred，禁止空文件占位。
4. 将机械双模型和固定假设数量改为按信息需求审查，保留正式结构对照裁决和证据要求。
5. 将参数来源分类与可信度评价分开，补齐数据、参数、场景、运行环境的依赖失效规则。
6. 明确候选/标定运行与最终主证据的区别；按需分析必须保留决定与理由，验证主张不得超过证据范围。
7. 阶段验收必须有可执行正常/失败检查和对应运行证据；本地通过、CI、PR 合并与发布分别报告。

导航链接可以双向，Authority 优先关系和运行依赖必须单独登记并保持无环；不把普通链接环误判为 Authority 环。本次先以计划修订提交保存这些决定，再修改 Phase A 实现。

## 0.4 Phase B 实施前审查

用户继续授权下一步修改。Phase A PR #1/#2 已合并，main `6f8634314909d669c5758bb41fcc17faa4892ab3` 的 CI、源码与本机证据回读通过。Phase B 在独立分支实施，先作如下修订：

- 题意审查可以从 NEW 开始，不以 MATLAB 当前资格为前提；运行环境只控制需要它的执行。
- B 冻结题意与已给条件，不强迫确定 C 才产生的完整模型状态、抽象对象或数学结构。
- 原文件/审阅文本身份、逐字覆盖、引用、数据使用范围、依赖 DAG、关键歧义和审查决定必须可校验。
- 同一物理量可以有多个明确关联的角色；不机械要求所有角色互斥。
- 项目 frozen Gate 与仓库 B 开发验收分开；保留关键审查决定，验证器不自动生成冻结决定或修改状态。
- 题面或审查决定变化使问题及其依赖失效；环境 TTL 不使未变的问题语义失效。

## 0.5 2026-10-08 Phase E 实施前审查摘要

用户继续授权下一阶段，要求先读计划、必要时先修订，再实施并独立复核。D 已在独立 PR #5 完成最终源码、实际 R2025b 结构资格、独立审查、双平台 CI 与合并回读。原 §9 只有 solver/协议字段与推荐 API，缺少协议冻结消费者、真正的仿真操作资格、历史运行身份、状态和可执行出口，不能据此直接开放仿真。

本次先补 §9.9：E 只开放当前 D 六类核心 block 的受控标量 Simulink 普通串行仿真，区分当前执行资格与历史 receipt，补齐协议/运行/状态消费者及真实正反例。仿真成功仍不代表 H 的数值验证、I 的现实有效性或 J 的成果验收。保留 A 七个 source-identity 文件、B schema/validator 与 D 十九个资格源码文件，避免为拓展 E 而使已验证的 D 身份失效。

用户同时指出 `--include-statistics` 的整体核心通过容易被误读。本次不改变 A 的可选探测语义；只修正使用说明，并要求 E 将实际依赖的 `statistics.fitlm`、`statistics.lhsdesign` 或 `statistics.normcdf` 明确传播为 required operations。必须消费该项的实际资格，不能用整体通过替代。先保存这些计划决定，再修改契约与实现。

# 1. 已冻结的顶层决策

以下决策视为 v1.0.0 的已确认前提，后续不重复讨论，除非出现新的硬约束。

## 1.1 仓库定位

本仓库定位为：

> **面向仿真建模竞赛的上层方法论、工作流、路由、验证与交付系统。**

它不是：

- Simulink API 手册；
- 模块拖拽助手；
- MATLAB 代码片段合集；
- 某一具体学科毕业设计模板；
- 数学建模 Skill 的子目录。

目标闭环：

~~~text
逐字审题
→ 系统边界与任务冻结
→ 数学/物理模型设计
→ 模型路线比较
→ MATLAB/Simulink/Simscape/Stateflow 实现
→ 仿真实验设计
→ 参数辨识/标定/优化
→ 数值正确性检验
→ 灵敏度/鲁棒性/不确定性
→ 多模型与多求解器对照
→ Verification & Validation
→ 科研图表证据
→ 论文证据包
→ 论文交付
~~~

## 1.2 MATLAB R2025b 为强基线

v1.0.0 不采用“尽量兼容所有 MATLAB”的策略。

强基线：

~~~text
MATLAB R2025b
Simulink 25.2
Windows 为首要资格验证平台
~~~

约束：

- 所有主动推荐 API 必须能够在 R2025b 使用或有 R2025b 等价实现；
- R2026a 新 API 不得直接进入 active path；
- 上游 Skill 声明 >=R2023a 只表示最低范围，不替代本仓库的 R2025b 组合验证；
- 旧版本兼容放到 v1.0.0 之后单独设计 compatibility profile。

## 1.3 Toolbox 使用策略

核心硬依赖只保留：

- MATLAB；
- Simulink。

其余按能力路由，不因“已安装”就全量加载。

当前重点能力矩阵：

### 数值与优化

- Optimization Toolbox
- Global Optimization Toolbox
- Parallel Computing Toolbox
- Symbolic Math Toolbox
- Curve Fitting Toolbox
- Partial Differential Equation Toolbox

### 控制、辨识与鲁棒性

- Control System Toolbox
- Robust Control Toolbox
- Model Predictive Control Toolbox
- System Identification Toolbox
- Model-Based Calibration Toolbox

### 统计与机器学习

- **Statistics and Machine Learning Toolbox：当前已恢复为可调用能力。**

实施前的 bootstrap 文件保留旧 quarantine 记录，因此 Phase A 的第一项正式修复就是：

1. 删除旧 quarantine 状态；
2. 将该工具箱纳入候选能力矩阵，以当前 probe 的实际调用证据决定 callable；
3. 增加 runtime probe，未来以当前检测结果为准；
4. 不再永久硬编码历史故障状态。

本计划写入阶段不修改旧 baseline，避免边写计划边改实现。

### 仿真与物理建模

- Simscape
- Simscape Battery
- Simscape Driveline
- Simscape Electrical
- Simscape Fluids
- Simscape Multibody
- Stateflow
- SimEvents
- System Composer

### Simulink 高级验证与设计

- Simulink Control Design
- Simulink Design Optimization
- Simulink Test
- Simulink Coverage
- Simulink Design Verifier
- Simulink Check
- Simulink Fault Analyzer
- Simulink Coder
- Embedded Coder

## 1.4 MathWorks 官方 Agentic Toolkit 的职责

优先对接：

- matlab/simulink-agentic-toolkit
- matlab/matlab-agentic-toolkit

原则：

> 本仓库负责“为什么做、什么时候做、做完要证明什么”；官方 Toolkit 负责“具体如何操作 MATLAB/Simulink”。

职责边界：

~~~text
simulation-modeling-skill
负责：
- 任务理解
- 模型路线选择
- Fidelity 选择
- 验证策略
- 证据结构
- Claim 边界
- 回退逻辑

MathWorks Agentic Toolkit
负责：
- Model 编辑
- MATLAB 执行
- Simulink 仿真
- 工具箱级 API
- 测试与检查
- 官方产品最佳实践
~~~

不批量复制官方 Skill，避免：

- 上游版本漂移；
- 规则重复；
- stale API；
- License 风险；
- 双重 Authority。

## 1.5 与 mathmodel-skill 的关系

Vexushi1/mathmodel-skill 作为：

> **方法论来源 + 论文写作 Authority 参考。**

但不是本仓库核心 runtime dependency。

只迁移：

- 逐字审题思想；
- Problem Contract；
- Question Dependency DAG；
- Model / Solver / Validator 分离；
- Model Challenge / Approval；
- 主计算数值有效性与结果深化分析分层；
- 多模型 / 多算法检验；
- Result → Evidence → Claim；
- Figure Admission；
- Paper Writing Reasoning；
- Final Review / Submission Gate。

不迁移：

- 与仿真无关的全部 Pack；
- 双后端治理；
- 无必要的旧状态机细节；
- 整套论文写作目录的直接复制。

## 1.6 论文交付策略

v1.0.0 默认：

> **Simulation Evidence Package + Paper Handoff + 外部成熟写作 Skill。**

本仓库负责：

- 仿真问题分析素材；
- 模型建立与推导；
- 状态/参数/单位表；
- Simulink 架构说明；
- Solver 选择与理由；
- 结果；
- 数值检验；
- 灵敏度；
- 鲁棒性；
- 多模型对照；
- V&V；
- 图表；
- Claim Boundary；
- 模型优缺点和适用范围。

完整论文优先交给 mathmodel-skill 写作模块。

未来若明确要求本仓库完全离线独立写论文，再引入受控 snapshot 或 adapter，不在 v1.0.0 前期复制整套写作系统。

---

# 2. v1.0.0 目标能力边界

## 2.1 必须覆盖的仿真题型

### 动态系统

- ODE；
- DAE；
- 状态空间；
- 传递函数；
- 非线性状态方程；
- 连续—离散混合系统。

### 控制系统

- 开环 / 闭环；
- PID 与变体；
- 状态反馈；
- LQR / LQG；
- MPC；
- 鲁棒控制；
- 跟踪；
- 扰动抑制；
- 稳态与瞬态性能。

### 混合逻辑系统

- Stateflow；
- 事件触发；
- 状态切换；
- 故障模式；
- 保护逻辑；
- 离散控制逻辑。

### 多物理场

- 机械；
- 电气；
- 热；
- 流体；
- 电池；
- 驱动；
- 多体；
- 跨域 Simscape 网络。

### 数据驱动动力学

- 线性系统辨识；
- 非线性系统辨识；
- 参数辨识；
- 校准；
- 代理模型；
- 数据辅助机理模型。

### 仿真优化

- 参数优化；
- 控制器调参；
- 设计参数寻优；
- 约束优化；
- 多目标优化；
- 全局优化；
- 昂贵仿真代理优化。

### 不确定性与可靠性

- 参数扰动；
- Monte Carlo；
- 场景压力；
- 故障注入；
- 可靠性评估；
- 安全边界；
- 失效阈值。

## 2.2 v1.0.0 不追求

- 完整替代 MathWorks 文档；
- 对所有 Blockset 做百科全书；
- 支持所有旧 MATLAB；
- 把所有行业知识硬编码进核心 Skill；
- 自动宣称物理模型正确；
- 只靠视觉判断波形正确；
- 只要 Simulink 能运行就判任务完成。

---

# 3. 目标仓库结构

预计 v1.0.0 活跃结构：

~~~text
simulation-modeling-skill/
│
├── SKILL.md
├── README.md
├── manifest.yaml
├── AGENTS.md
├── DEVELOPMENT_GOVERNANCE.md
├── REPOSITORY_INDEX.md
├── SKILL_FILE_INDEX.md
├── CHANGELOG.md
├── LICENSE
│
├── core/
│   ├── bootstrap.yaml
│   ├── environment_baseline.yaml
│   ├── capability_taxonomy.yaml
│   ├── runtime_assurance_contract.yaml
│   ├── workflow_router.yaml
│   ├── module_manifest.yaml
│   ├── problem_contract.schema.yaml
│   ├── model_contract.schema.yaml
│   ├── model_approval_contract.yaml
│   ├── simulation_protocol.schema.yaml
│   ├── parameter_provenance.schema.yaml
│   ├── experiment_design.schema.yaml
│   ├── numerical_verification_contract.yaml
│   ├── model_verification_contract.yaml
│   ├── validation_contract.yaml
│   ├── evidence_contract.yaml
│   ├── paper_handoff_contract.yaml
│   ├── project_state.schema.yaml
│   ├── output_contract.yaml
│   └── upstream_integration_policy.md
│
├── modules/
│   ├── 01_problem_audit.md
│   ├── 02_model_design.md
│   ├── 03_domain_mapping.md
│   ├── 04_simulation_protocol.md
│   ├── 05_identification_calibration_optimization.md
│   ├── 06_experiment_design.md
│   ├── 07_numerical_verification.md
│   ├── 08_model_verification.md
│   ├── 09_validation.md
│   ├── 10_figure_evidence.md
│   └── 11_paper_delivery.md
│
├── adapters/
│   ├── mathworks/
│   │   ├── simulink_agentic_toolkit.md
│   │   ├── matlab_agentic_toolkit.md
│   │   ├── skill_mapping.yaml
│   │   └── compatibility.yaml
│   ├── paper/
│   │   └── mathmodel_skill_handoff.md
│   └── community/
│       └── registry.yaml
│
├── packs/
│   ├── domain/
│   │   ├── control_system.md
│   │   ├── physical_system.md
│   │   ├── hybrid_system.md
│   │   ├── electrical_system.md
│   │   ├── thermal_fluid_system.md
│   │   ├── multibody_system.md
│   │   └── data_driven_dynamic_system.md
│   ├── task/
│   │   ├── parameter_identification.md
│   │   ├── calibration.md
│   │   ├── optimization.md
│   │   ├── uncertainty.md
│   │   └── reliability_safety.md
│   └── evidence/
│       ├── convergence.md
│       ├── sensitivity.md
│       ├── monte_carlo.md
│       ├── model_comparison.md
│       ├── solver_comparison.md
│       └── validation.md
│
├── templates/
│   ├── project/
│   ├── contracts/
│   ├── matlab/
│   ├── simulink/
│   ├── experiment/
│   ├── evidence/
│   └── paper_handoff/
│
├── scripts/
│   ├── resolve_runtime.py
│   ├── validate_environment.py
│   ├── validate_problem_contract.py
│   ├── validate_model_contract.py
│   ├── validate_simulation_protocol.py
│   ├── validate_evidence.py
│   ├── validate_project_state.py
│   ├── lint_skill.py
│   └── sync_project.py
│
├── tests/
│   ├── test_runtime.py
│   ├── test_problem_contract.py
│   ├── test_model_contract.py
│   ├── test_router.py
│   ├── test_evidence_contract.py
│   ├── test_upstream_mapping.py
│   └── fixtures/
│
├── examples/
│   ├── first_order_control/
│   ├── nonlinear_dynamic_system/
│   ├── simscape_physical_system/
│   ├── parameter_identification/
│   └── monte_carlo_validation/
│
└── docs/
    ├── CANONICAL_ARCHITECTURE.md
    ├── V1_IMPLEMENTATION_ROADMAP.md
    ├── V1_FULL_IMPLEMENTATION_PLAN.md
    ├── R2025B_QUALIFICATION.md
    ├── TOOLBOX_CAPABILITY_MATRIX.md
    ├── UPSTREAM_COMPATIBILITY.md
    └── RELEASE_CHECKLIST.md
~~~

原则：

> 先有 Authority，再有 Consumer；先有 Contract，再有 Validator；先有模块语义，再有模板与示例。

---

# 4. 总体运行状态机

以下是单个建模项目的目标运行状态链，不是仓库开发 Phase A–K 的完成状态。开发阶段只登记已实现且测试通过的能力；未实现的项目状态可以保留在目标图中，但不得被当前 router 激活或通过。Phase A 实现 NEW 与 ENVIRONMENT_ASSURED；Phase B 增加 PROBLEM_AUDITED 与 PROBLEM_FROZEN；Phase C 增加 MODEL_PROPOSED、MODEL_CHALLENGED 与 MODEL_APPROVED，不另造 MODEL_DESIGNED 状态；已完成 D 增加 IMPLEMENTATION_READY。E 本次拟增加 SIMULATION_PROTOCOL_FROZEN 与 PRIMARY_RUN_COMPLETE，须通过 §9.9 后才成为实际能力。下图是典型工作顺序，纯文本审题可以从 NEW 开始；环境 readiness 与题意/模型状态独立，问题冻结和模型批准都不授予数值执行许可。

主状态链：

~~~text
NEW
↓
ENVIRONMENT_ASSURED
↓
PROBLEM_AUDITED
↓
PROBLEM_FROZEN
↓
MODEL_PROPOSED
↓
MODEL_CHALLENGED
↓
MODEL_APPROVED
↓
IMPLEMENTATION_READY
↓
SIMULATION_PROTOCOL_FROZEN
↓
PRIMARY_RUN_COMPLETE
↓
NUMERICALLY_VERIFIED
↓
MODEL_VERIFICATION_DECIDED
↓
MODEL_VERIFIED
↓
VALIDATED
↓
EVIDENCE_ACCEPTED
↓
PAPER_HANDOFF_READY
↓
DELIVERABLE_READY
~~~

典型回退：

~~~text
结果异常
→ numerical_verification

模型结构被否证
→ model_design

题意/边界改变
→ problem_audit

参数识别失败
→ identification/calibration

验证数据不支持 claim
→ claim modify / model redesign

Simulink 实现错误
→ domain mapping

solver 不稳定
→ simulation protocol
~~~

禁止：

- 模型错了只调 solver；
- 数据不支持却只改论文措辞保留强 claim；
- 状态方程变化后复用旧 accepted 结果；
- 边界条件变化后不使下游仿真 stale。

---

# 5. Phase A — Runtime、治理与仓库可信根

## 5.1 目标

建立后续所有 Phase 可依赖的唯一可信根。

## 5.2 先处理 bootstrap 遗留问题

### A-01 Statistics Toolbox 状态修正

正式实施 Phase A 时：

- 删除旧 quarantined 记录；
- baseline 只声明候选能力与检测策略，不永久写死 available/callable；
- 用当前 probe 的实际调用结果写入能力 profile；失败时明确 unavailable/fallback，下一次成功检测可恢复；
- 增加 runtime capability probe；
- 未来 capability 以当前检测为准；
- 不永久硬编码旧故障。

`--include-statistics` 会探测三项统计操作，但它们默认不是仅需 MATLAB/Simulink 核心环境的必需项；某项失败时整体核心仍可通过。比赛任务实际依赖哪个函数，就将该 operation ID 通过可重复的 `--require-operation` 明确列为必需，并检查该项 call/assertion/qualified 结果。整体通过、某项成功或已安装工具箱都不能证明另外几项已经通过；一次失败也不等于统计工具箱整体不可用。

### A-02 Roadmap 与 Full Plan Authority

- docs/V1_IMPLEMENTATION_ROADMAP.md：摘要；
- docs/V1_FULL_IMPLEMENTATION_PLAN.md：详细实施 Authority。

README 和 Index 后续明确该层级。

## 5.3 文件计划

新建：

- core/bootstrap.yaml
- core/runtime_assurance_contract.yaml
- core/workflow_router.yaml
- core/module_manifest.yaml
- core/project_state.schema.yaml
- core/output_contract.yaml
- SKILL_FILE_INDEX.md
- AGENTS.md
- scripts/resolve_runtime.py
- scripts/validate_environment.py
- scripts/validate_project_state.py
- scripts/lint_skill.py
- tests/test_runtime.py
- tests/test_router.py
- core/capability_profile.schema.yaml
- scripts/probe_environment.py
- scripts/matlab/probe_environment.m
- scripts/runtime_common.py
- scripts/generate_indexes.py
- tests/test_project_state.py
- tests/test_lint.py
- tests/conftest.py（仅在共享 pytest fixture 确有需要时创建，不创建占位）
- .github/workflows/ci.yml
- .gitignore
- .gitattributes（统一源码换行，保证 Windows/Linux 的源码身份可复核）
- requirements.txt
- pyproject.toml

修改：

- core/environment_baseline.yaml
- manifest.yaml
- SKILL.md
- README.md
- REPOSITORY_INDEX.md
- docs/V1_IMPLEMENTATION_ROADMAP.md
- docs/CANONICAL_ARCHITECTURE.md
- DEVELOPMENT_GOVERNANCE.md

Roadmap、架构与治理的修改限于此次审查确认的语义一致性和 Authority 衔接。测试依赖、索引生成器与 CI 是 Phase A 验收所需；不创建 B–K 的占位模块、业务模板或示例目录。

## 5.4 Capability Assurance

至少区分：

~~~text
declared
installed
licensed
callable
qualified
selected
~~~

解释：

- declared：计划或配置声明；
- installed：MATLAB 实际识别；
- licensed：许可可用；
- callable：某项具体操作已实际调用成功；函数路径存在只属于 resolvable；
- qualified：该操作通过本仓库指定 probe 的输入、断言与 R2025b 检查，必须注明操作、输入范围和执行通道；
- selected：当前任务实际采用。

运行时路由以 callable/qualified 为核心，不用 license 单独判能力。

产品 inventory、license test、实际调用后的 license inuse 分开记录。不得从某个产品的一项成功操作推导其所有 API 都 qualified。Phase A 的 qualification_scope 只包含 MATLAB 基础调用、Simulink 官方库加载，以及按需检测的 Statistics 三项最小操作；库加载不能使 simulation_execution qualified。Phase E 与 Phase K 分别负责业务仿真和端到端资格。

能力证据由 repository probe 生产，记录 UTC 时间、实际 runtime 身份、平台/宿主指纹、probe 与合同源码哈希、确定性输入、逐项输出/错误及独立进程退出记录。Python runner 将原始报告、规范化 profile 和日志绑定到 receipt；validator 检查这些字节身份与逐项断言，不接受仅手填 qualified=true、status=passed 或 exit_code=0。

profile 默认有效期为 24 小时。未来时间、非法起止顺序、未完成或失败进程、宿主/runtime 不符、输入或绑定文件变化、过期记录均失效。显式检测与重检使用独立输出目录；不覆盖历史证据。无 MCP 时可以透明采用独立 matlab_batch 通道，资格范围不得写成 MCP 已连接。可选 Statistics 失败不阻断仅需 MATLAB/Simulink 核心操作的环境保障。

## 5.5 Runtime Router

输入：

- user intent；
- project state；
- capability profile；
- existing artefacts；
- current problem/model/protocol status。

输出：

- activated modules；
- activated packs；
- upstream skills；
- required gates；
- expected artefacts；
- fallback route。

module manifest 区分 implemented 与 deferred。当前只有 environment assurance 可执行；B–K 请求必须返回 deferred、具体原因、前置 Gate 与下一阶段，不返回可执行计划，也不加载不存在的模块/上游 skill。environment inspect 是只读意图，不要求已有 profile，不能推进项目状态。环境保障只选核心与用户本次显式所需的可选操作，selected 属于本次 route decision，不写回探测 profile。

Phase A project state 验证器只验收已实现的状态和被哈希绑定的当前环境证据。目标状态链的下游状态不是本阶段可以手填通过的状态；状态同步不由 resolver 自动完成。

## 5.6 Phase A 测试

- YAML 可解析；
- active path 全部存在；
- Authority 无循环；
- R2025b baseline 一致；
- Statistics Toolbox 状态正确；
- upstream repo 名称一致；
- router 不加载无关工具箱；
- capability missing 有 fallback；
- project state 合法；
- stale 状态可验证。
- profile/receipt/raw report 不一致、许可真但实际调用失败、伪造 qualified、过期/未来时间、错误宿主或源码变更均不能通过；
- optional capability 缺失有明确失败与回退，核心环境可独立通过；
- deferred 能力、未满足 Gate 和 inspect 请求都不能获得业务执行权限；
- CI 分开静态/模拟 fixture 检查与本机 R2025b qualification，不把无 MATLAB 的 CI 写成 runtime 已通过。

## 5.7 Exit Gate

~~~text
runtime_assured = true
authority_graph_valid = true
capability_profile_current = true
router_smoke_test = passed
~~~

满足后进入 Phase B。

四项 Gate 的本机证据与最终源版本必须一致；本地测试通过只是实现验收，正式阶段完成还要求独立 PR 审查、对应 CI 成功与合并后的回读。bootstrap PR 未合并时 Phase A 可以用明确依赖它的独立堆叠 PR，不为开始实施而绕过上游审查。阶段之间的 Gate 以产物/行为/证据/回退的审查结果为准；后续 Phase 开始前必须将其 Gate 细化为可执行检查，不能凭文档数量或实现者声明通过。

---

# 6. Phase B — 仿真逐字审题与 Problem Contract

## 6.1 目标

将 mathmodel-skill 的“先冻结题意，再设计模型”改造成仿真专用审题层。

## 6.2 禁止事项

本阶段禁止：

- 先搭 Simulink；
- 先搜 Block；
- 在题意未澄清时先写业务 MATLAB 模型；
- 因某 Block 好用而改变题意；
- 因计算方便把真实对象换成别的对象。

## 6.3 Requirement Map

逐句提取：

- 背景；
- 系统对象；
- 输入；
- 输出；
- 时间范围；
- 空间范围；
- 工况；
- 扰动；
- 可控量；
- 状态；
- 参数；
- 初始条件；
- 边界条件；
- 约束；
- 性能指标；
- 失效条件；
- 输出精度；
- 图表；
- 文件交付；
- 论文要求。

每个 statement source 同时绑定原文件字节 SHA 和 UTF-8 审阅文本 SHA。直接文本可复用同一文件；PDF/OCR 等抽取文本必须有当前可追溯的核实记录，本阶段不实现通用 PDF/OCR 引擎。数据附件按来源与使用范围绑定，不强行逐字覆盖整张数据表。

audit unit 使用 Unicode codepoint 的 start（含）/end（不含）、精确原句和 requirement/context/excluded 处置；validator 检查精确切片、全部非空白覆盖、无重叠及排除理由。Requirement 与 audit unit 双向引用，并按小问绑定；显式事实和解释/推断分别登记。覆盖及引用正确只是机械完整性，仍需审查题意解释本身。

## 6.4 Simulation Problem Contract

每问至少包含：

| 类别 | 字段 |
|---|---|
| 对象 | original_system, derived_system |
| 边界 | system_boundary |
| 输入 | commanded_inputs |
| 扰动 | disturbances |
| 状态 | state_variables |
| 代数量 | algebraic_variables |
| 参数 | parameters |
| 决策 | decision_variables |
| 输出 | outputs |
| 可观测量 | observables |
| 初值 | initial_conditions |
| 边值 | boundary_conditions |
| 事件 | events |
| 切换 | mode_transitions |
| 时间 | time_domain |
| 空间 | spatial_domain |
| 数据 | input / calibration / validation / benchmark |
| 目标 | direct_goal / implicit_goal |
| 约束 | explicit / mechanism-derived |
| 交付 | numerical / figure / model / paper |
| 风险 | ambiguity / identifiability / fidelity / numerical |

上述事实字段逐类登记 specified / not_specified / not_applicable / deferred、内容、理由及 requirement 引用。未给信息必须显式保留，不能编造数值。只有模型设计本来才确定的抽象、状态表示、代数量、参数推导、事件/切换等可 deferred；不能把题设明确的对象、初边条件或交付要求转成 deferred 来绕过审查。original_system、direct_goal 与 deliverables 必须明确，其余实质未知通过关键歧义记录控制冻结。

model_structures 只登记候选线索，也可以留空等待 C；不能登记 locked model。每问的 objectives/capabilities 分别登记。数据使用绑定来源、question、role 和范围；同文件不同子集可以承担不同角色，相同拟合范围不得宣称独立验证。B 只检查角色/范围声明的闭环，真实统计独立性与现实有效性仍在后续阶段核验。

## 6.5 变量角色闭环

建议语义：

~~~text
u(t)  commanded input
w(t)  disturbance
x(t)  dynamic state
z(t)  algebraic/internal variable
theta model parameter
d     design/decision variable
y(t)  output
yhat  predicted observable
r(t)  reference
e(t)  residual/error
~~~

不强制符号，但强制角色不混淆。

变量使用稳定 ID、物理量、单位（未知时明确为空）、角色、来源及 declared/candidate 状态。状态同时可被观测、物理参数同时作为设计量时，必须说明角色关系，不机械禁止多角色。B 不把候选状态或变量登记升级为模型方程已确定。

## 6.6 Question Dependency DAG

依赖类型扩展为：

- data；
- parameter；
- state；
- model；
- initial_condition；
- boundary_condition；
- result；
- controller；
- scenario；
- validation_evidence。

每条依赖指定 producer/consumer 小问、type、预期 artefact 与 requirement 依据。校验未知节点、自环、重复边和循环；预期产物无需在审题时已计算出来。

## 6.7 问题分类

使用：

- objective；
- model structures；
- capabilities。

不得一个项目级标签覆盖全部小问。

## 6.8 产物

- modules/01_problem_audit.md
- core/problem_contract.schema.yaml
- templates/contracts/problem_contract.yaml
- scripts/validate_problem_contract.py
- tests/test_problem_contract.py
- tests/problem_factory.py
- tests/test_problem_router.py
- tests/test_problem_state.py
- tests/fixtures/problem_audit/ 中的代表性原始题面与附件（明确为测试）

接通 bootstrap/manifest/module manifest/router/resolver、project state schema/validator、output contract、lint、入口文档与生成索引。保持 Phase A probe、runtime_common、profile schema 和操作资格合同不变。模板保持 draft，未填写内容不能被当成 audited/frozen。只激活 problem_audit；C–K 继续 deferred。

## 6.9 Gate

problem_contract_status = frozen

要求：

- 对象无混淆；
- 状态/参数/输入/输出无混淆；
- 初边值明确；
- 数据角色明确；
- 依赖 DAG 明确；
- 关键歧义关闭。

validator 分别报告 schema_valid、valid、audit_complete、freeze_ready 和 frozen。合法草稿可以保留未知与未解决歧义；audited 要求原文/事实/引用/角色/数据/DAG 检查完成。frozen 另要求关键歧义已关闭、必要内容明确、语义 digest 与当前审查决定一致。决定绑定当前文件 SHA 和精确原句，独立于语义内容，避免摘要循环。

冻结是一项明确的审查决定，是否需要用户补充或确认由任务授权和关键歧义决定；不额外要求每个小问都走一次用户审批。开发继续授权不是某道竞赛题的事实、歧义答复或 Model Approval。validator/router 只验证决定及条件，不自动写 frozen 或项目状态。

project state 保持旧 A 文件兼容，只在 PROBLEM_AUDITED / PROBLEM_FROZEN 要求精确问题合同绑定与相应状态。问题证据只依赖自身题面、附件及审查决定；环境记录仍按 A 的规则校验。problem_audit 使用明确的问题审查 scope，环境过期不阻断纯文本审题，也不使未变的问题合同 stale；需要 runtime 的 route 仍要求新证据。合同/来源/决定变化使问题及实际依赖它的 accepted 产物 stale，保留历史。

## 6.10 开发 Exit Gate 与测试

项目 frozen 不是仓库 Phase B 开发完成的替代标志。开发出口要求：

~~~text
problem_contract_checks = passed
problem_audit_route_smoke = passed
project_state_problem_binding = passed
source_and_stale_checks = passed
authority_and_indexes = passed
~~~

完整测试应覆盖正常 draft/audited/frozen 路径，以及来源/抽取文本变化或缺失、引用错位/遗漏/重叠、未核实抽取文本、错误角色与数据使用范围、未知/循环依赖、未关闭关键歧义、错误审查决定 digest、手填 frozen、合同与项目身份不符、路径越界、stale 传播、环境过期与问题语义分离、C–K 继续 deferred 和无写入。保留 A 的回归测试，并做一次独立 agent 从原始题面进行审题的行为测试。

独立 PR 审查、对应最终源码 CI、合并与合并后回读分别记录。代表性合成题可以资格验证 B 的实现，但不能冒充真实竞赛项目已冻结或已建模。

---

# 7. Phase C — 模型设计、机理闭环与 Fidelity Selection

## 7.1 目标

决定“系统用什么数学结构表示”，而不是决定“用什么 Simulink Block”。

### 实施前审查与范围（2026-10-07）

用户授权进入 C。B 已由 PR #3 合并至 main `67d12deccf9b9f6d38b644d14a9bb2319455d383`，最终与合并后 Windows/Ubuntu CI、独立审查和原始题面试用通过。独立计划审查发现 §7 缺少结构闭环、身份/批准的可执行边界和开发出口，且 F4 将证据用途与 fidelity 混合；因此先修订本节，再实施消费者。

C 仅实施数学/物理模型的文字设计、挑战审查、审批材料和只读校验。设计路径要求当前 frozen Problem；直接 validator 可读取合法但未完成的草稿，不能把它标成 proposed/challenged/approved。不要求 MATLAB profile，不建立业务模型文件，不运行 solver、辨识、仿真或 V&V。D–K 保持 deferred。

一份模型可以服务多个问题，同一问题也可以有有理由的多个候选模型；必须覆盖 Problem 中的所有问题及相关 requirement，不机械要求每题一个模型或固定两模型。参数的数值估计和实际 comparator 执行属于后续阶段，C 可以登记其未知值、来源角色和拟议方法。

## 7.2 候选模型路线

每个 material 问题先提出机制、数据与预算支持的最小充分主路线，再审查 0..N 个能够测试实质假设或满足题目要求的备选路线。经典与高级是候选类型，不是固定两条路线的配额；没有必要的高级路线应记录技术理由，不为凑数量增加状态、参数或复杂度。实际执行结构 comparator 的裁决仍由 §12.5 的 required / not_applicable 管理。

### Route A：经典稳健

要求：

- 数学结构清晰；
- 参数可解释；
- 数据要求合理；
- 计算成本可控；
- 适合主线。

### Route B：改进/高级

可包含：

- 非线性增强；
- 多物理耦合；
- 混合状态；
- 数据驱动校正；
- 鲁棒/不确定性；
- 更高 Fidelity。

必须说明：

- 为什么必要；
- 新增状态/参数；
- 数据支撑；
- 计算代价；
- 能产生什么额外证据。

## 7.3 Model / Solver / Validator

### Model

例：

- nonlinear ODE；
- DAE；
- state-space；
- equivalent circuit；
- rigid-body dynamics；
- thermal network；
- Simscape physical network。

### Solver

例：

- ode45；
- ode15s；
- variable-step；
- fixed-step；
- fmincon；
- ga；
- lsqnonlin。

### Validator

例：

- analytical solution；
- experimental data；
- benchmark；
- conservation；
- alternate model；
- Simulink Test。

禁止把 solver 名称写成模型名称。

主模型需登记对象/抽象与边界、结构类别、变量和单位、关系/方程及其变量引用、输入输出、适用初边值、机制/耦合与核心假设。非物理、离散、数据驱动或非因果网络可以采用适合的关系表达，不能为了过 Gate 强制改成显式 ODE。登记守恒、因果、量纲及初边值闭合的设计审查，区分 reviewed、pending、blocked、not_applicable 与理由；结构引用检查和审查记录不等于自动数学证明。

数学身份由结构本体计算：对象/边界、结构类别、变量定义/角色/单位、方程/关系、机制与核心假设；不含 solver/容差、validator、实现路径/Block、工况参数数值或审批状态。模型 ID 与完整设计语义摘要分别报告。仅改变 solver 或参数数值不得产生“另一个数学模型”；改变待审批的设计内容仍可使完整设计摘要变化并使旧批准失效。变量中的参数来源、当前值和证据用于完整设计审阅，不进入结构身份。

## 7.4 Fidelity Ladder

~~~text
F0 conceptual
F1 lumped / low-order
F2 mechanism-complete engineering
F3 detailed / coupled mechanisms
F4 resolved mechanisms / scales for the intended target
~~~

F0–F4 是本任务情境中的设计标签，不构成跨模型的质量排序。分别说明机制、尺度、阶次、耦合和数据支持；多领域或高成本不自动意味着更高保真。benchmark/reference 另记为验证证据角色。F0 可以是合法候选或草稿，但不能用缺失关系/变量的概念标签冒充完整主模型。

选择考虑：

- 题目目标；
- 数据；
- 时间；
- 参数可识别性；
- 数值稳定性；
- 对结论的边际收益。

## 7.5 假设

每个主模型记录所有影响结论的核心假设，数量由问题决定，不以 3–5 个作为配额。逐项记录：

- 现实含义；
- 数学作用；
- 合理性；
- 失效偏差；
- 检验方法。

## 7.6 Model Challenge

批准前必须检查：

- 是否遗漏关键机制；
- 参数是否可辨识；
- 是否超出数据支持；
- 是否过度高维；
- 是否把实现便利性当物理依据；
- 是否存在更简单等效模型；
- 是否需要事件/混合结构；
- 是否真的需要 Simscape；
- 是否存在可执行 V&V。

以上九项均须显式登记 reviewed、pending、blocked 或 not_applicable，说明结论、理由和拟议解决/检验。主模型的量纲、守恒、因果和初边值闭合另登记四项结构审查。MODEL_PROPOSED 要求提案结构完整；MODEL_CHALLENGED 另要求所有挑战/结构审查均已执行（无 pending），可以保留已识别的 blocked 问题；任何 blocked 材料问题阻止 ready_for_approval 和 approved。not_applicable 需要任务理由，不能用它隐去必需机制或题设条件。拟议检验不是已完成的数值证据。

## 7.7 Human Model Approval

生成 Model Approval Brief：

- 主路线；
- 备选路线；
- 核心方程；
- 状态变量；
- 参数来源；
- 假设；
- Simulink 映射预期；
- solver 风险；
- V&V；
- 计算成本；
- 推荐等级。

批准后形成 locked_model_spec。

Human Model Approval 来自实际人类对当前 Brief/设计的明确决定；可复用仍适用于当前摘要的既有决定。仓库开发授权、agent 推荐、approved 标志或自填 reviewer 不能替代真实批准。调用者可忠实记录人类原话及其项目/设计上下文，不要求用户亲自输入哈希，也不为仓库实施请求虚构真实模型批准。

ModelContract 使用 status draft/proposed/challenged/approved，绑定 project_id、当前 Problem 文件 path/SHA、设计依据 sources、designs、Brief 文件 path/SHA 和独立 approval 文件绑定。设计可多问共享，每个 design 登记 question_ids、requirement_ids、主模型、0..N 备选、选择理由、数学模型本体、fidelity 理由、solver 风险/validator 计划及九项挑战。未知参数可保留 null，来源 given/derived/identified/calibrated/optimized/assumed 与已知值、拟议来源/识别方案分别记录，不能制造数值或验证结果。

完整设计语义 digest 排除 status 和 approval 引用，其余内容（含当前 Problem、实际来源和 Brief 身份）全部绑定。Brief 不反向嵌入这个 digest；可引用独立的模型结构身份，避免摘要循环。外部 ModelApproval 绑定 project_id、problem_sha256、model_semantic_sha256、人类决定的 path/SHA/Unicode起止/quote/actor/action 和 locked_model_spec 的 path/SHA。决定的精确引用包含项目、Problem 与完整设计摘要以及明确的 action=approve 上下文；不能用包含当前摘要的拒绝/撤销记录冒充批准。锁定文件由显式调用者在真实批准后生成，必须与当前语义内容及摘要逐项匹配，不接受仅有 locked=true 的空壳。validator/router 从不写批准、锁定文件或项目状态。

状态 optional model/approval 绑定保持 A/B 兼容；三种 C 状态要求当前 frozen Problem，MODEL_PROPOSED/CHALLENGED/APPROVED 各要求相应当前合同状态与 Gate。accepted model/approval 产物精确绑定并依赖 model/problem（approval 另依赖 approval anchor）；不得依赖环境证据。model scope 验证 B/C，环境未评估；problem scope 不评估模型并明确报告该部分范围，不能冒充 MODEL_APPROVED 整体通过。默认 all 保留 A/B 检查。

来源、B freeze 记录、ModelContract、Brief、人类决定或锁定文件改变使相应 anchor 与 accepted 下游 stale。C 采用整个 Problem 字节绑定与 B 的来源校验，这是安全的保守失效：独立验证附件变化也可能使该绑定过期，不宣称已实现 §18.5 的精细失效图。另登记真正用于模型选择的 source/data ID 及用途，留给后续精化。环境 TTL 不使未变的文字模型语义过期。

未来路由不再将已完成的 phase_b_exit_reviewed 硬编码成项目缺项；只返回未实现能力及实际项目前置 Gate。模型批准不能使 D–K 激活，数值执行权限仍为 false。

## 7.8 产物

- modules/02_model_design.md
- core/model_contract.schema.yaml
- core/model_approval_contract.yaml
- templates/contracts/model_approval_brief.md
- scripts/validate_model_contract.py
- tests/test_model_contract.py
- templates/contracts/model_contract.yaml
- core/project_state.schema.yaml 与 scripts/validate_project_state.py 的 C 适配
- core/workflow_router.yaml 与 scripts/resolve_runtime.py 的 model_design 路由
- tests/test_model_router.py、tests/test_model_state.py 及原始合成来源夹具
- bootstrap/module/output/manifest/lint/index/入口文档同步

## 7.9 可执行开发出口

validator 分别报告 schema_valid、valid、proposal_complete、challenge_complete、ready_for_approval、approved、model_identities、semantic_sha256、contract_sha256、project_id/question_ids、errors/missing_gates/changed_sources。CLI/API只读，支持 require_proposed/require_challenged/require_approved。

开发出口要求：model_contract_checks（草稿、完整候选、多问共享、0..N备选、引用/单位/结构审查/挑战）、model_approval_binding（当前人类决定、项目/Problem/摘要/锁定文件、拒绝/agent/旧批准失败）、model_route_and_state（无环境纯设计、当前frozen B、状态不伪升、不自动写文件、D–K deferred）、source_and_stale_checks（当前来源/Brief/决定/锁定文件、保守失效、TTL分离）、authority_and_indexes 与全部 A/B 回归。

独立复核补充：design/model ID 可以包含点号，但导出的平面 `model_identities` 使用 `design.id + '.' + model.id`；不同 ID 对若生成同一键，validator 必须显式拒绝，不能静默覆盖并进入 proposed/challenged/approved 或生成锁定快照。保留原 ID，不自动重命名；提供碰撞负例及非碰撞点号 ID 正例，保证每个有效候选都有唯一且完整的身份映射。

锁定快照匹配还必须保留当前完整 JSON 内容及类型，不能依赖 Python 中 `true == 1` 或 `1.0 == 1` 的宽松相等。使用与语义 digest 一致的 canonical 表示比较完整 payload；布尔/整数/浮点类型替换、非有限值或不支持的 YAML 类型均受控失败，不得复用原人类决定放过已改变的锁定内容。

独立原始输入行为测试、精确最终提交审查、对应 Windows/Ubuntu CI、合并与合并后回读分别记录。合成批准夹具只验证开发基础设施，不证明有人批准真实模型、数学正确、真实物理有效、统计独立或已获数值执行资格。

---

# 8. Phase D — 数学模型到 Simulink / Simscape / Stateflow 映射

## 8.1 目标

将当前批准的 locked_model_spec 映射为可追踪的工程实现，审查语义保持；机械结构检查不证明数学等价、物理有效性或数值正确性。

## 8.2 Domain Selection

### Simulink

适合：

- signal-flow；
- control；
- ODE blocks；
- discrete-time；
- algorithmic subsystem。

### Simscape

适合：

- conservation network；
- multidomain；
- electrical/mechanical/thermal/fluid coupling；
- acausal modeling。

### Stateflow

适合：

- mode switching；
- event logic；
- protection；
- finite-state behavior。

### System Composer

适合：

- architecture；
- interface；
- multi-component MBSE。

## 8.3 官方 Skill 适配

初始映射：

- building-simulink-models
- specifying-plant-models
- finding-simulink-examples
- 官方 Physical Modeling / Control / Stateflow 相关 Skill

本仓库 adapter 只定义：

- trigger；
- precondition；
- expected output；
- evidence；
- fallback。

## 8.4 模型层级规范

推荐但不强制：

~~~text
Top Model
├── Inputs / Scenario
├── Plant
├── Controller / Algorithm
├── Disturbance
├── Sensors / Measurement
├── Constraints / Protection
├── Metrics
└── Logging
~~~

## 8.5 参数治理

禁止散落 magic number。

参数来源：

- given；
- derived；
- identified；
- calibrated；
- optimized；
- assumed。

记录：

- symbol；
- code_name；
- value；
- unit；
- source；
- scope；
- uncertainty；
- tunability。

## 8.6 产物

- modules/03_domain_mapping.md
- adapters/mathworks/simulink_agentic_toolkit.md
- adapters/mathworks/skill_mapping.yaml
- adapters/mathworks/compatibility.yaml
- core/parameter_provenance.schema.yaml
- templates/simulink/
- tests/test_upstream_mapping.py
- core/domain_mapping.schema.yaml
- core/implementation_assurance_contract.yaml
- scripts/validate_domain_mapping.py
- scripts/validate_parameter_provenance.py
- scripts/probe_implementation.py
- scripts/validate_implementation_profile.py
- scripts/run_implementation.py
- scripts/matlab/ 受控核心构建与实际结构回读
- mapping/parameter/native/router/state/stale回归与Authority入口同步

---

## 8.7 2026-10-08 实施前审查与执行契约

用户于2026-10-08继续授权D，要求先审查、必要时修订计划，再实施并独立复核。C已按最终54f0519合并为ecf59c7，main双平台CI成功。D当前§8缺少可执行契约、项目与开发出口，本次先补下列决定。

### D状态和权限

D新增项目IMPLEMENTATION_READY；只有当前真实C批准、完整审查的映射、必要参数绑定、实际实现文件和结构receipt均有效时，由显式调用者更新。草稿、mapping_complete、build_ready、built、structure_checked、implementation_ready分别报告，检查器不推进状态。不授予E仿真、solver协议、辨识/标定/优化、数值V&V或成果验收。

文字domain_mapping不依赖环境profile；正式映射路线要求当前C require_approved Gate。实际simulink_build及结构更新需当前A运行资格和独立D操作资格，不能由A library_load升级。execution_allowed只适用于明确implementation_execution范围；business_execution_allowed和simulation权限保持false。构建只在新的输出目录执行，不覆盖已有模型/历史证据。

### 数学和实现身份

绑定当前C文件/Approval/locked的完整校验、所选design/main_model及数学身份。保持Blocks、路径、布局、求解器和数学模型不同。允许多问共享、0..N必要组件、一对多/多对一关系映射，以及任务合理的层级合并/省略；不强制固定九层，也不为过Gate建立空子系统。C自由文本关系不是可执行语法，不进行eval或自动数学转码。

映射完整要求selected main models的数学关系、变量、输入输出、初边值与事件都有实现追踪/审查或具体有理由处置。辅助日志/结构对象解释用途；新增延迟、采样、饱和、切换或近似若改变C语义须返回C。反馈、DAE和非因果网络不机械要求block图无环，来源依赖仍须DAG。结构update与追踪不构成数学等价证明、物理有效性或数值正确性。

### Domain和实际支持范围

按数学目标登记Simulink/Simscape/Stateflow/SystemComposer或适用MATLAB算法组件、混合耦合、备选及理由。域适用性与操作可用性分开。D本次Native baseline为明确受支持的Simulink核心blocks/ports/connections/model-workspace参数，以及update/save/reopen/actualreadback。资格只覆盖实际测试范围；Simscape/Stateflow/SystemComposer实际操作未有各自qualification时继续explicitdeferred，不能因安装或selection激活。fallback不得偷偷换域或数学模型。

本地受限builder补齐可复现核心结构receipt缺口，输入为经契约校验的显式block/connection/binding指令。初始支持Inport/Outport/Constant/Gain/Sum/Integrator；其他库block、MATLABFunction、自定义mask/callback、modelreference、外部字典、任意代码表达式等仅可登记待支持映射，不能进本地native ready。上游能力选择仍按固定版本、实际资源与当前资格；不把受限builder说成通用数学代码生成器。

2026-10-08 独立边界复核补充：数学模型没有外部输入或不要求根输出端口时，不强迫建立Inport/Outport；已存在的同类根端口编号才需连续、唯一。参数code_name不能与其原生target模型名冲突，mapping build_ready与实际builder应对同一受支持指令作一致裁决。增加Constant→Outport无外部输入案例与名称冲突负测；保存原始复现，并在真实R2025b中执行无外部输入结构回读。

### 参数绑定

参数登记引用当前C design/model/variable，以原symbol与合法独立code_name、作用域/owner、value或null、unit或null、来源角色/当前source IDs、不确定性状态、tunability及理由绑定。值/单位/来源必须与当前批准C一致；不解析自由文本推导、不识别或校准、不填0/1/零不确定性或默认可调。实现名称/作用域冲突、未知引用、不支持值类型、非有限值和当前来源变化应受控失败。

未知参数可完成文字映射，但必要值缺失阻止native build_ready/结构ready。不同C参数provenance仅是来源角色。实际构建的增益/常量等必须引用参数登记；Integrator初值等必须引用批准C初边值的明确结构化位置，不能让block默认值引入未批准条件。只保留项目明确可调的决定，不混入qualification fixture值。

ModelFile模型工作区是本地baseline的参数scope，不强制全局baseworkspace或数据字典。未知单位可在文字阶段保留，核心native要求其需要的绑定完成。单位登记/Simulink.Parameter.Unit不自动证明量纲一致；信号/接口单位和温差/绝对温度需独立审查。

### 契约/消费者/证据

新增core/domain_mapping.schema.yaml、core/parameter_provenance.schema.yaml、core/implementation_assurance_contract.yaml；先契约，再只读validate_domain_mapping/validate_parameter_provenance，再modules/03_domain_mapping和真实draft模板。Mapping绑定C、参数文件、sources、domain decision、targets/关系和变量trace、reviews及可选implementation receipt。映射semantic digest排除status与receipt引用，其余内容全绑定；producer先捕获当前完整payload再形成receipt，不能创建自引用摘要。

D操作profile为A的独立伴随证据，不改A七个hash-bound文件或把A原资格扩大。D记录新source/input/host/runtime/channel、过程completed/exit0、raw结构与日志、实际SLX字节与receipt。当前构建gate分别消费当前A和Dprofile。Dprofile生产者实际创建/连接/赋值/update/save/close/reload/readback；不是手填qualified/structure_checked标志。新运行需当前runtime资格，历史receipt按其完整身份及当时资格回读，不因为现在TTL过期就删除未变结构的历史有效性。

2026-10-08 真实单项目构建复核补充：MATLAB成功保存/重开模型后，单条struct结果被JSON编码成object，暴露了多case资格探测与单case项目生产之间的协议缺口。原始raw和SLX保留为诊断，不能计入缺失consumer receipt的完成证据。跨语言raw的cases及结构中的blocks/connections/parameters必须保持0/1/N一致的JSON数组类型；MATLAB端使用明确cell数组编码，Python端验证实际形状并受控拒绝非法对象，不做宽松单值提升。修复后重新取得最终源码资格、真实单case反馈和Constant→Outport项目回读、最终commit审查与双平台CI。结构数组为空或单项时同样纳入真实回读，不能仅用Python fixture代替跨语言出口。

加载、保存、update可能执行callback/初始化/掩码代码，绝非纯只读inspect。本地baseline只创建受控官方核心block、无自定义callback的自有新模型，记录库来源、实际函数路径和执行surface；不关闭其他模型或修改全局路径。支持范围以contract声明并真实运行核验。未知/错误端口、值、update或source变化受控失败并保留证据，不产出成功receipt。

### 状态、时效和失效

增加implementation partial scope，评估B/C/D，environment_checked=false。problem/model scope报告D未评估；默认all保留环境要求。Mapping/parameter/implementation/structure artifacts明确消费各自合同/receipt，不能落入A route_decision的environment-only分支。当前C→parameters→mapping→native files/structure的实际anchor与accepted依赖须闭合。当前build-route依赖runtime，历史实现/结构证据在receipt绑定当时环境，不把现在TTL当作语义anchor。

C Problem的保守全字节/source校验继续；模型/参数/映射/SLX/实际执行代码/依赖变化使相应D证据及下游stale。环境TTL只限制新的执行，不使未变文字映射/C批准自动失效；E仍须独立当前runtime检查。本地baseline不支持的依赖/域返回具体缺项，不顺便声称精细数据失效图或完整项目结构验证。

### 官方适配与出口

官方MathWorks适配记录repository、commit/tag、实际skill/resource、release/toolbox/channel、本地版本、trigger/precondition/input/output/evidence/fallback/side effects，不复制整套官方手册。候选skill名字需在实施时live核验，缺失不装作已安装。保留必要R2025b官方API链接，不引入仅R2026a行为。

实际资源除原§8.6外增加：D两类消费者、操作probe/validator、受支持native builder/结构receipt producer、mapping/parameter草稿，以及mapping/parameter/native/router/state/stale测试与bootstrap/output/manifest/lint/index入口同步。不创建未实现业务占位。

开发出口：domain_mapping_checks、parameter_binding_checks、native_simulink_structure_qualification、mapping_route_and_state、source_and_stale_checks、upstream_compatibility_and_authority、authority_and_indexes、全部A/B/C回归、原始输入独立行为测试、精确最终commit复核、Windows/Ubuntu CI、合并及合并后回读。Native qualification至少两个不同结构的开发case（静态与带状态反馈），实际端口/参数/保存重开/update断言，另一个受控失败case；不模拟仿真结果。

synthetic批准/数值/案例仅资格化基础设施，不为实际项目提供ModelApproval、辨识参数或物理真实性。工程结构实现许可不等于E的仿真协议和数值执行许可。同步§17 mapping/parameter→implementation/structure链、§18失效、§25 Mapping Evidence限定含义。

---

# 9. Phase E — Solver 与仿真执行协议

## 9.1 目标

避免“默认 solver 能跑就算完成”。

## 9.2 Solver 分类

检查：

- continuous / discrete；
- stiff / non-stiff；
- DAE；
- event；
- zero crossing；
- algebraic loop；
- multirate；
- fixed-step requirement；
- real-time / codegen。

## 9.3 Solver 决策记录

至少记录：

- Solver；
- SolverType；
- MaxStep；
- MinStep；
- InitialStep；
- RelTol；
- AbsTol；
- ZeroCrossing；
- StopTime；
- sample time；
- Simscape local solver（适用时）。

## 9.4 Simulation Protocol

包含：

- model identity；
- parameter set；
- scenario；
- inputs；
- initial conditions；
- boundary conditions；
- solver；
- tolerance；
- stop criterion；
- logging；
- seed；
- acceleration；
- expected metrics；
- runtime class。

## 9.5 Non-destructive Simulation

优先使用：

- Simulink.SimulationInput；
- setVariable；
- setModelParameter；
- setBlockParameter；
- setExternalInput。

参数扫描不得反复污染主 slx 模型。

## 9.6 数据输出

优先：

- signal logging；
- Dataset；
- logsout；
- SimulationOutput；
- Simulation Data Inspector。

不为了导数据机械插入大量 To Workspace Block。

## 9.7 Run Receipt

记录：

- MATLAB release；
- model hash；
- parameter hash；
- protocol hash；
- solver；
- start/end；
- success/failure；
- diagnostics；
- machine info（仅性能 claim 必须）；
- output artefacts。

## 9.8 产物

- modules/04_simulation_protocol.md
- core/simulation_protocol.schema.yaml
- templates/matlab/
- templates/simulink/
- scripts/validate_simulation_protocol.py
- tests/test_simulation_protocol.py

## 9.9 2026-10-08 实施前审查与执行契约

### E 状态、协议冻结与权限

协议仅使用 draft/frozen，不引入没有消费者的 reviewed 中间状态。validator 分别报告 schema_valid、valid、protocol_complete、frozen、execution_ready 和 missing_gates；run 消费者另报告 run_complete、criteria_satisfied 及实际输出完整性。合法草稿、当前冻结协议、可执行门控和成功运行不可混为一个 passed。

协议绑定当前 B、C 文件/完整人类批准/locked snapshot、D 参数登记与映射、实际 SLX/结构 receipt、选定 design/model/target 与数学身份。冻结记录为独立文件，绑定 project、完整协议语义摘要及明确的授权审查决定、当前来源和精确 quote。协议 semantic digest 只排除 status 与冻结记录引用，其余内容全部绑定；不能把包含自身 SHA 的 receipt 或批准摘要写回自身形成循环。显式调用者先准备完整可审查材料，真实执行审查后记录决定、冻结合同并更新状态；validator/router 从不生成决定、修改文件或推进状态。

E 的协议审查不另造一次 C Human Model Approval；它在当前授权范围内审核执行条件。C 的实际人类批准仍必须当前有效，仓库开发授权或 synthetic 案例不能替实际项目提供这个批准。改变 E solver/tolerance 等而保持 C 内容不变时，数学模型身份与 C 批准保持；修改 C 内 solver_plan、Brief、参数、条件或其他完整设计内容仍须依现 C 合同更新批准，不能以数学结构身份未变绕过完整设计摘要。

SIMULATION_PROTOCOL_FROZEN 要求当前完整冻结协议及有效 B/C/D 绑定，不要求运行已经发生。PRIMARY_RUN_COMPLETE 另要求当前协议的实际成功运行、完整有限输出、预先声明的检查判据通过及显式调用者的运行审查/登记。该状态仅记录可供后续验证的运行，不授予 NUMERICALLY_VERIFIED、VALIDATED、EVIDENCE_ACCEPTED 或论文主张权限。read-only protocol 设计与检查不要求当前 MATLAB profile；新的 simulation_execution 必须满足当前资格和完整协议 Gate。solver_diagnostics 仅消费该次实际运行配置/诊断，不开放 H 的 solver comparison。

### 实际支持范围与 solver 决策

本轮 native baseline 为当前 D 已 qualified 的一个 flat scalar Simulink target，六类 Inport/Outport/Constant/Gain/Sum/Integrator，至少一个根 Outport，普通 normal mode、串行单次仿真。无根 Inport 的常量模型可以运行；没有根 Outport 时不能得到本 baseline 的成功主运行证据，明确返回缺项，不能为了过 Gate 新添数学对象或伪造输出。

受控 solver 先实现 variable-step ode45 与 fixed-step ode4；ode15s 作为单独案例候选，只有实际 R2025b stiff 资格案例和对应断言通过才开放其操作。每种 solver 按各自实际资格裁决；某一项失败不得由其他 solver 的成功提升成 qualified，也不得自动切换 solver 或改数学模型。记录 continuous/discrete、stiffness、DAE、event/zero-crossing、algebraic loop、multirate、fixed-step、real-time/codegen 的分类、判断依据、风险与适用性，不把声明或图更新当作这些复杂能力的证明。

solver 值以 typed、有界有限数据登记，记录 StartTime/StopTime、Solver/SolverType、适用的步长、容差和 zero-crossing 设置及理由。不适用参数显式 null/理由，不能给 fixed-step 填无意义容差或给 variable-step 默填固定步长。要求 start < stop、步长/容差处于对应 API 的合法范围以及适用字段一致。实际运行保存有效 solver/readback，而非只回显请求。期望指标、阈值和 claim_limit 在冻结前确定，实际结果不反向修改这些条件。

第二轮真实 R2025b 探测证明此前允许 MinStep=0 的审查判断错误：变量步长案例实际返回 Simulink:ConfigSet:BdInvSimParam，固定 ode4 与受控错误/早停案例则按预期通过。R2025b MinStep 文档也规定 auto 或正标量。E 当前范围使用显式有限数值，因此 variable-step 的 MinStep 必须严格为正，并与 InitialStep/MaxStep 一致；不将零暗改为 auto。先修订计划、协议与运行器共同拒绝零值，然后显式重新审查新的正值协议，保留原冻结协议和失败运行。该错误不构成 solver 或工具箱不可用的结论。

独立复核补充：协议与运行器必须使用一致的时间和容差边界。R2025b StartTime 允许有限负起点，RelTol 要求正标量，没有通用的非负起点或不大于 1 限制；不能在运行器暗加这两项约束。固定步长的起点必须是步长的整数倍，以浮点表示误差范围检查，冻结前拒绝会被引擎自动调整的起点，不把这种调整当成已审查工况。StopTime 不凭空要求整数倍，但实际输出仍必须覆盖冻结终点。实际公开 SolverInfo 的名称、类型和适用的固定步长或 MaxStep 必须存在且与协议一致；缺失或矛盾不能凭配置回显通过。warning_policy=reject 同时检查实际 WarningDiagnostics 与 lastwarn 消息/标识，不能因诊断数组为空而忽略已经观测到的警告。

第三轮真实 R2025b 记录了 ode45、ode4、ode15s 的正常终止与对应公开步长，及无状态 constant 的实际 Solver=VariableStepDiscrete。R2025b 引擎会将无连续状态模型编译为对应离散求解器；检查须保留请求与实际方法，按 variable/fixed 类型分别识别 VariableStepDiscrete/FixedStepDiscrete，不能用未经实测的笼统名称 discrete 误拒，也不能声称静态模型实际运行了连续 ODE 求解器。存在 Integrator 的受控目标仍要求实际选定连续方法一致。该轮随后发生原生 Illegal instruction，整个资格失败；部分正常记录只供 API 诊断，不合并或提升为完整资格。

第四轮原生记录进一步发现 Constant 的继承 Inf 采样仅记录初始输出，多输出案例中的 constant 端口也只有一个采样；因此虽然终止正常，仍不满足已冻结的完整时间覆盖。不能通过复制常数到伪造时间轴或放宽覆盖检查过 Gate。E 协议须显式冻结 logging.sample_time=0，将每个根 Outport 的连续采样设置通过 SimulationInput.setBlockParameter 临时应用，保存实际应用的端口/采样设置并核验运行后与重新加载时的原设置恢复；这是根输出记录方式，不改变已批准参数、数学本体或保存的 SLX。无输入 static 仍为合法 primary 场景，须在全新原生九案例及真实项目中验证这个设置确实产生完整采样。保留旧协议、原始单采样与未完成回执，不补写未知进程退出码。

R2025b 公开 SimulationMetadata 的 SolverInfo 不保证暴露全部容差字段。配置记录与实际观测分开：记录 SimulationInput 施加的完整 typed 参数，实际 solver 名称/类型及公开步长从 SimulationMetadata 读取；只核对公开观测和实际时间覆盖。未公开的容差不声称已独立 get_param readback，也不为此引入自定义运行 callback。输出采样间隔与内部求解步长保持区别。该限制来自本轮官方 API 审查，先保存此计划修订，再实施相关消费者。

初轮真实 R2025b 九案例发现 ExecutionInfo 不含 StopEventTime，直接读取会使已返回的仿真输出在后处理失败中丢失。终止事件继续读实际 StopEvent；实际停止时间以 SimulationOutput.tout 的最后有限采样及各必需输出覆盖独立裁决，并记录观测来源，不能用配置 StopTime 代替。错误/零输出导致 tout 为空时保留 unknown 与失败诊断；受控早停必须有实际时间依据。SimulationOutput 返回后先持久化原始 MAT，再做元数据与格式后处理；失败保留原生部分数据，不提升成成功。此次按实际 API 证据先修订计划，再修正消费者，原九案例保留为失败记录。

Simscape/Stateflow/System Composer 执行、复杂 DAE/事件/多速率支持、实时/codegen、accelerator/rapid accelerator、Fast Restart、并行、参数扫描、辨识/标定/优化以及 solver comparison 保持 deferred。SDI、内部 signal logging/logsout 扩展可以登记待支持，不因推荐 API 出现在 §9.5/§9.6 而自动获得资格。

### 参数、场景、输入与非破坏执行

SimulationInput 只独立覆盖已审核的 solver 设置，并通过模型 workspace 将当前 D/C exact 已批准参数再次显式绑定；不覆盖 C 参数、初值或边值，不寻找 base workspace 默认值。参数 hash、exact typed value/unit/provenance/owner 与当前 D/C 一致。初始化与边界继续消费 D 实际结构和 C 条件，新增采样、延迟、初值、事件或其他数学变化返回 C。G 的扫描与 F 的拟合不由 E 顺带执行。

场景有当前要求/来源依据、工况说明、输入变量/单位和 seed、runtime class 的明确值或不适用理由。所有根 Inport 必须完整、唯一、按当前 C/D 身份绑定；支持有限标量 constant 或严格有限、时间有序、覆盖所需区间的 time/value 输入，显式声明插值/保持规则和边界处理。C 已知输入值和来源规范必须保持，关键场景或输入缺失时返回具体缺项，不自动补零、step、随机信号或 qualification fixture。自由文本关系和任意 MATLAB 表达式不解析、不 eval。

采用 Simulink.SimulationData.Dataset + SimulationInput.setExternalInput；外部输入是当前协议的受控数值数据。根 Outport 通过 SimulationOutput 的 yout Dataset 输出，不机械插入 To Workspace，也不保存为了 logging 改 dirty 的主 SLX。SimulationInput.setBlockParameter 虽为推荐 API，本 baseline 不用它改已批准初边值或引入未审语义。

每次运行使用新目录、拥有的模型副本和独立 file-generation 目录，只 load/close 本次拥有的模型；恢复 file-generation 与 RNG 设置，不修改全局路径、不关闭其他模型、不写入 base workspace。加载/仿真可能执行 callbacks，须在载入前核实当前 D 结构 receipt 与 SLX 字节身份，并限制为已审核心 execution surface；不接受任意用户 SLX、mask、引用模型、外部字典或 callbacks。原 C/D/参数/SLX 在执行前后逐字节不变；文件存在或 normal-mode 启动不构成非破坏执行通过。

### 独立仿真操作资格和 Statistics 要求

新增 E simulation_assurance companion contract/profile/probe/consumer，不修改或扩大 A 的 minimal operation scope，也不把 D 结构资格升级为 sim 资格。真实 probe 必须在当前 A 资格的同一 R2025b/runtime/host/channel 上实际运行受控 solver、输入和 logging 路径，检查数值输出、有效 solver、非破坏原件与输出解释，并观察受控失败。资格记录具体操作/solver、实际函数来源和 assertion 结果；未通过某项给明确未 qualified，不得用 installed/license/整体 qualified 布尔值掩盖。

新的业务运行分别要求当前 A 所有实际必需操作及 E 所选 solver/输入/输出操作通过、同 runtime、输入/源码/宿主/receipt 完整绑定。历史 D 结构按其执行时资格和当前身份回读，不要求现在重新取得 D TTL 以只读消费已有结构；E 不借此获取新的建模权限。E profile 的 TTL 与当前检测规则独立登记，不覆盖已有失败和成功证据。

协议明确 required_A_operations，至少核心 MATLAB/Simulink 操作，并将实际方法依赖的统计 operation ID 作为必需传播给 A 校验和 route。用户/调用者显式 `--require-operation` 的要求不得静默忽略或被协议较小集合覆盖。`--include-statistics` 仍只扩展探测；整体 runtime_assured/core 通过不能替代所需 fitlm/lhsdesign/normcdf 的 qualified 与 assertion。未声明且不使用的统计操作不阻断核心；声明为必需而失败/缺失必须阻止 E execution，fallback 不得悄悄换方法。F/G 分析模块继续 deferred，即使相关 A 最小操作已 qualified。

### Run receipt、原始输出与终止检查

每次 producer 捕获完整协议和输入 snapshot、B/C/D/参数/SLX/结构身份、当前 A/E profile/receipt、源代码集合、runtime/channel/host、实际有效配置、过程 started/finished/state/exit、原始 MATLAB 报告和日志、输出 MAT/JSON/CSV 文件与逐文件 SHA。运行 receipt 不写回协议形成自引用；实际数据从 SimulationOutput/Dataset 读取，记录每个输出的根端口、observable/变量身份、单位、采样时间和值。CSV/JSON 与 MAT 内容/数组形状按同一声明的输出契约核对，不凭非空文件声称正确。

第五轮真实 R2025b 九案例均完成原生执行，常量与多输出端口已取得完整采样，但 MAT 消费者误把存储 payload dtype 当作 MATLAB 数组类型：MAT v7 可将 double 类的整数值压缩为 miUINT8，SciPy loadmat 默认返回存储类型。这不代表原输出是 uint8，且实际 MAT/JSON/CSV 数值完全相同。独立消费者应使用 loadmat(mat_dtype=True, squeeze_me=False) 按 MATLAB 声明类型读取，仍严格要求 float64、完整形状及精确数值一致，不通过强制 cast 或数值容差放宽 Gate。新增 double 类/uint8 payload 的真实格式回归以及真正 uint8/logical 类拒绝检查，保留 v5 原始失败报告，并在修订后的当前源码上重新取得完整原生资格和项目运行。

独立负例还确认 SciPy 1.18.1 的 mat_dtype=True 会将 complex double 转为实部并发出 ComplexWarning。为保留既有 real-double 边界，先用默认存储类型只读选定数值字段并拒绝任何 complex 数组，再按 MATLAB 声明类型读取校验。不得通过丢弃虚部使本来无效的数据通过；使用实部恰好等于 JSON 的 complex 负例验证此路径。

最终提交附加独立负例发现 MAT 身份字段仍有隐式转换缺口：logical true 可与端口 1 比较相等，数值单位 1 可经 str 转换匹配文本 "1"；端口 row 方向也未区分。该问题没有改变已取得的真实数值输出，但不符合 typed 身份和同一格式的核对目的。现明确冻结 producer 的 MAT 规范：output_ports 为 MATLAB double 类 N×1 正整数端口列；run_id 为单行 char 文本；output_variables/output_units 为 N×1 cell，其成员为单行 char 文本，只有空的声明单位可用空 char。consumer 严格验证声明类、方向和文本，拒绝 logical/整数类伪端口、数值/多行伪文本及方向不符，不经 str/cast 放宽。允许的 null 单位在 JSON 保持 null、MAT 保持空 char，不编码成 JSON []；在受控 passthrough 实例中真实测试 nullable 单位与文本身份出口，保留旧成功和新负例证据后重新取得当前源码资格、真实项目及最终提交检查。

process.json 在后续 normalization 前保存；异常、超时、raw 缺失、JSON 形状错误、单例/空集记录等保留原始证据并受控失败。raw 中 cases/functions/diagnostics/outputs 等记录集合使用 0/1/N 一致数组协议，MATLAB producer 明确编码，Python 严格校验；不把 object/null 宽松提升为数组。没有输入或参数是合法基数；没有必需输出或缺输出是运行失败，不能把空数组当作完整主结果。

进程 exit0、MATLAB 调用返回、时间轴完整性、预期终止、输出有限性、指标判据与 diagnostics 分开检查。消费 SimulationOutput Error/Warning/StopEvent 等实际终止信息及实际最终时间；错误、非预期早停、时间未达到已冻结 StopTime、缺少/重复/非有限输出或判据失败均不能生成成功主运行 receipt。warning 的接受/阻断策略与理由在协议中明确并按实际内容审查，不静默丢弃 warning，也不把所有 warning 一律当失败。不得只用 exit0 或波形“看着正常”断言成功。

历史 run 消费者只读重算身份/receipt/raw/输出/判据及当时完整 A/E 资格，当前 TTL 过期不否定未变历史运行，也不给新的执行权限。receipt/输出成功证明当前声明范围的可复核执行，不证明数学等价、数值收敛或物理真实性。

### 状态、依赖与失效

project state 增加 protocol、primary_run 和独立 simulation_environment 绑定，新增 E artifact roles 和 simulation partial scope。simulation scope 评估 B/C/D/E 的实际 anchors、历史运行与依赖，environment readiness 未评估；problem/model/implementation scope 明确 E 未评估，default all 保持当前环境要求。草稿协议不可通过冻结状态，旧运行或手写 success 标志不可通过 PRIMARY_RUN_COMPLETE。所有 state/route 消费者只读，必须分别报告 checked/unchecked 范围与 execution scope，不能把 E artifact 当 A route_decision 消费。

E solver/tolerance/logging/输入/场景等协议变化，或输入源、C/D 参数/映射/SLX、必要源码/运行依赖变化，使相应协议/运行及实际依赖的验证、主张和交付 stale。当前环境 TTL、runtime/host/source 变化限制新执行并使当前环境与 route 失效；未变历史证据按绑定当时资格核验并保留。C whole-Problem 的保守失效保持，不宣称已完成未来精细 validation-data 图。

保留 A 七个 source-identity 文件、B schema/validator 与 D implementation_assurance source_files 的十九个源码文件逐字节不变；E 扩展通过独立契约、producer/consumer 和非 D source-bound 的 router/state/lint/module/入口接入。若确有改这些文件的必要，先修订计划写明相关 A/D 历史身份失效范围，重新取得受影响资格和实现证据，不能以“仍是同一模型”继续使用原证据。solver/tolerance 的 E 局部变更本身不能迫使未变 C/D 自动 stale。

### 实际资源与开发出口

除 §9.8 资源外，增加 core/simulation_assurance_contract.yaml、E profile/receipt consumer、scripts/probe_simulation.py、scripts/validate_simulation_profile.py、scripts/run_simulation.py、scripts/validate_simulation_receipt.py、受控 scripts/matlab/ 实现、合法协议 draft 模板，以及 protocol/freeze/native/runtime/router/state/stale/output 回归。同步 bootstrap/output/manifest/lint/index/入口与版本 0.5.x；不创建未来模块占位。

官方适配以 live pinned skill/resource、实际文件与 R2025b API 为准，按实际 simulating/inputs/output 需求更新兼容矩阵；上游文档或 release 声明不能代替本地实际组合资格。官方 API 选择需核对 R2025b，R2026a-only 行为不得进入当前 native 路径。SDI/logsout 等本轮 deferred 范围在适配中同样明确。

开发出口要求 simulation_protocol_checks、protocol_freeze_binding、native_simulation_qualification、run_receipt_and_outputs、simulation_route_and_state、source_and_stale_checks、required_operation_propagation、upstream_compatibility_and_authority、authority_and_indexes、完整 A/B/C/D 回归、原始输入独立行为测试、精确最终 commit 独立复核、Windows/Ubuntu CI、合并及合并后回读。先做当前源码资格，再由该资格执行真实单项目；改动资格源码后，原 native green 不能作为新源码完成证据。

Native 正例覆盖 variable ode45、fixed ode4、constant/no-input、带状态 feedback、passthrough 与多个根输出；ode15s 另做候选 stiff case 并据实际结果决定是否开放。资格须至少两个不同 solver 的正例、一个受控失败与非预期早停不得成功的终止检查。实际验证输入/参数/solver 应用、完整输出、原 SLX 不变、模型副本加载/关闭及 0/1/N 跨语言数组；无输出作为 negative boundary，不列成功 case。Python fixtures 只能补充错误路径，不能替代以上 MATLAB 真实正例和出口。

tests 覆盖 frozen/status 伪造、错 project/C/D/SLX/参数/协议 SHA、旧审查决定、未批准或未知关键值、不完整输入/不合法时间与单位、solver 不适用或未 qualified、optional Statistics 失败但核心仍可用与显式必需失败阻断、output/MAT/CSV/raw/receipt 篡改、非有限输出、exit0 但失败/早停、TTL 与历史语义分离、scope/accepted 依赖闭合、只读文件不变、deferred 模块未激活。独立 agent 从原始合成题面和必要的当前来源进入 workflow，不靠 implementation tests/factory 生成应有答案。

synthetic C 批准、参数和数值只资格化仓库基础设施；不制造真实用户模型批准，不替比赛模型完成 F/G/H/I/J，不发布 v1.0.0，也不将 E 单次仿真成功说成最终数值可信或现实有效。同步 §17 协议→运行→待验证数值产物链、§18 失效边界和 §25 仿真/solver 证据限定含义。

---

# 10. Phase F — 参数辨识、Calibration 与 Optimization

## 10.1 参数来源与证据适用性

~~~text
given / derived / identified / calibrated / optimized / assumed
~~~

这些是来源角色，不是通用可信度排名。显式题设先约束任务；其它来源按当前对象、工况、单位、识别条件、独立验证与不确定性判定适用性。设计优化变量不得冒充已知物理参数，标定结果不得拿同一拟合数据宣称独立验证，假设参数不能伪装成辨识结果。

开发顺序 F→G 不代表每个项目必须执行两者。F 的辨识/标定/优化可以使用其阶段明确的最小实验协议和迭代运行；这些候选运行标为 trial，不作为最终 accepted 主证据。参数或模型确定后重新冻结最终协议、重跑和数值验证，才进入正式主证据链；G 扩展成正式批量 campaign。

## 10.2 System Identification

流程：

- input/output data audit；
- excitation adequacy；
- training/validation split；
- model order；
- delay；
- linear / nonlinear；
- residual analysis；
- fit；
- holdout validation。

优先接入 System Identification Toolbox 与官方 MATLAB Skill。

## 10.3 Calibration

基本形式：

J(theta) = L(y_obs, y_sim(theta))

必须定义：

- loss；
- weighting；
- bounds；
- identifiability；
- calibration interval；
- independent validation interval。

## 10.4 Optimization

路由：

- Optimization Toolbox；
- Global Optimization Toolbox；
- Simulink Design Optimization；
- Model-Based Calibration Toolbox；
- surrogate / expensive simulation optimization（必要时）。

## 10.5 目标函数

禁止只写“最小误差”。

必须说明现实组成，例如：

~~~text
J
= tracking error
+ energy
+ overshoot penalty
+ control effort
+ constraint penalty
~~~

以题目真实结构为准。

## 10.6 多目标

必要时采用：

- weighted sum；
- epsilon constraint；
- Pareto；
- compromise solution。

## 10.7 产物

- modules/05_identification_calibration_optimization.md
- packs/task/parameter_identification.md
- packs/task/calibration.md
- packs/task/optimization.md
- optimization evidence schema
- templates
- tests

## 10.8 2026-10-08 实施前审查与初版边界

用户授权继续下一阶段，先修订计划再实施及独立复核。E 已由 PR #6 合并为 main `6c8cbbf84364c49b85dce62db15aba9b11f55e53`，精确候选独立 938 项回归、实际九案例及三个项目、候选与 main 双平台 CI、合并回读均有分离记录；本机失败进程仍保留。三份独立 F 审查确认原 §10 缺少可执行合同，并与 C/D/E 的精确批准值绑定冲突。给参数覆盖贴 `trial` 标签不能产生执行权限。

初版版本 0.6.0 实现以下三个独立、有限串行操作，按任务条件选择，不因工具箱安装而全部激活：

- `identification.arx_111`：System Identification Toolbox 的实数稠密 SISO `iddata`/`arx`，固定阶次及单样本延迟 `[1 1 1]`、均匀采样、一阶预测损失。参数对应批准离散方程 `y[k]=a*y[k-1]+b*u[k-1]`，不自动改写为连续物理参数。训练回归矩阵实际满秩及条件数可接受；holdout 一阶预测使用其已声明的实测滞后输出，不能冒充零初态自由运行、统计独立证明或现实验证。
- `calibration.simulink_gain`：单个实数增益 `y=k*u` 的有界 `lsqnonlin`，`trust-region-reflective`、串行残差向量；每次目标计算实际运行本次拥有的 Inport→Gain→Outport 试验模型。使用同运行环境的独立 E `ode4` 资格、固定均匀测量网格及临时根端口采样，分别核验时间、实际参数、输出、solver 和恢复；任何仿真失败、提前停止、非有限值或违反诊断政策都停止本次研究，不能替换旧输出、零残差或任意罚数。
- `optimization.quadratic_sqp`：一至二维、正权重及正尺度的显式平方项目标、有限边界及有限线性不等式，`fmincon` 的串行 SQP。目标组成、目标值、尺度、单位及约束须来自批准数学表示和当前研究来源。独立重算目标及可行性，并记录实际终止/一阶最优性；算法收敛不自动证明全局最优。纯设计优化不虚构观测、训练/holdout 或参数可辨识性结果。

任意其它表达式、高阶/非线性/非均匀采样辨识、任意六块动态模型标定、Simscape/Stateflow/System Composer、SDO/MBC、Global Optimization、并行/全局/代理/多目标路由仍 deferred。`fitlm` 是静态回归候选，本轮不把它冒充 ARX 动态辨识。若后续确实使用它，仍必须把 `statistics.fitlm` 明列为 A 必需操作。复杂模型的候选与失效证据可以保留为草稿，不伪造可执行性。

## 10.9 独立研究与试验权限

新增 `core/parameter_study.schema.yaml`、模块 05、三个按需 task packs、合法未知草稿模板及只读 validator。研究区分 `draft` 与 `reviewed`，绑定项目、当前 frozen B 与完整 approved C、design/model/参数变量身份、实际来源、方法/精确方程及变量映射、候选参数单位与来源角色、初始化/边界、数据选择、loss/weights、诊断及预算、先验标准、适用性与可辨识性限制。已有 given/derived 值不能被当作未知待估参数或设计变量；准许的目标必须是当前 C 中明确提出 identified/calibrated/optimized/assumed 且具相应研究计划的参数。不要求未知参数先有 D build_ready 或 E primary_ready，也不填默认值。

研究审查决定绑定完整语义 digest、当前研究文件/来源及明确的 `action=review`；合法草稿保留未知，完整的 source-backed review 才允许该限定 trial。实际 C 人员批准是独立必要上游，F 研究审查不能代替它。研究可显式登记经来源支持的 finite 初值，不写回 C。执行只在新目录、新进程及本次拥有的模型内做已审查范围的有限候选；此 F 构造/覆盖权限仅属于已独立资格化的增益试验内核，不能开放 D 构建或 E primary 参数覆盖。

所有 F 产物是 candidate/trial。结果写入新的建议及原始证据，validator/resolver 从不修改 C、locked specification、D 参数/SLX、E 协议或项目状态。候选正式采纳必须由显式调用者准备当前新 C 设计/Brief 和实际人员批准，随后重新取得 D 实现、最终 E 冻结/主运行及后续 H 验证。F 完成不能记录 PRIMARY_RUN_COMPLETE、EVIDENCE_ACCEPTED、数值验证、真实系统有效或论文接受。

## 10.10 数据、可辨识性、目标与预算

辨识/标定使用有限实数 CSV 的明确列、单位、时间列与半开数据行范围，绑定当前 B/C 登记的实际来源 path/SHA 和数据角色。至少登记训练/标定与 holdout 两个选择；检查同路径、相同原始字节副本及原始行范围的重叠，不随机打乱时序，不自行插值/重采样或清洗缺失值。ARX 的 lag 范围也计入来源使用，训练与 holdout 不共用原始行。角色及范围闭合只能检查声明与可见重叠，不能认证真实统计独立性。

ARX 实际检查 `[y[k-1],u[k-1]]` 的秩及条件数，登记固定阶次、采样延迟、训练/预测 residual 和指标限制。增益标定实际检查输入激励不全为零、有限权重、参数范围与初值；heldout 仅在候选确定后评估，不能影响目标/参数选择。记录 identifiability 的具体依据与限制，不能从低拟合损失推断任意模型参数唯一。

优化须显式说明每个目标平方项的物理/任务含义、中心、尺度、单位、权重和线性约束；不只写“最小误差”。预算包含有限迭代/目标调用数、总进程和单次仿真超时。全部目标调用按顺序保留实际 theta、残差/目标、实际输出、错误、终止与计数；失败调用与预算终止不能丢弃或改为最优结果。正 exitflag、有限值、边界/约束、先验标准和实际诊断分别检查。候选输出不带“全局最优”“现实有效”或数值收敛接受旗标。

## 10.11 操作资格及回执

新增独立 `core/parameter_study_assurance_contract.yaml`、原生 MATLAB producer、Python qualification/study runners、profile 与 trial receipt 的只读消费者。按每个 operation 分开记录实际函数解析、产品/许可证诊断、调用、数值断言与 qualified；某个操作成功不能使其它操作 qualified。产品安装/原有 A 统计烟雾资格不能替代 ARX、优化算法或实际 Simulink 标定组合资格。原生 raw、process、log、MAT v7 数值及规范化 JSON/receipt 分别绑定；MAT MATLAB 类/实数/形状及精确数值必须独立核对，不以默认紧凑存储 dtype 误判 MATLAB double，也不吞 complex。

新 trial 要求当前同宿主/runtime/channel 的 A 与所选独立 F operation；增益标定另要求当前同 runtime E `ode4`。A 所需项取方法、研究及调用者的并集，必需项缺失/失败在启动 MATLAB 或创建产物目录前阻断。历史回执消费执行时资格及现时不可变源/数据/产物身份，当前 TTL 只控制新执行。默认时效 24 小时，未来时间、身份变化、异常/未完成进程、非零退出及字节变化均不得 qualified。某分支失败的诊断保留，不能用整体核心 green 放行。

资格至少实际执行：已知离散递推 ARX 与不同 holdout；已知增益真实 Simulink+lsqnonlin 及 heldout；已知受约束二维平方目标 fmincon；秩不足、标定仿真错误、预算终止和非法设置的正常拒绝。预设独立解析/线性代数真值及判据；负例预期通过不计为成功候选。项目 study 生产与合成 qualification 分开；手填成功标志和测试 factory 不是真实资格。

## 10.12 路由、状态、来源保护及失效

增加参数研究文字入口、parameter_identification/calibration/optimization 条件执行及候选只读复核；每次只加载相应方法的合同/module/pack。独立 `parameter_study` state scope 检查 B/C/F、历史候选及其 accepted-trial 依赖；文字范围不评估当前 runtime，all 范围另核验相应新执行 readiness。新增 PARAMETER_STUDY_REVIEWED 与 PARAMETER_CANDIDATE_COMPLETE 属于 C→F→新 C 采纳的可选分支，不插入所有项目的必经主状态链。仅显式调用者写入状态，当前研究/来源/review/候选回执缺失或改变传播依赖失效，较早范围留下 F unassessed。

保持 A 七个 source identity 文件、B schema/validator 与 D 十九个 source-bound 文件逐字节不变，包括已有 taxonomy（其中 F 名称已登记，不需要增加第二套 taxonomy）。为接入 F 修改共享 bootstrap/router/manifest/state/output/resolver 会使原 E critical-source identity 失效。必须保留旧 E 资格/运行历史，显式记录为旧源码；最终 F 源码重新取得 E 九案例及其当前资格下的三个真实项目回执，再用于新执行和合并回读。不能通过放宽 E source closure 或沿用旧绿色回执绕过。

当前 B/C 是保守完整内容绑定：研究数据一旦改变，也可能使当前 C 和下游全部 stale；本轮不宣称已实现 §18 的细粒度 validation-only 失效图。F review/status/candidate hash 是证据身份，不是人类认证、数学等价或现实独立性证明。

## 10.13 开发出口

退出项：parameter_study_checks、review_and_candidate_binding、data_split_and_identifiability、native_method_qualification、trial_receipt_and_numeric_outputs、required_operation_propagation、parameter_route_and_state、source_and_stale_checks、upstream_compatibility_and_authority、authority_and_indexes。覆盖合法未知草稿、approved null 参数、未经批准/审查、错误符号/关系/来源/单位、数据泄漏与 rank 不足、非法 bounds/预算/目标、原生错误/提前停止/不收敛/预算耗尽、缺失或被篡改输出、时效与历史分离、缺失回执的 accepted-trial stale、部分状态范围及无写入。所有 A–E 回归必需，不能删旧测试来迁就新能力。

正式阶段完成要求精确最终 commit 独立审查、从最少原始材料进入流程的独立行为测试、最终源版本真实 F 方法及单研究试验、源版本对应 E 重新资格/三项目、Windows/Ubuntu CI、单主题 PR、合并及 main 实际回读与 CI。正常/失败记录和声明范围全部保留。所有开发 decision-shaped 记录明确 SYNTHETIC INFRASTRUCTURE TEST，不冒充真实用户模型批准、现实测量、数值验证、全局最优或论文接受。G–K 不开放；本阶段不创建 Release/tag 或安装技能。

---

# 11. Phase G — DOE、Monte Carlo 与并行计算

## 11.1 目标

让批量仿真成为有设计的实验，而不是盲目网格搜索。

## 11.2 Experiment Design

候选：

- one-factor sweep；
- full factorial；
- fractional factorial；
- Latin hypercube；
- response surface；
- Monte Carlo；
- scenario matrix；
- stress test；
- boundary search。

Statistics and Machine Learning Toolbox 当前可正式进入 DOE / 统计分析候选路由。

## 11.3 Monte Carlo

记录：

- uncertain parameter；
- distribution；
- correlation；
- sample size；
- seed；
- convergence criterion；
- metric；
- confidence interval。

## 11.4 Parallel Simulation

优先：

- parsim；
- Fast Restart；
- Rapid Accelerator；
- batchsim（长任务）。

禁止：

- 无意义 parfor + sim；
- worker 反复初始化；
- 大规模保存全部冗余信号导致内存爆炸。

## 11.5 Output Reduction

使用：

- postSimFcn；
- summary metrics；
- selected signals；
- file-based output。

## 11.6 产物

- modules/06_experiment_design.md
- core/experiment_design.schema.yaml
- packs/evidence/monte_carlo.md
- templates/experiment/
- tests/test_experiment_design.py

---

# 12. Phase H — 数值有效性、敏感性、鲁棒性与多模型检验

这是 v1.0.0 的核心竞争力阶段。

## 12.1 两层验证结构

### H1 Primary Numerical Verification

只验证：

> 当前 locked model + 当前 solver + 当前 protocol 的内在数值有效性。

检查：

- simulation success；
- residual；
- constraint；
- conservation；
- tolerance；
- step refinement；
- event localization；
- convergence；
- numerical drift。

### H2 Model Verification / Alternative Worlds

在 Primary accepted 后执行：

- parameter sensitivity；
- uncertainty；
- stress scenarios；
- initial-condition robustness；
- solver comparison；
- structural model comparison；
- failure boundary。

该分层继承 mathmodel-skill “主计算有效性”和“结果深化分析”分离思想。

## 12.2 Sensitivity

按成本与问题选择：

- local derivative；
- normalized sensitivity；
- OAT；
- Morris；
- Sobol；
- variance-based；
- PRCC；
- scenario response。

高级方法必须有样本量与计算预算支撑。

## 12.3 Robustness

必须绑定具体 claim。

禁止：

> “变化不大，所以模型鲁棒。”

必须给：

- perturbation domain；
- metric；
- threshold；
- failure condition；
- disposition。

## 12.4 Solver Comparison

保持数学模型不变，只改变 numerical method。

比较：

- key outputs；
- event time；
- peak；
- integral；
- residual/error；
- runtime（仅性能 claim）。

## 12.5 Multi-model Comparison Gate

每个 material result：

~~~text
model_comparison_requirement
= required | not_applicable
~~~

### required 情形

- 主模型结构存在 material uncertainty；
- 高低 Fidelity 均合理；
- 数据驱动和机理路线都可建立；
- 简化假设可能改变结论；
- 用户/题目要求；
- 论文拟声明结构稳定性。

### 合法 comparator

必须改变：

- governing equations；
- mechanism；
- model order；
- physical abstraction；
- constitutive relation；
- coupling structure；
- state representation；
- fidelity。

### 不算模型对照

- solver 不同；
- tolerance 不同；
- seed 不同；
- parameter 不同；
- Block 名称不同；
- 等价 reformulation。

## 12.6 Comparison Protocol

固定：

- common input；
- common scenario；
- common output；
- mapping；
- metric；
- unit；
- direction；
- criterion。

## 12.7 Evidence Disposition

每项证据：

~~~text
support
modify
reject
~~~

记录：

- target_claim；
- impact_scope；
- required_action；
- return_stage。

## 12.8 产物

- modules/07_numerical_verification.md
- modules/08_model_verification.md
- core/numerical_verification_contract.yaml
- core/model_verification_contract.yaml
- packs/evidence/convergence.md
- packs/evidence/sensitivity.md
- packs/evidence/model_comparison.md
- packs/evidence/solver_comparison.md
- validator scripts
- tests

---

# 13. Phase I — Verification & Validation、测试与安全分析

## 13.1 Verification / Validation 分离

Verification：

> 是否正确实现并求解了预定模型？

Validation：

> 模型对现实系统和当前 claim 是否足够有效？

## 13.2 Verification 路线

- dimensional consistency；
- limiting case；
- conservation；
- analytic solution；
- subsystem check；
- numerical convergence；
- model connectivity；
- Model Advisor；
- Simulink Test；
- Design Verifier。

## 13.3 Validation 路线

- experiment；
- benchmark；
- literature/reference；
- holdout；
- measured trajectory；
- physical plausibility（限定为可检查的物理合理性主张）；
- cross-model evidence（限定为结构/基准对照覆盖的主张）。

结构一致、覆盖率、物理合理性或仿真成功均不自动证明对现实系统有效。每个 validation 决定必须指明目标对象、独立参考、适用工况、指标和主张边界；无独立现实证据时，不得宣称现实有效。

## 13.4 Simulink Test

按需：

- quick component test；
- persistent test；
- requirement-linked test；
- regression test。

## 13.5 Coverage

可能使用：

- decision；
- condition；
- MCDC。

覆盖率不自动等价于正确性。

## 13.6 Design Verifier

用于：

- design error；
- dead logic；
- overflow；
- division-by-zero；
- unreachable logic；
- property proving。

## 13.7 Fault Analyzer

适用于安全/可靠性题：

- fault injection；
- FMEA / FHA / FTA；
- fault scenarios；
- robustness。

## 13.8 产物

- modules/09_validation.md
- core/validation_contract.yaml
- packs/evidence/validation.md
- adapters
- tests

---

# 14. Phase J — 图表证据、论文交付与结果叙事

## 14.1 Figure Admission

每张图回答：

- 哪个问题；
- 哪个 claim；
- 哪个 evidence；
- 为什么图优于表。

禁止：

- 为图而图；
- 重复图；
- 无共同评价口径的多模型柱图；
- 默认 Scope 截图直接充当论文核心图。

## 14.2 核心图类型

按需：

- time response；
- state trajectory；
- phase portrait；
- Bode / Nyquist；
- parameter response；
- sensitivity curve；
- Monte Carlo PDF / CDF / ECDF；
- uncertainty band；
- heatmap；
- Pareto；
- convergence；
- residual；
- error distribution；
- model comparison；
- solver comparison；
- threshold/event；
- fault response；
- validation parity；
- profiler output。

## 14.3 科研绘图规范

默认：

- MATLAB R2025b；
- 白底；
- 细线；
- 色盲友好；
- 中文标题和坐标；
- 图例不遮挡；
- 单位完整；
- 必要时科学计数法；
- 矢量 PDF/EPS/SVG 或高分辨率 PNG；
- 图中数值与 accepted evidence 一致。

## 14.4 Evidence Package

至少包含：

~~~text
problem summary
model contract
model equations
parameter registry
simulation protocol
run receipt
primary results
numerical verification
sensitivity decision / evidence when required
robustness decision / evidence when required
model comparison decision/evidence
validation
figure manifest
claim manifest
paper handoff
~~~

辨识、标定、优化、敏感性、鲁棒性、不确定性及高级 V&V 根据题目和 material claim 决定是否 required。未执行时记录 not_required 的技术理由与限制，不生成虚构证据，也不为满足目录清单强制执行无信息增益的分析。普通任务的决定记录不替代用户明确要求的分析；结构 comparator 继续使用 §12.5 的 required / not_applicable。

## 14.5 Paper Handoff

传给 mathmodel-skill：

- 题目/小问；
- 模型标准名称；
- 数学推导；
- 模型假设；
- 参数来源；
- solver；
- Simulink 架构；
- 结果；
- verification；
- validation；
- figures；
- claim boundary；
- limitations。

## 14.6 论文叙事链

正文功能：

~~~text
MODEL
→ SIMULATION SETUP
→ SOLVE / RUN
→ RESULT
→ VERIFY
→ VALIDATE
→ CLAIM
~~~

不能写成“打开 Simulink—拖模块—点击 Run”的软件流水账。

## 14.7 产物

- modules/10_figure_evidence.md
- modules/11_paper_delivery.md
- core/evidence_contract.yaml
- core/paper_handoff_contract.yaml
- adapters/paper/mathmodel_skill_handoff.md
- templates/evidence/
- templates/paper_handoff/
- tests/test_evidence_contract.py

---

# 15. Phase K — 全量审计、R2025b 资格验证与 v1.0.0 发布

## 15.1 静态审计

检查：

- 路径；
- 版本；
- Authority；
- schema；
- producer/consumer；
- duplicate rules；
- stale terms；
- dead files；
- upstream names；
- MATLAB release；
- toolbox names。

## 15.2 语义漂移审计

重点：

- model / solver 混淆；
- verification / validation 混淆；
- sensitivity / robustness 混淆；
- model comparison / solver comparison 混淆；
- installed / licensed / callable 混淆；
- result / claim 混淆。

## 15.3 R2025b Qualification Cases

至少建立五类端到端测试。

### Case 1：一阶/二阶控制系统

验证：

- problem audit；
- Simulink build；
- solver；
- step response；
- control metrics；
- numerical verification；
- paper evidence。

### Case 2：非线性动态系统

验证：

- ODE；
- stiffness/event；
- solver comparison；
- phase portrait；
- sensitivity。

### Case 3：Simscape 物理系统

验证：

- physical network；
- conservation；
- Simscape solver；
- multidomain evidence。

### Case 4：参数辨识 + Calibration

验证：

- data role；
- system identification；
- calibration；
- holdout validation；
- uncertainty。

### Case 5：Monte Carlo + Multi-model

验证：

- parsim；
- seed；
- uncertainty；
- structural comparator；
- claim disposition。

## 15.4 CI

至少包括：

- Markdown path/link check；
- YAML parse；
- schema validate；
- Python unit tests；
- authority graph；
- index completeness；
- upstream mapping check；
- version consistency。

如果没有 MATLAB R2025b CI runner：

- 可以做静态 CI；
- 不得伪称 MATLAB runtime qualification 已通过；
- runtime qualification 由本地 R2025b 证据补齐。

## 15.5 Release Gate

v1.0.0 发布前必须：

- Phase A–K 全部 passed；
- active index 完整；
- CI passed；
- R2025b qualification evidence 完整；
- Statistics Toolbox 状态无历史冲突；
- upstream mapping current；
- 无未关闭高风险 semantic debt；
- paper handoff 端到端通过；
- CHANGELOG 完整；
- RELEASE_CHECKLIST passed。

---

# 16. 上游 Skill 适配矩阵

初始候选映射，实施时必须按上游当时版本复核：

| 本仓库能力 | 优先上游 Skill / Toolkit |
|---|---|
| 建 Simulink 模型 | building-simulink-models |
| Plant 设计 | specifying-plant-models |
| 运行仿真 | simulating-simulink-models |
| 输入数据 | authoring-simulink-inputs |
| Simulation Data Inspector | create-sdi-run |
| 并行仿真 | simulink-run-parallel-simulations |
| 测试 | testing-simulink-models |
| 线性化 | simulink-linearize |
| 频率响应 | simulink-frequency-response |
| Simscape | official physical-modeling skills |
| MATLAB 优化 | matlab-solve-optimization |
| 系统辨识 | matlab-identify-linear-system |
| MATLAB 性能 | matlab-optimize-performance 等 |

第三方扩展：

- simulink/skills 中 profiler / solver profiler / debug；
- 仅在官方能力缺口明确时接入；
- 接入前检查 license、release、工具重叠、安全面和 fallback。

---

# 17. 数据与证据 Authority

## 17.1 Source of Truth 链

~~~text
题面/附件
↓
Problem Contract
↓
Locked Model Contract
↓
Parameter Provenance + Domain Mapping
↓
Implementation Files + Actual Structure Receipt
↓
Simulation Protocol
↓
Run Receipt
↓
Primary Evidence
↓
Verification Evidence
↓
Validation Evidence
↓
Claim Manifest
↓
Paper Handoff
~~~

## 17.2 禁止反向改写

禁止：

~~~text
看到结果
→ 反推题意
~~~

禁止：

~~~text
solver 跑得稳定
→ 反推模型正确
~~~

禁止：

~~~text
论文需要亮点
→ 补写未真实执行的高级分析
~~~

---

# 18. Stale 传播规则

## 18.1 改题意

~~~text
problem
→ model
→ simulation protocol
→ run
→ verification
→ validation
→ paper
全部 stale
~~~

## 18.2 只改 solver tolerance

本规则指独立 E 协议内的 solver/tolerance 变更，C 内容及其完整批准、D 参数/映射/SLX 均保持不变。若同时修改 C solver_plan/Brief 等设计字节，仍依 §7 的完整批准和其下游失效规则处理；数学结构身份未变不能替代当前完整设计批准。

~~~text
model 保持
simulation protocol stale
run stale
numerical verification stale
依赖该运行的 model verification / validation / claim stale
相关 figures / paper stale
~~~

## 18.3 只改 figure style

~~~text
model 保持
numerical evidence 保持
figure render stale
paper figure anchor stale
~~~

## 18.4 改模型结构

~~~text
model approval
及其全部下游 stale
~~~

## 18.5 参数、数据、工况与环境变化

- D参数登记、映射、SLX、实际构建代码或其依赖变化：相应mapping/implementation/structure及实际依赖的下游失效；未变历史结构按当时完整资格回读，当前环境TTL只限制新的执行。
- E协议、场景/输入源、solver/tolerance/logging、实际仿真源码或输出/receipt变化：相应protocol/run及实际依赖的下游失效；未变历史运行按当时完整A/E资格与当前身份回读，当前TTL到期不伪造历史失败也不授予新执行许可。
- 参数、控制器、初值、边值、输入或场景变化：协议、运行及实际依赖的验证、主张、图表和论文失效；不自动改写题意。
- 辨识/标定数据变化：相关参数和模型选择依据及下游失效；独立验证数据变化只使相关 validation、claim 和交付失效。
- runtime/宿主、probe/合同、必要操作、输入或有效期变化：环境 profile 与依赖它的路由/环境状态失效并重检。后续运行按实际依赖传播，不删除历史证据。
- 每项失效必须记录变化原因、影响范围与回退阶段；无依赖的产物保持有效，不用单个全局 stale 布尔值替代依赖追踪。

---

# 19. MATLAB / Simulink 代码质量规范

MATLAB 脚本/函数应具备：

- R2025b 兼容；
- 参数集中定义；
- 路径健壮；
- dependency check；
- dimension check；
- finite value check；
- unit assumption；
- solver diagnostics；
- random seed；
- logging；
- result save；
- error reporting；
- clear main entry。

避免：

- 大量隐式 base workspace；
- magic number；
- 扫描时污染 slx；
- 随意 set_param；
- 不检查 simulation errors；
- 无版本/参数记录；
- 不可追踪的 GUI-only 操作。

---

# 20. 仿真性能策略

性能优化顺序：

~~~text
先保证模型正确
→ profile
→ 定位瓶颈
→ 减少无用 logging
→ Fast Restart
→ 优化初始化
→ parsim
→ Rapid Accelerator
→ model/fidelity optimization
~~~

禁止一开始为了速度牺牲模型语义。

---

# 21. 失败策略

每个模块必须明确 failure route。

## 21.1 环境失败

- capability unavailable；
- 给 fallback；
- 不静默降级。

## 21.2 模型失败

- 回 Phase C；
- 不靠调 solver 隐藏。

## 21.3 Solver 失败

- 回 Phase E；
- 判断 stiffness / algebraic loop / event / tolerance。

## 21.4 Calibration 失败

检查：

- identifiability；
- excitation；
- bounds；
- loss；
- data quality。

## 21.5 Robustness 失败

- modify/reject claim；
- 必要时回 model。

## 21.6 Validation 失败

- 不能继续原强 claim；
- 缩小适用范围或重构模型。

---

# 22. 论文与答辩支持

虽然完整论文优先交给 mathmodel-skill，但本仓库必须让用户能够回答：

- 为什么选这个模型；
- 为什么选这个 solver；
- 为什么这样设步长；
- 参数从哪里来；
- Simulink subsystem 各自做什么；
- 为什么结果可信；
- 是否做收敛；
- 是否换 solver；
- 是否换模型；
- 参数是否敏感；
- 实验/数据验证如何；
- 失效边界在哪里；
- 模型不足是什么。

Evidence Package 必须面向答辩可解释性。

---

# 23. 每个 Phase 的 PR 模板

每个 PR 至少说明：

## Scope

属于哪个 Phase / WP。

## Authority Changes

修改哪些 Authority。

## Behavior Changes

路由或用户行为发生什么变化。

## Evidence

新增哪些测试、fixture、示例。

## Compatibility

R2025b 与上游兼容情况。

## Stale Impact

影响哪些已有 artefact。

## Deferred

明确留给后续的内容。

禁止把 Deferred 内容假装“顺手做完”。

---

# 24. 版本策略

建议：

~~~text
0.1.x  bootstrap / governance
0.2.x  problem audit
0.3.x  model design
0.4.x  Simulink mapping
0.5.x  runtime & solver
0.6.x  identification / optimization
0.7.x  experiment design
0.8.x  verification / V&V
0.9.x  evidence / paper / release candidate
1.0.0  qualified stable release
~~~

实际 minor 切分可调整，但 1.0.0 Gate 不降低。

---

# 25. 最终验收矩阵

| 目标 | 必需证据 |
|---|---|
| 题意不漂移 | Frozen Problem Contract |
| 模型可解释 | Model Contract + Approval |
| Simulink 实现追踪与结构 | 当前批准C + Parameter Provenance + Mapping Review + 原生SLX/Structure Receipt；不自动证明数学等价或物理有效 |
| 仿真可复现 | 当前冻结Simulation Protocol + 完整实际Run Receipt/原始数值输出 + 执行时A/E操作资格；不等于数值收敛或现实有效 |
| 参数有来源 | Parameter Provenance |
| Solver 决策可审查 | typed Solver Decision + 实际有效配置/终止Diagnostics + 对应操作资格；solver comparison/数值验证仍依H |
| 数值可信 | Primary Numerical Verification |
| 结论稳定 | Sensitivity / Robustness Evidence |
| 结构可信 | Model Comparison Decision / Evidence |
| 现实有效 | Validation Evidence |
| 图有用途 | Figure Evidence Manifest |
| 论文不夸大 | Claim Manifest + Paper Handoff |
| R2025b 可用 | Qualification Cases |
| 仓库无漂移 | Lint + Authority Audit |

---

# 26. 实施顺序冻结

后续严格按照：

~~~text
PLAN APPROVED
↓
Phase A
↓
Phase B
↓
Phase C
↓
Phase D
↓
Phase E
↓
Phase F
↓
Phase G
↓
Phase H
↓
Phase I
↓
Phase J
↓
Phase K
↓
v1.0.0
~~~

只允许在同一 Phase 内并行做互不依赖的 tests/docs。

禁止跨越关键 Gate：

- Problem 未冻结，不建正式模型；
- Model 未批准，不形成正式实现；
- Simulation Protocol 未冻结，不把运行结果列为主证据；
- Primary Numerical Verification 未通过，不进入广义 claim；
- Validation 未完成，不声称现实有效；
- Evidence 未 accepted，不进入正式论文主张。

---

# 27. 本计划批准后的第一批动作

原计划写入时暂停实现。用户于 2026-10-07 明确授权“开始进行修改”，并要求先审查、必要时先调整计划再实施；此授权适用于本次按阶段开发，不需要重复确认常规修订。

当前第一批修改只允许属于 Phase A：

1. 修正 Statistics and Machine Learning Toolbox 的旧 quarantine；
2. 建立 bootstrap.yaml；
3. 建立 runtime assurance；
4. 建立 workflow router；
5. 建立 module manifest；
6. 建立 project state；
7. 建立 output contract；
8. 建立最小 lint / tests；
9. 更新 README / SKILL / index；
10. 完成 Phase A 自检；
11. 提交独立 Phase A PR；
12. Phase A 通过后才进入 Phase B。

---

# 28. Release Definition of Done

simulation-modeling-skill v1.0.0 不是“仓库里已经有很多 Skill 文件”就算完成。

完成必须意味着：

> 给定一道新的仿真建模竞赛题，系统能够从题面开始，形成可审查的系统与模型定义；根据 R2025b 当前能力选择 MATLAB / Simulink / Simscape / Stateflow 路线；生成或指导可运行仿真；按任务需要完成参数辨识、标定或优化；对数值、参数、场景、求解器和模型结构进行相应检验并记录每项分析的决定与证据边界；完成适用于目标主张的 Verification & Validation；形成科研级图表与可追踪证据；最后把内容可靠交接给论文写作模块，而且每个核心论文主张都能追溯到真实模型和真实仿真证据。

这才是 v1.0.0 的最终完成定义。
