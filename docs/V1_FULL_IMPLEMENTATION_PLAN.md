# Simulation Modeling Skill v1.0.0 全流程实施计划

> **文档状态：CANONICAL IMPLEMENTATION PLAN（全量实施主计划，2026-10-07 审查修订）**
> 仓库：Vexushi1/simulation-modeling-skill  
> 主目标版本：v1.0.0  
> 强运行基线：MATLAB R2025b + Simulink R2025b  
> 当前启动分支：bootstrap/v0.1.0-architecture  
> 当前架构 PR：Draft PR #1  
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

以下是单个建模项目的目标运行状态链，不是仓库开发 Phase A–K 的完成状态。开发阶段只登记已实现且测试通过的能力；未实现的项目状态可以保留在目标图中，但不得被当前 router 激活或通过。Phase A 实现 NEW 与 ENVIRONMENT_ASSURED；Phase B 只增加 PROBLEM_AUDITED 与 PROBLEM_FROZEN。下图是典型工作顺序，纯文本审题可以从 NEW 开始；环境 readiness 与题意状态独立，问题已冻结不代表数值执行已获许可。

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

## 7.4 Fidelity Ladder

~~~text
F0 conceptual
F1 lumped / low-order
F2 mechanism-complete engineering
F3 multidomain / high-fidelity
F4 benchmark / reference / high-cost
~~~

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

## 7.8 产物

- modules/02_model_design.md
- core/model_contract.schema.yaml
- core/model_approval_contract.yaml
- templates/contracts/model_approval_brief.md
- scripts/validate_model_contract.py
- tests/test_model_contract.py

---

# 8. Phase D — 数学模型到 Simulink / Simscape / Stateflow 映射

## 8.1 目标

将 locked_model_spec 映射为工程实现，同时保证数学语义不改变。

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
| Simulink 实现一致 | Mapping Evidence |
| 仿真可复现 | Simulation Protocol + Run Receipt |
| 参数有来源 | Parameter Provenance |
| Solver 合理 | Solver Decision + Diagnostics |
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
