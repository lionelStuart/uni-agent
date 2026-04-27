# uni-agent 差距分析与改进计划

本文基于当前仓库实现与 [Agent 研发预研与最佳实践](./Agent研发预研与最佳实践.md) 中整理的外部共识，对 **uni-agent** 现状进行对比分析，给出不足判断与分阶段改进计划。

具体开发 round 拆分见：[Agent Loop 硬化开发计划](./AgentLoop硬化开发计划.md)。

目标不是否定当前设计，而是回答两个更具体的问题：

- `uni-agent` 已经做对了什么
- 相比当前较稳定的 Agent best practice，下一步最值得补的缺口是什么

---

## 1. 总体判断

### 1.1 结论

`uni-agent` 当前已经不是“prompt + tools”的轻量 demo，而是一个具备明显 runtime 形态的 Agent Client。它已经具备以下关键基础：

- 有显式 `Orchestrator -> Planner -> Executor -> ToolRegistry -> Sandbox` 分层
- 有结构化 `PlanStep` / `TaskResult` 契约
- 有多轮重规划
- 有 `prior_context` 压缩
- 有 `goal_check`
- 有任务落盘与 replay
- 有 skills、session memory、sub-agent 委派和流式事件

这些基础能力说明项目方向是对的。

但如果按最新 Agent Harness best practice 对照，`uni-agent` 仍处于：

**“运行时骨架已建立，但 verifier、working memory、anti-loop、tool/result contract、状态机语义还不够硬”** 的阶段。

也就是说，当前主要短板不是“没有 loop”，而是：

- loop 的控制粒度还不够细
- 状态表达仍偏文本拼接
- 验证机制偏单点
- 防抖与失败恢复机制还不够工程化

---

## 2. 当前设计的优势

### 2.1 Harness 边界已经基本成型

这一点是 `uni-agent` 最重要的优点。

当前运行时装配已经比较清晰：

- `Orchestrator` 负责主循环与收束  
  见 [src/uni_agent/agent/orchestrator.py](/Users/a1021500406/private/uni-agent/src/uni_agent/agent/orchestrator.py)
- `Planner` 负责计划生成  
  见 [src/uni_agent/agent/planner.py](/Users/a1021500406/private/uni-agent/src/uni_agent/agent/planner.py)
- `Executor` 负责逐步执行工具  
  见 [src/uni_agent/agent/executor.py](/Users/a1021500406/private/uni-agent/src/uni_agent/agent/executor.py)
- `ToolRegistry` 负责工具注册与执行分发  
  见 [src/uni_agent/tools/registry.py](/Users/a1021500406/private/uni-agent/src/uni_agent/tools/registry.py)
- `LocalSandbox` 负责命令边界  
  见 [src/uni_agent/sandbox/runner.py](/Users/a1021500406/private/uni-agent/src/uni_agent/sandbox/runner.py)

这和当前主流的 harness thinking 基本一致。

### 2.2 上下文预算与日志压缩意识是正确的

`prior_context`、`goal_check digest`、`ContextBudgets` 都说明当前设计已经在主动处理长任务的上下文膨胀问题，而不是无条件把完整历史塞回模型。

相关实现：

- [src/uni_agent/agent/orchestrator.py](/Users/a1021500406/private/uni-agent/src/uni_agent/agent/orchestrator.py)
- [src/uni_agent/agent/goal_check.py](/Users/a1021500406/private/uni-agent/src/uni_agent/agent/goal_check.py)
- [src/uni_agent/context/budgeting.py](/Users/a1021500406/private/uni-agent/src/uni_agent/context/budgeting.py)

这点比很多只有“聊天历史直传”的 Agent 要成熟。

### 2.3 单 Agent 为主、多 Agent 为辅，这个节奏合理

当前 `delegate_task` 只做单层子 run，不允许递归委派，属于比较克制的设计：

- 避免多 Agent 图过早失控
- 便于 replay 和审计
- 符合“先单 Agent，后受控多 Agent”的最佳实践

相关实现：

