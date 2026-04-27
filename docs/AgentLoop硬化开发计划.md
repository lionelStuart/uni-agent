# Agent Loop 硬化开发计划

本文承接 [uni-agent 差距分析与改进计划](./uni-agent差距分析与改进计划.md)，将 `working memory`、`verifier`、`anti-loop`、工具结果契约、状态机扩展等改进拆成可逐轮实施的开发计划。

目标是先把 **单 Agent Loop** 做稳，再扩展多 Agent 和更复杂的 harness 能力。

---

## 1. 总体目标

当前 `uni-agent` 已具备 `Orchestrator + Planner + Executor + ToolRegistry + Sandbox` 的 runtime 骨架。下一阶段的核心目标不是增加更多工具，而是让主循环具备更强的状态管理、验证和防抖能力。

本计划按以下优先级推进：

1. 显式 run 内 working memory
2. step-level verifier 与 no-progress / duplicate detector
3. 工具结果结构化 envelope
4. 状态机语义扩展
5. planner 职责拆分
6. sandbox 审计与 failure analysis
7. 受控多 Agent 增强

---

## 2. 开发原则

- 保持兼容：现有 `TaskResult`、`PlanStep.output`、`uni-agent replay`、SDK 返回结构不能在早期 round 里破坏。
- 先内部结构化，再公开契约：新增对象先作为内部字段或可选字段落盘，稳定后再作为 SDK 文档承诺。
- 优先规则 verifier：能用确定性规则判断的，不先引入 LLM 反思。
- 每 round 可单独合并：每轮都应有清晰产出、测试和文档更新。
- 不引入复杂图编排：本计划默认继续使用当前 orchestrator 主循环，不迁移到外部图框架。

---

## 3. Round 拆分总览

| Round | 主题 | 主要目标 | 主要产出 |
|------|------|----------|----------|
| Round 1 | Working Memory 基础 | 建立 run 内结构化状态 | **已完成**：`RunWorkingMemory`、动作/artifact/失败摘要、重规划 digest |
| Round 2 | Step Verifier | 每步执行后做轻量验证 | **已完成**：`StepVerifier`、内置规则、`step_verified` 事件 |
| Round 3 | Anti-loop | 检测重复动作与无进展循环 | **已完成**：`LoopGuard`、action fingerprint、replan/fail 收束 |
| Round 4 | Tool Result Envelope | 统一工具结果结构 | **已完成**：`ToolResult`、字符串兼容、`PlanStep.tool_result` |
| Round 5 | 状态机扩展 | 表达 blocked / partial / needs_review | **已完成**：扩展 `TaskStatus`，不改变默认成功判定 |
| Round 6 | Planner 职责拆分 | 分离 intent routing 与 planning | **已完成**：`IntentRouter` 承接 memory/web/delegate 显式捷径 |
| Round 7 | Harness Observability | 支持失败分析和调优 | **已完成**：`run_stats` 统计工具、状态、失败、verifier 与 loop guard |
| Round 8 | 受控 Sub-agent 增强 | 强化子任务协议 | **已完成**：`delegate_task` 保留文本输出，同时通过 `ToolResult.payload` 暴露子 run 摘要 |

---

## 4. Round 1：Working Memory 基础

### 4.1 目标

建立 run 内显式 working memory，减少 planner 对自由文本 `prior_context` 的依赖，为 verifier 和 anti-loop 提供结构化状态。

### 4.2 范围

新增内部模型，建议落点：

- `src/uni_agent/agent/working_memory.py`
- `src/uni_agent/shared/models.py` 可选增加落盘字段

建议模型：

```python
class RunWorkingMemory(BaseModel):
    facts_confirmed: list[str] = []
    actions_attempted: list[ActionRecord] = []
    artifacts_created: list[str] = []
    recent_failures: list[FailureRecord] = []
    open_questions: list[str] = []
    constraints_active: list[str] = []
```

### 4.3 实现要点

- `Orchestrator` 在 run 开始时创建 working memory。
- `Executor` 每完成一步后返回可用于更新 memory 的最小信息。
- 初期不要求 LLM 抽取事实，先用规则更新：
  - 每次工具调用写入 `actions_attempted`
  - 失败步骤写入 `recent_failures`
  - `file_write` / `run_python` 等可推断产物写入 `artifacts_created`
- `_format_prior_context` 可追加一段短的 working memory digest。

### 4.4 不做事项

- 不做长期记忆持久化。
- 不改变 `memory_search` 语义。
- 不要求所有工具立即返回结构化 payload。

### 4.5 测试

- 新增 `tests/unit/test_working_memory.py`
- 覆盖动作记录、失败记录、artifact 记录、digest 渲染
- 更新 orchestrator 单测，确认 run 后 working memory 不影响现有结果兼容性

