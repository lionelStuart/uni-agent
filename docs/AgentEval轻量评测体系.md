# Agent Eval 轻量评测体系

本文定义 `uni-agent` 的轻量自评测体系，用于对当前 agent 质量做可复现、置信度较高的综合打分。

设计原则：

- 默认启用 LLM judge，对最终任务完成质量进行模型评审。
- 规则评分仍保留，用于高置信的轨迹、效率、稳定性和安全检查。
- 评估 agent 的最终结果，也评估执行轨迹。
- 使用当前 `TaskResult`、`PlanStep`、`verifications`、`run_stats`，不引入外部平台依赖。
- 分数可进入 CI 或本地回归，先做小而可信的用例集。

---

## 1. 评测对象

每个 eval case 对应一次 `Orchestrator.run()`：

- 输入：用户任务、可选静态 plan、可选 session context
- 输出：`TaskResult`
- 评分输入：`status`、`output`、`plan`、`tool_result`、`verifications`、`working_memory`、`run_stats`

---

## 2. Case Schema

评测用例使用 YAML：

```yaml
id: read-readme
description: Read README through file_read.
task: read README.md
plan: null
assertions:
  status: completed
  output_contains:
    - "# uni-agent"
  required_tools:
    - file_read
  forbidden_tools:
    - shell_exec
  max_steps: 3
  max_failed_steps: 0
  max_loop_guard_triggers: 0
weights:
  goal: 0.35
  trajectory: 0.25
  efficiency: 0.15
  stability: 0.15
  safety: 0.10
```

字段说明：

- `id`：稳定用例 ID。
- `task`：传给 agent 的任务。
- `plan`：可选静态 plan 文件路径，相对 case 文件所在目录解析。
- `assertions.status`：期望任务最终状态。
- `assertions.output_contains`：最终答案或原始工具输出中必须包含的片段。
- `assertions.output_not_contains`：最终答案和原始工具输出中都不能包含的片段。
- `assertions.required_tools`：轨迹中必须出现的工具。
- `assertions.forbidden_tools`：轨迹中不能出现的工具。
- `assertions.expected_tool_sequence`：严格工具序列，适合高置信度固定流程。
- `assertions.max_steps`：最大步骤数。
- `assertions.max_failed_steps`：最大失败步骤数。
- `assertions.max_loop_guard_triggers`：最大 loop guard 命中次数。
- `weights`：可选评分权重；未提供时使用默认权重。

---

## 3. 评分维度

总分为 0 到 100。

默认权重：

| 维度 | 权重 | 含义 |
|------|------|------|
| `goal` | 0.35 | 最终状态与输出断言是否满足 |
| `trajectory` | 0.25 | 工具选择、工具顺序、禁用工具约束 |
| `efficiency` | 0.15 | 步数是否受控 |
| `stability` | 0.15 | 失败步骤、verifier 失败、loop guard 命中 |
| `safety` | 0.10 | 是否调用 forbidden / high-risk 工具 |
| `llm_judge` | 0.20 | 使用环境默认大模型评估最终任务完成质量 |

### 3.1 Goal Score

高置信规则：

- 最终 `status` 匹配得分。
- `output_contains` 全部命中得分；匹配范围为 `TaskResult.answer + TaskResult.output`，避免 LLM 最终答案改写精确标记后误判。
- `output_not_contains` 全部未命中得分；同样检查最终答案和原始输出的联合文本。

### 3.2 Trajectory Score

高置信规则：

- `required_tools` 全部出现。
- `forbidden_tools` 全部未出现。
- 如果定义 `expected_tool_sequence`，实际工具序列必须严格匹配。

### 3.3 Efficiency Score

高置信规则：

- 未设置 `max_steps` 时默认满分。
- 设置后，`steps_total <= max_steps` 满分，否则按超出比例扣分。

### 3.4 Stability Score

高置信规则：

- 失败步骤数不能超过 `max_failed_steps`。
- loop guard 命中不能超过 `max_loop_guard_triggers`。
- verifier 失败越多分越低。

### 3.5 Safety Score

高置信规则：

- 调用 forbidden tool 直接扣分。
- high-risk 工具调用可作为 penalty，但不默认失败，因为有些任务确实需要写文件或 shell。

---

## 4. CLI

```bash
uni-agent eval docs/evals/cases --format summary
uni-agent eval docs/evals/cases --format json
uni-agent eval docs/evals/cases --no-llm-judge
uni-agent eval docs/evals/cases --llm-review
```

输出包含：

- case 数量
- 平均分
- pass rate
- 每个 case 的维度分
- 失败断言
- 对应 `run_id`

默认情况下，`uni-agent eval` 会启用 LLM judge，使用当前 `UNI_AGENT_MODEL_NAME` / `UNI_AGENT_OPENAI_*` 等环境配置中的默认大模型评审最终质量。

同时，eval 默认会关闭被测 agent 运行过程中的 LLM goal-check 与 LLM conclusion hook，避免“被测执行过程的复核”和“评测器复核”混在一起。最终答案 `answer` 默认仍会用环境大模型合成；若合成失败会回退到规则答案。需要同时观察被测 agent 自身的 LLM 复核行为时，再显式传 `--llm-review`。

离线或 CI 环境可使用 `--no-llm-judge` 只跑确定性评分。

---

## 5. 当前用例集

当前种子用例位于 `docs/evals/cases/`，覆盖：

- `read-readme`：基础文件读取，strict trajectory。
- `search-workspace`：workspace 搜索，required tool / forbidden tool。
- `missing-file-recovery`：缺失文件失败收束。
- `write-artifact`：写入 artifact 并验证文件状态。
- `search-then-read-code`：搜索后读取代码，多步工具链路。
- `memory-recall-route`：回忆类任务路由到 `memory_search`。
- `delegate-explicit`：显式 `delegate_task` 与结构化子 run 元数据。
- `python-analysis`：`run_python` 执行确定性数据分析。
- `code-inspection`：用 `file_read(start_line/max_lines)` 读取 registry 目标代码片段，并由 LLM judge 判断解释质量。
- `no-extra-tools-read`：简单读取任务不应调用额外工具。

这些 case 覆盖了 smoke、trajectory、artifact、error handling、memory、delegate、data analysis、code inspection 和 tool efficiency。后续可继续补安全拒绝、HTTP fetch、本地服务交互和 pass^k 稳定性。

## 6. 当前边界

本体系暂不做：

- 语义相似度评分
- 大规模外部 benchmark
- 多模型排行榜

原因：

- 当前目标是高置信、可复现、适合 CI 的质量评估。
- 主观判断后续可作为可选维度加入，不应成为基础分。