- [src/uni_agent/tools/registry.py](/Users/a1021500406/private/uni-agent/src/uni_agent/tools/registry.py)
- [docs/Agent运行流程与领域模型.md](/Users/a1021500406/private/uni-agent/docs/Agent运行流程与领域模型.md)

### 2.4 技术文档已经在形成 system of record

仓库里已经有：

- 设计文档
- 开发文档
- 运行流程文档
- 预研与最佳实践文档

这比“把系统语义全塞进 prompt 或 README”要健康得多。

---

## 3. 主要不足

以下不足按优先级排序，不按模块排序。

### 3.1 缺少显式 working memory，重规划仍偏“文本回看”

当前重规划依赖的核心输入是：

- `session_context`
- `prior_context`
- `outcome_feedback`

这些输入本质上仍以文本压缩为主，见：

- [src/uni_agent/agent/orchestrator.py](/Users/a1021500406/private/uni-agent/src/uni_agent/agent/orchestrator.py)

问题在于，系统还没有一个显式、结构化、可机读的工作记忆层，例如：

- 已确认事实
- 已尝试动作
- 最近失败原因
- 已产生 artifacts
- 当前阻塞点
- 不应重复的动作

结果是：

- planner 容易重复选择类似动作
- replan 的依据仍较依赖模型自己解析历史文本
- verifier 难以直接消费运行状态

这会直接导致长任务稳定性不足。

### 3.2 `Executor` 的执行语义过于线性，缺少 richer outcome contract

当前 `Executor.execute()` 的语义比较简单：

- 顺序执行
- 单步失败即返回当前批次
- 成功时仅写入字符串 `output`
- 失败时仅写入字符串 `error_detail`

实现见：

- [src/uni_agent/agent/executor.py](/Users/a1021500406/private/uni-agent/src/uni_agent/agent/executor.py)

问题：

- 工具结果没有统一结构化 envelope
- 没有“部分成功 / 可继续 / 建议下一步”的结果层
- 无法把 step outcome 可靠地喂给 verifier
- 后续 conclusion / goal_check 仍需二次理解自由文本

这会限制后续 verifier 与 anti-loop 机制的准确性。

### 3.3 verifier 体系仍偏单点，`goal_check` 不够覆盖主循环质量控制

当前最接近 verifier 的能力是 `goal_check`，它发生在“一轮步骤全部成功之后”：

- [src/uni_agent/agent/goal_check.py](/Users/a1021500406/private/uni-agent/src/uni_agent/agent/goal_check.py)
- [src/uni_agent/agent/orchestrator.py](/Users/a1021500406/private/uni-agent/src/uni_agent/agent/orchestrator.py)

这有价值，但仍不够：

- 没有 step-level verifier
- 没有 duplicate-action detector
- 没有 no-progress detector
- 没有 artifact existence verifier
- 没有 policy gate verifier

结果是很多“应在执行中被发现的问题”，只能等到一轮做完后再由 LLM 回顾。

这会让反应太慢，也容易浪费回合数。

### 3.4 anti-loop / anti-oscillation 机制不足

当前 orchestrator 有：

- `max_failed_rounds`
- `max_step_retries`
- `goal_check` 后可再规划

但还缺少更细粒度的“抖动检测”：

- 最近几步是否重复同一工具 + 参数
- 最近几轮计划是否高度相似
- 是否在无新信息情况下重复读同一文件
- 是否连续多轮没有新增事实或产物

目前这些没有被显式建模，结果可能出现：

- 计划轻微改写但实质重复
- 搜索 / 读取 / web fetch 类动作反复打转
- 模型在“看起来忙碌”的状态下消耗预算

### 3.5 `TaskStatus` / `PlanStep` 状态表达偏窄

当前状态模型是：

- `pending`
- `running`
- `completed`
- `failed`

见 [src/uni_agent/shared/models.py](/Users/a1021500406/private/uni-agent/src/uni_agent/shared/models.py)

这个状态集对最小实现够用，但对长任务治理偏弱，因为缺少：

- `blocked`
- `skipped`
- `cancelled`
- `needs_review`
- `partial`

这会带来两个问题：

- orchestrator 难以表达“失败但可继续”与“被策略拦截”的区别
- replay 与分析时难以区分真正错误和流程控制分支