### 4.6 验收标准

- 重规划上下文中能看到 working memory digest。
- replay 仍可读取旧 run。
- 现有 `TaskResult.output` 行为不变。

---

## 5. Round 2：Step Verifier

### 5.1 目标

在每步执行后加入轻量 verifier，优先做确定性检查，减少“工具成功但任务无效”的情况。

### 5.2 范围

建议新增：

- `src/uni_agent/agent/verifier.py`

核心接口：

```python
class StepVerification(BaseModel):
    passed: bool
    code: str
    reason: str = ""
    hints: list[str] = []

class StepVerifier:
    def verify_step(step: PlanStep, memory: RunWorkingMemory) -> StepVerification:
        ...
```

### 5.3 初始规则

- `file_read`：输出为空时标记 `empty_output`。
- `search_workspace`：无匹配时标记 `no_matches`，但不一定失败。
- `file_write`：写入后可选读回验证。
- `shell_exec`：输出为空且任务期望检查内容时给出 warning。
- `memory_search`：无命中时给出可继续 hint。

### 5.4 Orchestrator 集成

- 每个 `step_finished` 后运行 verifier。
- verifier 结果写入 stream event，例如 `step_verified`。
- 初期 verifier 只产生 warning / hints，不直接改变 `TaskStatus`。

### 5.5 不做事项

- 不做 LLM verifier。
- 不把 verifier warning 直接视为失败。
- 不改变 goal check 当前触发时机。

### 5.6 测试

- 新增 `tests/unit/test_verifier.py`
- 覆盖空输出、无匹配、失败步骤跳过验证
- 更新 stream event 相关测试

### 5.7 验收标准

- verifier 结果可在 stream event 和 run 内部状态中被观测。
- 现有成功 / 失败收束不被 verifier warning 破坏。

---

## 6. Round 3：Anti-loop / Anti-oscillation

### 6.1 目标

识别重复动作、重复计划和无进展循环，避免 agent 在长任务中消耗预算但没有新增信息。

### 6.2 范围

建议新增：

- `src/uni_agent/agent/loop_guard.py`

核心能力：

- action fingerprint
- repeated action detector
- no-progress detector
- loop guard decision

建议结构：

```python
class LoopGuardDecision(BaseModel):
    triggered: bool
    code: str
    reason: str
    suggested_action: Literal["continue", "replan", "fail"]
```

### 6.3 初始规则

- 最近 `N` 步中同一 `tool + normalized_arguments` 重复超过阈值。
- 连续多轮 `search_workspace` / `file_read` 没有新输出摘要。
- goal check 连续 mismatch 且 planner brief 相似。
- 连续失败原因相同。

### 6.4 Orchestrator 集成

- 每轮执行后调用 `LoopGuard`。
- `suggested_action == "replan"` 时，将 guard reason 注入 `outcome_feedback`。
- `suggested_action == "fail"` 时提前收束，并写入明确 error。
- 增加 `loop_guard` stream event。

### 6.5 不做事项

- 不做复杂语义相似度模型。
- 不用 LLM 判断重复。
- 不自动删除或回滚文件。

### 6.6 测试

- 新增 `tests/unit/test_loop_guard.py`
- 构造重复工具参数、重复失败、无新增输出场景
- 更新 orchestrator loop 测试，确认命中 fail-fast 或 replan

### 6.7 验收标准

- 重复动作可被稳定识别。
- 命中 loop guard 后，run 的 error / event 能解释原因。

---

## 7. Round 4：Tool Result Envelope

### 7.1 目标

为工具执行结果增加统一结构，降低 planner、verifier、conclusion 对自由文本的依赖。

### 7.2 范围

建议新增或扩展：

- `ToolResult`
- `ToolError`
- `PlanStep.tool_result` 可选字段

建议 envelope：

```python
class ToolResult(BaseModel):
    status: Literal["ok", "error", "partial"] = "ok"
    summary: str = ""
    text: str = ""
    payload: dict[str, Any] = {}
    artifacts: list[str] = []
    warnings: list[str] = []
    retryable: bool = False
    error_code: str | None = None
```

### 7.3 兼容策略

- `ToolRegistry.execute()` 初期仍允许 handler 返回 `str`。
- registry 内部将 `str` 包装成 `ToolResult(text=..., summary=...)`。
- `PlanStep.output` 继续填充 `ToolResult.text`，保持 CLI 和 replay 兼容。
- 新字段只作为附加信息落盘。

### 7.4 不做事项

- 不一次性重写所有工具输出。
- 不移除 `PlanStep.output`。

### 7.5 测试

