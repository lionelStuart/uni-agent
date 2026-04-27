# Agent 研发预研与最佳实践

本文整理 2024 年末到 2026 年 4 月公开资料中，关于 Agent 项目研发、Harness Engineering、Agent Loop 与多 Agent 编排的较稳定共识，并将其映射到 **uni-agent** 这类本地 / 受控环境 Agent Client 的工程实践。

结合当前仓库实现的差距分析与路线建议见：[uni-agent差距分析与改进计划.md](./uni-agent差距分析与改进计划.md)。

本文不是产品宣传摘要，而是面向研发落地的预研文档。重点回答：

- Agent 项目研发是否已经有比较固定的方法论
- `plan / execute / reflection` 应如何设计
- Harness 在工程里到底承担什么职责
- 当前哪些模式已接近 best practice，哪些仍应谨慎使用
- 对 `uni-agent` 这类项目，下一步应优先补哪些能力

---

## 1. 结论摘要

截至 **2026-04-27**，Agent 研发已经形成一套相对稳定的工程思路，但尚未收敛成单一标准框架。

当前较强的行业共识是：

- 先把 Agent 当成 **运行系统**，而不是单次提示词调用。
- 先做 **单 Agent + 工具 + 验证回路**，再做多 Agent。
- 先设计 **Harness / Runtime / Sandbox / Workspace**，再增加自主性。
- `plan -> execute -> reflection` 不是每轮必做的固定三段式，稳定做法是 **轻规划、强执行、强验证、按需反思**。
- Reflection 不应成为主流程默认重步骤，而应更多下沉为 **verifier、tests、lint、goal-check、human checkpoint**。
- 长任务必须依赖 **工作区、可落盘 artifacts、上下文压缩、显式退出条件**。
- 没有 **trace、eval、failure corpus、权限边界** 的 Agent，通常只能算 demo，不能算稳定工程。

---

## 2. 最新 best practice 共识

### 2.1 先把 Agent 当系统，不当 prompt

当前主流做法不再把 Agent 理解为一段“能调用工具的 prompt”，而是如下组合：

- model
- orchestrator / harness
- tool registry
- sandbox / execution environment
- memory / artifact store
- context management / compaction
- verifier / guardrails
- observability / tracing / replay

其中模型只负责部分决策；真正决定稳定性的，往往是 harness 是否把状态、执行、验证和权限边界组织好了。

### 2.2 先 workflow，后 autonomy

目前工程上比较稳的落地方式不是“让模型完全自由行动”，而是：

- 先定义任务边界
- 再定义工具边界
- 再定义状态表示
- 再定义成功条件与失败恢复
- 最后才增加更高自主性

换句话说，Agent 不是“先让模型足够聪明”，而是“先让系统足够可控”。

### 2.3 先单 Agent，后多 Agent

这一点已经接近共识：

- 单 Agent 适合多数代码任务、文档任务、受控工具调用任务
- 多 Agent 只在任务天然可拆分、可并行、上下文依赖较弱时收益明显

典型适合多 Agent 的场景：

- 并行检索
- 多来源调研
- 多候选方案并发分析
- 宽搜型 research

典型不宜优先上多 Agent 的场景：

- 对同一代码库连续改写
- 强依赖共享状态的长事务
- 上下文耦合极高的修复任务

### 2.4 工具设计比框架选型更重要

当前一个越来越稳定的判断是：Agent 项目成败，常常更取决于工具接口是否合理，而不是框架 logo。

更稳定的工具设计模式包括：

- 工具名与参数名语义直接
- 入参 schema 严格
- 输出结构化
- 错误结构统一
- 明确副作用
- 可审计
- 失败后可恢复

对模型来说，`tool schema` 是操作系统 API，不是附属说明。

### 2.5 反思应谨慎使用

较新的工程口径不再建议“每轮反思一次”。原因很直接：

- 成本高
- 容易拖慢执行
- 容易导致计划频繁改写
- 容易出现 oscillation / dithering

更稳的做法是把反思触发为事件：