### 3.6 Planner 仍混合了启发式捷径、文本注入和工具选择，职责略重

当前 `HeuristicPlanner` 里承担了很多职责：

- 快捷意图识别
- web / memory / delegate 短路
- 路径提取
- fetch URL 选择
- shell 命令兜底

见 [src/uni_agent/agent/planner.py](/Users/a1021500406/private/uni-agent/src/uni_agent/agent/planner.py)

这在当前阶段是务实的，但问题是：

- planner 同时承担了 intent router 和 plan synthesizer
- 某些 shortcut 与后续 verifier / working memory 脱节
- planner 很难只专注在“高层计划”和“下一步动作选择”

长期看，这会增加 planner 的脆弱性和维护成本。

### 3.7 工具契约和风险分层还不够深入

当前 `ToolSpec` 有：

- `name`
- `description`
- `risk_level`
- `input_schema`

但从执行面看，还缺少一些更强约束：

- 统一输出 schema
- side effect 分类
- idempotency 标记
- 是否需要 approval
- 是否允许自动重试
- 失败类型枚举与恢复建议

相关位置：

- [src/uni_agent/shared/models.py](/Users/a1021500406/private/uni-agent/src/uni_agent/shared/models.py)
- [src/uni_agent/tools/registry.py](/Users/a1021500406/private/uni-agent/src/uni_agent/tools/registry.py)

`risk_level` 目前更像展示字段，还没有完全成为 orchestrator 的控制输入。

### 3.8 Sandbox 约束仍偏命令 allowlist，缺少更细粒度执行治理

`LocalSandbox` 当前主要控制：

- 是否在 allowlist
- timeout
- stdout/stderr 截断

见 [src/uni_agent/sandbox/runner.py](/Users/a1021500406/private/uni-agent/src/uni_agent/sandbox/runner.py)

这对 MVP 很合理，但与更成熟的 harness 相比还缺：

- 文件变更跟踪
- 写操作 diff 摘要
- 目录级配额或范围限制反馈
- 更细粒度 approval 语义
- 更明确的 side effect 审计记录

也就是说，现在的 sandbox 更像执行闸门，还不是完整的行为审计层。

### 3.9 可观测性已具备事件流，但缺少“失败分析视角”的聚合

当前有 `stream_event`、task store、replay，这很好。  
但从调优角度，还建议继续补：

- failure taxonomy 统计
- 重复动作统计
- 计划收敛率
- goal_check mismatch 分布
- 工具失败原因热图

当前 trace 更偏“过程可见”，还不是“可系统调优”。

---

## 4. 优先级判断

如果把当前缺口按“短期收益 / 工程杠杆”排序，我建议优先级如下：

1. **working memory**
2. **verifier 体系**
3. **anti-loop / anti-oscillation**
4. **工具输出结构化**
5. **状态机语义扩展**
6. **planner 职责拆分**
7. **sandbox 审计增强**
8. **多 Agent 扩展**

这里有一个核心判断：

`uni-agent` 当前最缺的不是“更多能力”，而是“让已有能力更稳定地协同工作”的控制层。

---

## 5. 改进计划

## 5.1 Phase 1：把单 Agent Loop 做硬

目标：

- 降低重复动作
- 提高 replan 质量
- 让 verifier 真正参与主循环

建议事项：

### A. 引入显式 working memory 对象

建议新增运行态结构，例如：

- `facts_confirmed`
- `actions_attempted`
- `artifacts_created`
- `recent_failures`
- `open_questions`
- `constraints_active`

最小落地方式：

- 先不引入长期存储
- 仅在 run 内维护
- 每步执行后更新
- planner / verifier / conclusion 统一读取

### B. 增加 step-level verifier

建议为每步增加轻量检查：

- 工具是否返回空结果
- 关键文件是否真的存在
- 写文件后是否能读回
- 搜索是否命中
- shell 返回是否缺少预期证据

这层 verifier 不一定都要 LLM，可以先规则化。

### C. 增加 duplicate / no-progress detector

建议在 orchestrator 中记录最近若干步指纹：

- `tool`
- 归一化参数
- 输出摘要

