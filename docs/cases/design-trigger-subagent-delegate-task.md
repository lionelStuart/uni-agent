# 设计案例：如何触发 Sub Agent（`delegate_task`）

本文给出**可复现**的触发方式：

- **静态计划**：必现（跳过自动规划）。
- **自然语言**：① **显式委派关键词**（见下）时，**启发式与 PydanticAI 规划器**均可能在调用 LLM 之前就产出单步 `delegate_task`；② 否则在 **`pydantic_ai` / `auto`（且网关可用）** 下依赖模型按系统提示选用 `delegate_task`。

**注意**：若用户任务先命中 **回忆身份 / 搜索记忆** 类 `memory_search` 短路，则**不会**再走到委派短路（优先级：`memory_search` → 委派关键词 → 其余启发式或 LLM）。

**显式委派关键词**（匹配用户任务原文 `strip` 后，不区分大小写，正则见 `src/uni_agent/agent/planner.py` 中 `DELEGATE_USER_INTENT_PATTERN`）：子串 **`delegate_task`**、**`子代理`**、**`sub-agent`**、或整词 **`subagent`**。

---

## 目标

- 父 run：只负责「发起委派 + 消费子 run 返回文本」。
- 子 run：独立完成**单一、可验收**的子目标（例如只读分析某目录），返回 `CHILD_RUN_ID` / `STATUS` / `CONCLUSION` 等约定格式。

---

## 方式一：静态计划（推荐做演示 / 回归）

将下列内容保存为仓库内任意路径，例如 `docs/cases/plans/delegate_smoke.yaml`：

```yaml
steps:
  - id: step-1
    description: 委派子 agent 只读梳理 agent 包内模块
    tool: delegate_task
    arguments:
      task: >-
        在 src/uni_agent/agent 下用 search_workspace 查找 .py 文件，
        再 file_read 打开 orchestrator.py 与 planner.py 的文件头（前 40 行），
        用不超过 8 条要点说明这两个文件各自职责；不要改任何文件。
      context: >-
        工作区为仓库根；路径均相对根目录。输出只保留要点，不要贴全文。
```

执行（需已 `pip install -e '.[dev]'`，且 `UNI_AGENT_WORKSPACE` 指向仓库根）：

```bash
uni-agent run "smoke delegate" --plan docs/cases/plans/delegate_smoke.yaml --no-stream
```

**预期**

- `.uni-agent/runs/` 下出现 **两条** JSON（父、子）；子记录中 `parent_run_id` 等于父 `run_id`。
- 父 `plan[0].output` 中含 `CHILD_RUN_ID=`、`PARENT_RUN_ID=`、`STATUS=`。
- 子 `plan` 中**不出现** `delegate_task`（子侧未注册该工具）。

---

## 方式二：自然语言（关键词短路或 LLM 选工具）

### 2a. 不写 `--plan`、后端为 `heuristic`

只要用户任务原文包含上述**显式委派关键词**之一，且父侧工具集中已注册 `delegate_task`，规划器会返回**单步** `delegate_task`，`arguments.task` 为**整段**用户输入（便于一句话里同时写清子任务边界）。

### 2b. `pydantic_ai` 或 `auto`（且网关可用）

- 任务中含 **2a** 的关键词时，行为与启发式一致（在调用规划 LLM **之前**短路），不消耗规划 LLM。
- **无**关键词时：用**显式拆分子任务**的表述，便于模型选用 `delegate_task`（与 `DEFAULT_PLANNER_SYSTEM_PROMPT` 中「独立子目标 / 用户显式要子代理」一致）。

**示例用户任务（中文）**

> 请使用 **delegate_task** 派一个子任务：只在仓库里做只读调查——总结 `src/uni_agent/agent` 里与「编排、规划」相关的两个核心文件各干什么；子任务完成后，你根据子任务返回的摘要回答我：当前项目是否包含 `Orchestrator` 类？

**示例用户任务（英文）**

> Spawn a **delegate_task** child run: read-only survey of `src/uni_agent/agent` — summarize responsibilities of `orchestrator.py` vs `planner.py` in under 10 bullets. Then tell me if an `Orchestrator` class exists, based only on the child result.

若模型未选 `delegate_task`，可缩短父任务、在句中加上 **`delegate_task` / 子代理** 等触发词、或把「必须用 delegate_task」写进 `UNI_AGENT_PLANNER_INSTRUCTIONS` 做短期实验（生产环境慎用，以免滥用委派）。

---

## 方式三：交互客户端里用自然语言（介绍本项目功能）

启动：

```bash
uni-agent client
```

在 `uni-agent>` 下**整段粘贴**下面这一段（一次一行输入亦可，关键是任务里**显式写出委派关键词**与**子任务边界**）：

```text
请使用内置工具 delegate_task 做一次子代理运行。子任务的 task 字段请写清楚：
只读阅读仓库根目录的 README.md，必要时再读 docs/设计文档.md 的前 80 行，
用 5～8 条要点概括：项目定位、CLI 子命令（uni-agent …）、核心运行时模块、内置工具大类、Skills 与记忆相关能力。
不要改任何文件。子任务返回后，请你根据 delegate_task 输出里的摘要，用一段话向「刚 clone 仓库的同学」口头介绍本项目是干什么的，不要重复粘贴子任务全文。
```

**在终端里怎么确认触发了 sub-agent**

- stderr 里会出现 **`───────── sub-agent ─────────`**、`parent_run_id → child_run_id`，以及 **`■ sub-agent finished`**，再接 **`(parent run continues)`**。
- 最终 stdout JSON 里：父 `plan` 中应有一步 **`delegate_task`**；`available_tools` 仍含 `delegate_task` 属正常（父侧）。

**若模型没选 `delegate_task`**（仅发生在未命中关键词且走 LLM 规划时）：把首句改得更硬并含 **`delegate_task` / 子代理**；或改用 `--plan` 静态 YAML（方式一）。

---

## 可选：只读子代理

在 `.env` 中设置：

```bash
UNI_AGENT_DELEGATE_TOOL_PROFILE=readonly
```

则子 run 仅有 `file_read` / `search_workspace` / `memory_search` / `command_lookup`，适合「纯侦察」类子任务；需要 `git` / `shell_exec` 时不要开 readonly。

---

## 与启发式规划器（当前实现）

`heuristic` 后端**会**在用户任务含 **显式委派关键词** 时插入单步 `delegate_task`（在 `memory_search` 短路之后）。**不**含关键词时，启发式仍不会「猜」出委派，需 **方式一**、换用 **`pydantic_ai` / `auto`**、或在任务里加入 **`delegate_task` / 子代理** 等字样。

更多架构说明见 [开发文档 §4.4 Tool System / Sub-agent](../开发文档.md) 与 [Agent 运行流程 §2.6](../Agent运行流程与领域模型.md)。