- 连续多步没有进展
- 工具结果冲突
- 关键检查点
- 高风险动作前
- 即将结束但置信度不足时

### 2.6 Harness 是一等公民

最新公开材料里，Harness 已经不再是“业务层外围胶水”，而被视为 Agent 系统的主干：

- 提供受控执行环境
- 提供 artifact / workspace
- 管理 loop
- 做上下文压缩
- 接入 AGENTS.md / docs / skills
- 管理回放、审计和可观测性
- 暴露 guardrails 与人工审批

这意味着模型本身越来越像“决策器”，而 harness 越来越像“运行时内核”。

---

## 3. Harness Engineering 的工程含义

### 3.1 Harness 的职责边界

在 Agent 工程里，Harness 至少应承担以下职责：

- 装配模型、工具、沙盒、记忆、文档和运行参数
- 维护 `goal -> plan -> act -> observe -> verify -> conclude` 主循环
- 保存运行过程中的状态、产物和中间结论
- 为模型提供稳定的工作区与可读上下文
- 对高风险动作做限制、审批或降权
- 暴露 trace、events、logs、artifacts、metrics
- 让失败可回放、可复盘、可复现

如果这些职责分散在若干脚本和 prompt 里，系统会很快失去可维护性。

### 3.2 AGENTS.md 的正确定位

较新的实践已经比较一致：`AGENTS.md` 不应承担“完整知识库”职责，更适合作为一个导航入口。

更推荐的方式是：

- `AGENTS.md` 保持短
- 写明运行约束、目录约定、验证入口、危险操作红线
- 更完整的架构、流程、规范进入 `docs/`
- 关键约束尽量可被 lint / CI / test 校验

对 `uni-agent` 这类工程，这一点尤其重要，因为 Agent 会反复读取 repo 文档；长而发散的单文档会直接污染上下文预算。

### 3.3 Workspace 与 Artifacts 是必要能力

长任务稳定性的关键，不是让模型在一个超长上下文里记住一切，而是：

- 把中间状态写入 workspace
- 把大产物落成文件
- 把计划和执行记录持久化
- 让模型按需回读文件，而不是反复复述

这类做法有三个直接收益：

- 降低上下文膨胀
- 降低状态漂移
- 提高回放与人工审阅效率

### 3.4 Verifier 比 Reflection 更值得工程化

一个成熟 harness 更该优先建设：

- goal check
- schema validation
- tool result validation
- file existence checks
- diff / test / lint checks
- completion criteria checks

而不是把“请你自我反思”作为主要质量保障方式。

---

## 4. Agent Loop 的固定实践

### 4.1 当前更稳定的 loop

面向工程的稳定 loop 更接近下面这个形式：

```text
prepare
  -> load goal / constraints / tools / memory / docs
plan
  -> produce or refresh a coarse plan
act
  -> choose and execute only the next best action
observe
  -> parse tool result and update working state
verify
  -> run completion / failure / stuck / policy checks
replan if needed
  -> only when plan is invalid, blocked, or low-confidence
finish
  -> synthesize result, save artifacts, emit conclusion
```

这里真正固定的是：

- `act`
- `observe`
- `verify`

而不是每一轮都完整做一次 heavy planning 或 heavy reflection。

### 4.2 Planning 应分层，不应一步规划到底

较稳定的实践是“两层计划”：

- 高层 `task plan`：3 到 7 步即可
- 当前 `next action`：只决定下一步动作

原因：

- 长计划很快过期
- 环境反馈会不断改变最优路径
- 完整展开计划常导致无效 token 消耗
- 过度预规划会增加后续抖动

因此更推荐：

- 初始只给粗计划
- 执行中滚动修订
- 遇到关键失败再局部重规划

### 4.3 Reflection 应变成检查点机制

当前更推荐把 reflection 视作一个条件触发模块，而不是常驻主流程。

推荐触发条件：

- 连续 `N` 步没有有效进展
- 最近 `N` 步高度重复
- 工具失败超过预算
- 观察结果与目标明显冲突
- 准备结束但 verifier 未通过
- 即将执行高风险动作

