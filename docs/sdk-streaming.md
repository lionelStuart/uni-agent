# SDK / CLI 流式事件（NDJSON）

`uni-agent run --stream`、以及 `create_client(..., on_event=cb)` / `build_orchestrator(stream_event=...)` 使用的**是同一套**事件：每次回调收到一个 **`dict`**，语义上可**一行一个 JSON**（NDJSON）写出，与 CLI 在 stderr 上的行为一致。

**说明**：这是**编排层**事件（规划轮次、步骤完成、结论等），不是规划/结论 LLM 的逐 **token** 流。

## 传输形式

| 场景 | 建议 |
|------|------|
| 本机进程 | `print(json.dumps(ev, ensure_ascii=False), file=sys.stderr, flush=True)` |
| HTTP 长连接 | 每行一条 NDJSON（`Content-Type: application/x-ndjson` 或 `text/plain`），或 SSE：每事件 `data: {json}\n\n` |
| WebSocket | 每个事件一个 text 帧，内容为**单行 JSON 字符串**；与 NDJSON 等价 |

客户端解析：按**行** `json.loads`，或 WebSocket 一帧一对象。

## 事件类型（`type` 字段）

以下字段为常见键；未列出的键可能随版本增加，应忽略未知键（forward compatible）。

| `type` | 说明 | 主要字段 |
|--------|------|----------|
| `run_begin` | 一次 `run` 开始 | `run_id`, `task`, `selected_skills`（名称列表） |
| `round_plan` | 某轮规划结果（将执行的步骤摘要） | `round`（int）；`steps`：`[{id, tool, description}, ...]`；仅 `--plan` 时可能含 `source`: `"file_override"` |
| `plan_empty` | 规划器返回空计划 | `failed_rounds_so_far`, `max_failed_rounds` |
| `step_finished` | 单步工具执行结束 | `round`；`step`：完整 `PlanStep` 字典（含 `output`、`status`、`error_detail` 等） |
| `round_completed` | 本批步骤**全部**成功 | `round` |
| `round_failed` | 本批有失败，将进入重规划 | `round`, `failed_rounds_so_far`, `max_failed_rounds` |
| `goal_check` | 可选；每批全成功后若开启目标检查 | `round`；`satisfied`: `true` / `false` / `null`（检查异常时）；`reason`；失败时 `error` |
| `conclusion_begin` | 开始生成结论文本 | `run_id` |
| `conclusion_done` | 结论已生成 | `run_id`, `conclusion`（字符串） |
| `run_end` | 本次 `run` 结束 | `run_id`, `status`（`completed` / `failed`）, `orchestrator_failed_rounds` |

## 子代理（`delegate_task`）

子 run 产生的事件**仍走父级** `on_event`，但对象上带 **`delegation`**：

```json
{
  "type": "step_finished",
  "round": 1,
  "delegation": { "phase": "child", "parent_run_id": "…" },
  "step": { ... }
}
```

- `phase == "child"` 表示该事件属于子 `Orchestrator`；展示时可缩进或单独分区（见 `client_shell._human_stream_event`）。

## 代码位置

- 事件发出：`src/uni_agent/agent/orchestrator.py`（`self._stream({...})`）
- 子流包装：`src/uni_agent/tools/delegation_stream.py`（`wrap_child_stream`）
- SDK：`on_event` 与 `stream_event` 为同一回调类型：`StreamEventCallback`
