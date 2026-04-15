# Agent 运行流程与领域模型

本文概括 **uni-agent** 作为可插拔 Skills 的 Agent Client：一次任务如何被编排，以及核心领域对象如何定义。实现以 `src/uni_agent` 为准，与设计文档 §6–7 一致。

---

## 1. 领域模型

核心类型定义在 `src/uni_agent/shared/models.py`（Pydantic），表示**一次运行**及其**计划步骤**的契约。

| 模型 | 职责 |
|------|------|
| `TaskStatus` | 步骤/任务生命周期：`pending` → `running` → `completed` / `failed`。 |
| `ToolSpec` | 注册表中的工具：名称、描述、风险等级、`input_schema`。 |
| `SkillSpec` | 本地 skill：元数据（`name`、`version`、`description`、`triggers`、`priority`）、`allowed_tools` / `required_tools`（可选；**不**限制规划器可见工具）、路径 `path`；加载器还会填充 `instruction_text`、`reference_paths`、`script_paths`、`skill_load_format`。 |
| `PlanStep` | **原子执行单元**：`id`、`description`、`tool`、`skill`（可选）、`arguments`、`status`、`output`、失败时的 `error_*` / `failure_code`。 |
| `TaskResult` | **单次 run 的结果**：`run_id`、`task`、`status`、`selected_skills`、`available_tools`、**累积的** `plan`、`output`、`error`、`orchestrator_failed_rounds`、`conclusion`。 |
| `TaskRunRecord` | 落盘封装：`run_id` + `TaskResult`（供回放）。 |

关系可概括为：**TaskResult 由多条 PlanStep 组成；每步绑定一个 tool，并可标注来源 skill；工具与 skill 的静态描述分别对应 ToolSpec 与 SkillSpec。**

---

## 2. 运行流程（Orchestrator）

`Orchestrator.run()`（`src/uni_agent/agent/orchestrator.py`）驱动从用户任务到 `TaskResult` 的全流程。

### 2.1 准备阶段

1. 生成 `run_id`（`TaskStore`）。
2. `SkillLoader.load_all()` 加载全部 skill；`SkillMatcher.match(task)` 打分，取 **前 2 个** 作为 `selected_skills`（供 `TaskResult`、LLM 用户提示中注入「Selected skill instructions」，以及步骤上可选的 `skill` 标注；**不**收窄规划器可见的内置工具集合）。
3. `ToolRegistry.list_tools()` 得到当次可用工具列表：**始终为注册表中的全部内置工具**，与 `selected_skills` 或 `SkillSpec.allowed_tools` 无关。

### 2.2 分支

- **`--plan` 静态计划**：跳过 Planner，直接执行文件中的步骤；成功条件为该批步骤全部 `completed`。
- **自动规划**（默认）：进入 **规划 → 执行 →（失败则带 prior 再规划）** 循环。

### 2.3 自动规划主循环

1. `prior_context`：将**已执行步骤**（含截断的 output / error）格式化为文本；首轮为空。
2. `planner.create_plan(task, selected_skills, tools, prior_context=..., session_context=...)`  
   - `session_context`：交互客户端传入的会话压缩摘要。  
   - Planner 实现：`HeuristicPlanner` 与/或 `PydanticAIPlanner`（LLM 结构化计划，可回退启发式）；共享部分意图短路（如回忆类 → `memory_search`）。
3. `executor.execute(plan)` 逐步调用工具；步骤 id 会加上轮次前缀 `r{n}-`。
4. 若本批**全部** `completed` → 成功结束循环。  
5. 否则 `failed_rounds` 递增，将本轮结果并入 `accumulated`，下一轮带着新的 `prior_context` **再规划**；若空计划或持续失败，计数至 `max_failed_rounds` 则停止。

**成功判定（当前实现）**：累积 `plan` 中**每一步**均为 `completed` 时任务为 `completed`；若存在未修复的失败步骤或轮次耗尽，则为 `failed`（详见设计文档 §7.2）。

### 2.4 收尾

- 拼接各步 `output` 为总 `output`；失败时写入 `error`。
- `conclusion`：先规则摘要，若配置 LLM 再合成。
- 保存 `TaskResult` 至任务日志目录；可选通过 `stream_event` 输出 NDJSON 事件（`run_begin`、`round_plan`、`step_finished`、`round_failed`、`conclusion_*`、`run_end`）。

### 2.5 内置工具与 Skill 的关系

- **内置工具**在 `ToolRegistry` 中注册，与「是否匹配到某个 skill」正交；规划器（启发式与 LLM）每轮都能从**完整**工具清单中选步。
- **Skill** 主要提供 `instruction_text`（及 `triggers` / `description` 等匹配信号），帮助模型选对工具与步骤顺序；`allowed_tools` / `required_tools` 可作文档或后续策略字段，**当前不用于**限制规划阶段可选的工具名集合。
- 默认规划系统提示见 `src/uni_agent/agent/system_prompts.py` 中的 `DEFAULT_PLANNER_SYSTEM_PROMPT`（可通过 `UNI_AGENT_PLANNER_INSTRUCTIONS` 整体覆盖）。

---

## 3. 与架构文档中角色的对应

| 设计文档中的概念 | 代码中的主要落点 |
|------------------|------------------|
| Orchestrator | `agent/orchestrator.py` |
| Planner | `agent/planner.py`、`agent/pydantic_planner.py` |
| Execution | `agent/executor.py` + `tools/registry.py` + builtins |
| Skill | `skills/loader.py`、`skills/matcher.py`、`skills/bundle.py` |
| Sandbox | `sandbox/runner.py`（如 `shell_exec`） |
| 会话上下文 | `observability/client_session.py` 等 |
| 审计 / 回放 | `observability/task_store.py`、`cli` 的 `replay` |

**CLI 回放**：`agent replay <run_id>` 调用 `TaskStore.load`，返回当时保存的完整 `TaskResult`（不重新执行工具）；`--format` 控制 stdout 为完整 JSON、仅步骤行、或步骤 NDJSON + 末尾摘要行。

---

## 4. 相关文档

- [设计文档](./设计文档.md) — 目标边界、架构图、模块职责
- [开发文档](./开发文档.md) — 实现细节与目录
- [Skills 目录与 SKILL 说明](./Skills目录与SKILL说明.md) — skill 磁盘布局与 `SKILL.md` 约定