推荐输出字段：

- 当前阻塞点
- 已尝试动作
- 失败归因
- 新假设
- 是否需要 replan
- 下一步建议动作

### 4.4 Anti-oscillation / Anti-dithering 机制

当前比较固定的防抖动策略包括：

- 明确每步 `success condition`
- 为每个工具调用记录 `intent`
- 保存 working memory，避免模型忘记“已经试过什么”
- 引入 `retry budget`
- 检测重复动作、重复参数、重复计划
- 在低收益循环中强制 replan 或 fail-fast
- 设置总步数上限、总 token 预算、总 wall-clock 预算
- 将反思和计划修正限制在检查点，而不是任意触发

这类能力比“优化提示词措辞”更能稳定 Agent Loop。

### 4.5 如何提高规划与执行效果

从工程角度，最有效的手段通常不是加更长的 CoT 提示，而是：

- 缩小动作空间
- 提高工具输出结构化程度
- 增强状态表示
- 提前提供 repo / task 的关键约束
- 减少不必要工具数量
- 提供高质量 working memory
- 提供 verifier 与 completion criteria
- 提供足够好的观察信号

一句话总结：

**提高执行效果的核心是“优化外部约束与反馈”，不是“让模型空想更久”。**

---

## 5. 对 `uni-agent` 的落地建议

### 5.1 当前方向与 best practice 基本一致的部分

从现有代码与文档看，`uni-agent` 已具备多个与当前共识一致的方向：

- 明确采用 `Orchestrator + Planner + Executor + Tool Registry + Sandbox` 分层
- 已有结构化 `plan` 与多轮 replan
- 已有本地 workspace 与任务落盘
- 已有 replay
- 已有 `session_context`、`prior_context` 与 token budgeting
- 已有 goal check / conclusion
- 已有 `delegate_task` 但保持单层
- 已有 skills、AGENTS.md、可观测事件流

这些说明项目已经从“prompt agent”走向“runtime agent”，方向是对的。

### 5.2 当前应优先补强的能力

按收益排序，建议优先补以下能力。

#### A. 显式 working memory

当前有 `prior_context` 和会话上下文，但仍建议增加更显式的工作记忆结构，例如：

- `completed_facts`
- `attempted_actions`
- `open_questions`
- `known_failures`
- `artifacts_created`
- `next_constraints`

目标是减少模型在重规划时重新阅读大段历史文本的成本，并降低重复动作。

#### B. 统一 verifier 层

建议将现有 goal check 继续抽象为统一 verifier 体系，例如：

- plan-step verifier
- task completion verifier
- duplicate-action detector
- no-progress detector
- dangerous-action gate

这会比扩充 reflection prompt 更稳。

#### C. anti-loop / anti-oscillation 策略

建议在 orchestrator 层显式记录和判断：

- 最近若干步 `tool + arguments` 是否重复
- 最近若干轮 plan 是否高度相似
- 是否连续出现“读同一文件 -> 无结论 -> 再读”
- 是否连续多轮没有新增 artifact / facts

一旦命中，可触发：

- 强制 replan
- 降级为只读调查模式
- 请求人工输入
- 直接失败收束

#### D. 工具返回契约再结构化

内置工具如果还存在较多自由文本输出，建议继续统一为：

- `status`
- `summary`
- `payload`
- `error`
- `artifact_paths`
- `next_hints`

这样 planner / verifier / conclusion 都更容易消费。

#### E. docs as system of record

当前仓库中文档已经较多，下一步建议明确：

- 哪份文档是架构真源
- 哪份文档是运行语义真源
- 哪份文档是阶段性历史记录

否则 Agent 读取文档时容易吸收过时内容。

建议：

- `docs/设计文档.md` 负责架构边界
- `docs/Agent运行流程与领域模型.md` 负责运行语义
- `docs/进度文档.md` 只保留历史记录和阶段 TODO
- 本文负责“外部 best practice 与内部联系”的方法论更新

### 5.3 当前不建议优先投入的方向

以下方向现阶段不建议优先投入：

