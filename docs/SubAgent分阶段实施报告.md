# Sub Agent 分阶段实施报告

本文档在既有讨论结论之上，给出 **uni-agent** 上单层 Sub Agent 的 **分阶段目标、交付物与测试验收条件**。与当前架构对齐：父级与子级均为同一套 `Orchestrator.run()`，子级 **不得** 再次委派（单层硬约束）。

---

## 1. 背景与目标

### 1.1 问题

复杂任务在单条 plan 中过长时，规划与执行耦合紧、上下文膨胀、排障困难。通过 **有边界的二次 `run`**，将「可独立验收」的子目标交给子 agent，父级仅消费 **有界交付物**，可提升可控性与可观测性。

### 1.2 总体目标

- **单层委派**：仅允许父 → 子一级；子 run 内 **不提供** 委派能力。
- **触发时机**：MVP 由 **规划器在计划中加入委派步骤**；后续阶段可补充路由与策略。
- **默认共享**：与子讨论一致，MVP 默认共享 `workspace`、配置与技能目录；**安全隔离** 通过后续阶段的子 Profile 补齐。

### 1.3 非目标（全文适用）

- 多层递归委派、子 agent 并行池、跨进程/容器隔离（可作为更后阶段单独立项）。
- 替代现有 Skill 机制；Sub Agent 与 Skill **互补**，不合并。

---

## 2. 设计原则（各阶段共同遵守）

| 原则 | 说明 |
|------|------|
| 有界传递 | 父 → 子：`task` + `context` 等字段 **设字符上限**；禁止默认附带完整 `prior_context`。 |
| 可关联 | 至少能通过 **子 `run_id`** 定位子 run；后续阶段将 `parent_run_id` 写入落盘或事件。 |
| 失败可解释 | 子 `failed` 或异常时，父级该步仍能得到 **结构化或可解析文本**，便于重规划或对用户说明。 |
| 契约稳定 | 工具名、入参键名、返回文本前缀或 JSON 形状 **版本化文档化**，避免静默变更。 |

---

## 3. 阶段划分概览

| 阶段 | 名称 | 核心价值 |
|------|------|----------|
| **阶段一** | MVP：委派工具 + 子 Orchestrator | 可跑通「一步委派、子独立落盘、单层约束」 |
| **阶段二** | 观测与关联 | 父/子 `run_id` 关联、流式事件可区分、可选结构化交付 |
| **阶段三** | 路由与预算 | 何时委派、子 run 独立预算与超时 |
| **阶段四** | 子 Profile 与安全 | 只读/缩工具集/策略，使委派具备隔离语义 |

各阶段 **可独立验收**；建议按顺序交付，避免阶段二依赖未完成的阶段一。

---

## 4. 阶段一：MVP（委派工具 + 子 Orchestrator）

### 4.1 范围

- 新增内置工具 **`delegate_task`**（或由项目最终定名，全文暂用此名）。
- **`build_orchestrator(enable_delegation: bool)`**（或等价机制）：`True` 时注册委派 handler；`False` 时 **不注册** 该工具，保证子 run 无法委派。
- 子调用：`child_orchestrator.run(subtask_effective, session_context=...)`，`subtask_effective` 由 `task`、可选 `context`、可选 `include_session` **有界拼接**。
- 工具返回：**有界文本**，至少包含子 `run_id`、子 `status`、结论/输出摘要（格式见阶段一验收）。

### 4.2 交付物

- [ ] `ToolRegistry` 中 `delegate_task` 的 `ToolSpec` 与描述（规划器可见）。
- [ ] 委派 handler：构造子 Orchestrator、执行 `run`、格式化返回字符串。
- [ ] 规划侧文档或系统提示 **简短说明**：何时使用委派、子任务应单一可验收（如 `system_prompts.py` 或设计文档引用）。
- [ ] 单元测试：子 registry **无** 委派 handler；委派 handler 在 mock 下返回约定格式。

### 4.3 测试与验收条件

**功能**

1. 父级计划中包含一步 `delegate_task`，且参数合法时，**`.uni-agent/runs/`（或配置的 `task_log_dir`）中出现两条记录**：父 `run_id`、子 `run_id`（顺序与实现无关，但必须可区分两条）。
2. `uni-agent replay <child_run_id>` 能加载子 run 的 `TaskResult`，且子 plan 中 **不出现** `delegate_task` 工具名（子侧工具集无委派）。
3. 父级该步 `output`（或工具返回写入的步骤输出）中 **可解析出** 子 `run_id` 与子 `status`（`completed` / `failed`）。

**约束**

4. 当 `context` 或拼接后文本超过实现定义的上限时，**截断不抛未处理异常**，且子调用仍发起（或使用截断后文本）。
5. 子 `Orchestrator.run` 若抛错，委派 handler **捕获** 并返回含 `STATUS=failed` 或等价标记的文本，**不导致父进程崩溃**。

**回归**

6. 未使用委派时，现有 `uni-agent run` / 测试套件行为 **无破坏性变更**（或与明确列出的兼容性说明一致）。

---

## 5. 阶段二：观测与关联

### 5.1 范围

- **落盘关联**：`TaskRunRecord` 或 `TaskResult` 增加可选字段 **`parent_run_id`**（子 run 写入）；或并行维护轻量 **索引文件**（二选一，文档固定一种）。
- **流式事件**：子 run 产生的 `stream_event`（若开启）带 **`delegation` 元数据**（如 `parent_run_id`、`phase: child`），避免与父级 NDJSON 混淆。
- **交付物格式**：可选支持 **JSON 块**（仍作为工具返回字符串内嵌），字段含 `child_run_id`、`status`、`conclusion`、`output_snippet`、`error`。