命中以下条件时强制触发 replan 或 fail-fast：

- 同一步骤重复超过阈值
- 同类计划连续出现
- 最近 N 步没有新增 artifact / fact

### D. 让 `goal_check` 降级为 verifier 体系的一部分

`goal_check` 应保留，但建议从“唯一事后复核器”演进为“多层 verifier 中的一层”。

---

## 5.2 Phase 2：重构工具与状态契约

目标：

- 减少自由文本理解成本
- 让 planner / verifier / conclusion 使用统一数据模型

建议事项：

### A. 给工具结果增加结构化 envelope

建议工具统一返回近似结构：

- `status`
- `summary`
- `payload`
- `artifacts`
- `warnings`
- `retryable`
- `error_code`

短期可以：

- 内部先保留字符串输出兼容
- 新增结构化结果对象
- `TaskResult` 落盘同时保存原始结果与摘要结果

### B. 扩展 `PlanStep` / `TaskStatus`

建议增加更丰富状态：

- `blocked`
- `skipped`
- `partial`
- `needs_review`

并让 orchestrator 明确区分：

- 工具失败
- 策略拦截
- 目标未满足
- 无法继续

### C. 把风险分层接入主循环控制

当前 `risk_level` 应逐步成为可执行策略，而不仅是描述。

例如：

- `high` 风险工具默认需要 verifier 或 approval
- `high` 风险动作后强制 checkpoint
- 某些重试策略只允许低风险工具使用

---

## 5.3 Phase 3：整理 Planner 责任边界

目标：

- 降低 planner 内部复杂度
- 让 loop 更容易维护和调优

建议事项：

### A. 区分 intent router 与 planner

当前 planner 中的 shortcut 逻辑可逐步拆成：

- `IntentRouter`
- `Planner`

其中：

- `IntentRouter` 负责显式捷径，如 memory / web / delegate
- `Planner` 负责高层计划与下一步动作生成

### B. 从“全量计划”转向“粗计划 + 下一步动作”

如果后续任务复杂度继续上升，建议逐步演进为：

- planner 产出高层任务图
- orchestrator 每轮只请求下一步动作

这样更符合当前较稳定的 agent loop 实践。

---

## 5.4 Phase 4：增强 Harness 与调优闭环

目标：

- 从“可运行”进入“可持续调优”

建议事项：

### A. 建立 failure analysis 视图

建议在 observability 里沉淀统计项：

- 工具失败频次
- 重复动作频次
- 空计划比例
- goal_check mismatch 原因
- 子代理成功率

### B. 强化 sandbox 审计

建议逐步增加：

- 文件变更摘要
- side effect 记录
- 写操作前后差异快照

### C. 建立小型 eval 集

建议从现有 `tests/` 与 `docs/cases/` 中抽 20 到 50 条真实任务，作为回归集，覆盖：

- 文件读写
- 搜索与检索
- web search / fetch
- sub-agent
- goal-check 重规划
- 长上下文任务

---

## 6. 不建议优先做的事

当前阶段不建议优先投入：

- 多层递归子代理
- 复杂图编排框架替换
- 大规模新增工具而不补 verifier
- 把更多知识堆进超长 prompt / AGENTS.md

原因：

- 复杂度会先于稳定性增长
- 当前主瓶颈不在能力不足，而在控制层不够硬

---

## 7. 推荐执行顺序

更务实的执行顺序建议如下：

### 第 1 批

- working memory
- duplicate / no-progress detector
- step-level verifier

### 第 2 批

- 工具结果结构化
- 状态机扩展
- 风险级别接入策略

### 第 3 批

- planner 职责拆分
- sandbox 审计增强
- failure analysis / eval

### 第 4 批

- 更强的 sub-agent 编排

---

## 8. 一句话总结

`uni-agent` 当前最大的优点，是已经有一个正确方向的 Agent Runtime 骨架。  
`uni-agent` 当前最大的不足，不是“还不够聪明”，而是“还没有把状态、验证、防抖和恢复机制做成主循环里的硬约束”。

所以下一步最值钱的工作不是扩功能，而是：

**把单 Agent loop 的 working memory、verifier 和 anti-loop 做硬。**