- 复杂多层多 Agent 网络编排
- 过重的图框架迁移
- 把 reflection 设计成每轮固定步骤
- 把所有 repo 规范塞进单个超长 `AGENTS.md`
- 在 verifier 体系没成型前大幅增加工具数量

理由很直接：这些投入会先放大复杂度，而不是先提升稳定性。

---

## 6. 推荐的 `uni-agent` Loop 演进方案

### 6.1 目标形态

推荐将主循环逐步演进到如下逻辑：

```text
load task + session summary + repo instructions + tool registry
  -> build coarse plan
  -> pick next action
  -> execute tool
  -> normalize observation
  -> update working memory
  -> run verifiers
  -> if blocked or repeated then replan
  -> if completed then conclude and persist artifacts
```

### 6.2 每层职责建议

#### Planner

只负责：

- 高层步骤拆分
- 下一步候选动作选择
- 必要时局部重规划

不负责：

- 代替 verifier 判断是否真的成功
- 长篇解释历史

#### Executor

负责：

- 工具调用
- 错误归一化
- 产物记录
- 观察结果结构化

#### Orchestrator

负责：

- 状态迁移
- 重试预算
- 重规划触发
- 反抖逻辑
- 完成 / 失败收束

#### Verifier

负责：

- 步骤完成判定
- 任务完成判定
- 重复动作检测
- 无进展检测
- 风险动作拦截

### 6.3 触发式 reflection 模板

如果保留 reflection，建议仅在触发时运行，并要求结构化输出：

- `issue`
- `evidence`
- `root_cause_guess`
- `what_not_to_repeat`
- `replan_needed`
- `suggested_next_action`

这样 reflection 才能被 orchestrator 真正消费，而不是变成纯文本自言自语。

---

## 7. 研发路线建议

若按“先稳定，再扩展”排序，建议下一阶段路线如下：

### Phase A：稳定单 Agent Loop

- 补 working memory
- 补 verifier 分层
- 补 anti-loop / anti-oscillation
- 工具输出进一步结构化
- 明确 docs 真源关系

### Phase B：增强 Harness

- 更细粒度权限 / 风险分级
- 更清晰 artifact 目录与索引
- 更好的 trace / replay / failure analysis
- 更显式的 compaction 策略

### Phase C：受控多 Agent

- 只在 research / delegate 场景扩大使用
- 明确 manager-worker 协议
- 强制子任务输入输出 schema
- 严控共享状态和递归深度

这条路线比“先把多 Agent 做复杂”更符合当前公开 best practice。

---

## 8. 参考资料

以下材料用于形成本文结论，日期均以公开发布时间为准。

### OpenAI

- 2026-04-15: [The next evolution of the Agents SDK](https://openai.com/index/the-next-evolution-of-the-agents-sdk/)
- 2026-03-11: [From model to agent: Equipping the Responses API with a computer environment](https://openai.com/index/equip-responses-api-computer-environment/)
- 2026-02-11: [Harness engineering: leveraging Codex in an agent-first world](https://openai.com/index/harness-engineering/)
- 2025-03-11: [New tools for building agents](https://openai.com/index/new-tools-for-building-agents/)
- OpenAI Business: [A practical guide to building AI agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/)

### Anthropic

- 2024-12-19: [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- 2025-06-13: [How we built our multi-agent research system](https://www.anthropic.com/engineering/built-multi-agent-research-system)
- 2024-11-25: [Introducing the Model Context Protocol](https://www.anthropic.com/news/model-context-protocol)

### Google

- 2026-01-28: [Towards a science of scaling agent systems](https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/)
- 2025: [An introduction to Google’s approach for secure AI agents](https://research.google/pubs/an-introduction-to-googles-approach-for-secure-ai-agents/)
- 2025-04-09: [A2A: A new era of agent interoperability](https://developers.googleblog.com/a2a-a-new-era-of-agent-interoperability/)

### 论文 / 方法参考

- [ReAct: Synergizing Reasoning and Acting in Language Models](https://react-lm.github.io/)
- [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366)