### 5.2 交付物

- [ ] 子 run 落盘含 `parent_run_id`（或等价索引）。
- [ ] 文档更新：README / 开发文档中「回放与委派」一小节。
- [ ] 若启用流式：事件 schema 说明（类型与字段）。

### 5.3 测试与验收条件

1. 执行一次委派后，子 run 的落盘 JSON **可被脚本或单元测试读出** `parent_run_id`，且与父 `run_id` 一致。
2. 父级 `replay` 不要求直接展开子 plan；但文档或 CLI 说明如何通过 `parent_run_id` / `child_run_id` **跳转排查**。
3. （若实现流式）在同一会话中父、子均 `--stream` 时，子事件均带 `delegation.phase=child`（或约定等价字段），**抽检 10 条事件**满足约定。
4. 阶段一验收用例 **全部仍通过**。

---

## 6. 阶段三：路由与预算

### 6.1 范围

- **委派路由**（可选其一或组合）：规则表、关键词、轻量 LLM 分类器，输出「是否委派 + 子 `task` 草稿」（MVP+ 不强制改 planner 结构）。
- **子 run 预算**：独立 `max_failed_rounds`、可选 **wall-clock 超时**、可选最大工具步数；写进 `Settings` / 子调用参数。
- **规划初期委派**（可选）：在父 `Orchestrator.run` 进入主循环前，若路由命中，则 **先执行子 run**，再将摘要注入 `session_context` 或 `task` 前缀（与工具型委派 **二选一或并存**，文档写明优先级）。

### 6.2 交付物

- [ ] 配置项：`UNI_AGENT_DELEGATE_*` 或子集预算相关变量（具体命名在实现 PR 中固化）。
- [ ] 路由模块（若采用）：单测覆盖 **命中 / 未命中**。
- [ ] 子超时：超时后子 `status=failed`，父级收到明确 `ERROR` 或 `STATUS=failed`。

### 6.3 测试与验收条件

1. 子 run 在 **人为缩短** 的 `max_failed_rounds` 下，**失败退出**且父级委派步输出中标明 **预算耗尽** 或等价原因。
2. （若实现 wall-clock）子 run 超时时，子进程/线程无悬挂；父级可在合理时间内拿到失败交付文本。
3. 路由：**至少 3 条** 固定用例（应委派 / 不应委派）在单测中稳定通过。
4. 阶段一、二验收用例 **全部仍通过**。

---

## 7. 阶段四：子 Profile 与安全

### 7.1 范围

- **子 Profile**：构造子 Orchestrator 时使用 **缩小的工具集**（例如仅 `file_read`、`search_workspace`、`memory_search`）与/或 **更严的 `http_fetch`、沙箱白名单**。
- **配置**：`delegate_profile=readonly|full`（示例）或独立 YAML；默认与阶段一行为兼容（`full` = 与父一致）。
- **文档**：明确「委派 **不** 默认提供更强隔离，除非启用 Profile」。

### 7.2 交付物

- [ ] 子 `ToolRegistry` 构建路径：按 profile 注册 handler。
- [ ] `.env.example` 增加 profile 相关注释。

### 7.3 测试与验收条件

1. `readonly`（或等价）profile 下，子 run 内 **无法** 调用 `file_write` / `shell_exec`（ planner 即使产出该步，执行应 **失败** 或工具不存在 —— 实现选型在 PR 中二选一并写清）。
2. 父级仍为 **full** 工具时，行为与阶段一一致（回归）。
3. 安全相关单测：**子侧** 对禁止工具的调用 **100%** 被拒绝（与实现策略一致）。

---

## 8. 风险与依赖

| 风险 | 缓解 |
|------|------|
| 规划器滥用委派 | 系统提示 + 阶段三路由 + 子预算 |
| 父级「工具 completed 但业务失败」 | 文档约定 + 阶段二结构化 `status` |
| 日志混乱 | 阶段二事件与 `parent_run_id` |
| 成本上升 | 子预算、默认不开启预委派 |

---

## 9. 文档与版本

- 本文档版本与仓库 **Sub Agent 实现 PR** 对齐；阶段交付时在本节更新 **修订记录**（日期、阶段、PR 链接）。
- 与 [设计文档](./设计文档.md)、[开发文档](./开发文档.md) 交叉引用：工具列表、环境变量、回放说明。

---

## 10. 修订记录

| 日期 | 修订 |
|------|------|
| 2026-04-15 | 初稿：四阶段划分与验收条件 |
| 2026-04-17 | 阶段一至四已在代码中落地：`delegate_task`、`bootstrap.build_orchestrator`、`TaskResult.parent_run_id`、流式 `delegation` 元数据、`UNI_AGENT_DELEGATE_*`；验收见 `tests/unit/test_delegate_task.py` 与 `tests/integration/test_delegate_integration.py`。 |

## 11. 实现索引（代码）

| 模块 | 说明 |
|------|------|
| `uni_agent/bootstrap.py` | `build_orchestrator(..., enable_delegate_tool, tool_profile, max_failed_rounds_override)` |
| `uni_agent/tools/registry.py` | `register_builtin_tools(include_delegate_task, tool_profile)` |
| `uni_agent/tools/builtins.py` | `delegate_task` handler（懒加载子 orchestrator） |
| `uni_agent/tools/delegate_format.py` | 工具返回文本格式与截断 |
| `uni_agent/tools/delegation_stream.py` | 子 run 流式事件包装 |
| `uni_agent/agent/run_context.py` | 当前 `run_id` / `session_context`（供委派读取） |
| `uni_agent/agent/orchestrator.py` | `run(..., parent_run_id=)`、`TaskResult.parent_run_id` |