- 更新 `tests/unit/test_tool_registry.py`
- 更新 `tests/unit/test_executor.py`
- 确认字符串 handler 和结构化 handler 都可执行
- 确认旧 replay 数据兼容

### 7.6 验收标准

- 新旧工具 handler 均可工作。
- `PlanStep.output` 保持原语义。
- verifier 可读取结构化 `tool_result`。

---

## 8. Round 5：状态机语义扩展

### 8.1 目标

让执行状态能表达更多 harness 语义，例如 blocked、partial、needs_review，而不是全部压成 failed。

### 8.2 范围

建议扩展 `TaskStatus` 或新增 step-level outcome。

候选状态：

- `blocked`
- `skipped`
- `partial`
- `needs_review`

### 8.3 兼容策略

- 如果扩展 `TaskStatus`，需要确认所有 `all(status == completed)` 判断点。
- 对 SDK 和 replay 文档说明新增状态。
- 旧状态含义不变。

### 8.4 不做事项

- 不改变默认成功判定。
- 不把 `needs_review` 自动等同于成功。

### 8.5 测试

- 更新 shared model 单测
- 更新 replay 测试
- 更新 orchestrator 成功 / 失败判定测试

### 8.6 验收标准

- 新状态能落盘、回放、输出。
- 旧 run 不受影响。
- orchestrator 对每个新状态有明确收束语义。

---

## 9. Round 6：Planner 职责拆分

### 9.1 目标

把启发式意图路由从 planner 中拆出，降低 `HeuristicPlanner` 复杂度，为后续“粗计划 + 下一步动作”做准备。

### 9.2 范围

建议新增：

- `src/uni_agent/agent/intent_router.py`

职责划分：

- `IntentRouter`：memory / web / delegate / direct fetch 等显式捷径
- `Planner`：高层计划生成与后续重规划

### 9.3 迁移方式

- 先搬迁纯规则函数，不改行为。
- 保留测试快照，确保同样输入生成同样计划。
- 后续再考虑 next-action planner。

### 9.4 不做事项

- 不重写 PydanticAI planner。
- 不引入图编排框架。

### 9.5 测试

- 迁移现有 planner 单测
- 新增 intent router 单测
- 保持 `test_heuristic_plan.py` 语义不变

### 9.6 验收标准

- 规则短路行为不变。
- `HeuristicPlanner` 职责变薄。

---

## 10. Round 7：Harness Observability 与 Eval 种子

### 10.1 目标

让运行日志不仅能 replay，还能支持失败分析和后续 eval。

### 10.2 范围

建议新增：

- run-level summary stats
- failure taxonomy aggregation
- loop guard trigger counts
- verifier warning counts
- goal check mismatch reasons

### 10.3 文档与案例

从现有 `docs/cases/` 和测试中整理一批最小 eval 种子：

- 文件读写
- workspace 搜索
- web search / fetch
- memory search
- delegate_task
- goal check 重规划

### 10.4 不做事项

- 不先接复杂评测平台。
- 不要求所有 eval 都调用真实 LLM。

### 10.5 测试

- 新增 stats 构造单测
- 新增 docs case 索引测试或链接检查

### 10.6 验收标准

- 每次 run 有可读的质量摘要。
- 失败原因可以按类别统计。

---

## 11. Round 8：受控 Sub-agent 增强

### 11.1 目标

在单 Agent Loop 更稳定之后，再增强 `delegate_task` 的协议与验证能力。

### 11.2 范围

建议增强：

- 子任务输入 schema
- 子任务输出 schema
- 子 run verifier
- 子 run artifact 归属
- parent / child context 边界说明

### 11.3 不做事项

- 不开放递归委派。
- 不做多层 agent 网络。
- 不让子代理共享无限制写权限。

### 11.4 测试

- 更新 delegate integration 测试
- 覆盖 readonly profile
- 覆盖子 run 失败传播

### 11.5 验收标准

- 父 run 能可靠消费子 run 的结构化结果。
- 子 run 失败不会让父 run 丢失上下文。

---

## 12. 跨 Round 交付要求

每个 round 完成前都应检查：

- 是否需要更新 [Agent运行流程与领域模型.md](./Agent运行流程与领域模型.md)
- 是否需要更新 [开发文档.md](./开发文档.md)
- 是否需要更新 README 文档索引
- 是否需要新增或调整 `tests/`
- 是否需要新增 `docs/cases/`
- 是否影响 SDK 文档和示例

---

## 13. 推荐起步顺序

建议先执行 Round 1 到 Round 3：

1. `RunWorkingMemory`
2. `StepVerifier`
3. `LoopGuard`

理由：

- 这三轮不要求大规模改动工具契约。
- 对当前 loop 稳定性收益最高。
- 可以为后续 ToolResult envelope 和状态扩展提供真实使用场景。
