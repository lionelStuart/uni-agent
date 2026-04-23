# SDK 并发与资源

在 Web 服务、批处理或多 agent 共进程场景中，常需要在**限制并发**的前提下调度多次 `run`。本文说明 **`uni_agent.sdk` 有意不内置**哪些机制，并给出在**业务层**可组合的常见做法。

## 本 SDK 不提供的机制

- **不**在库内提供进程级/全局的并发「配额」实现（如固定的 `threading.Semaphore`、全局限流器或内置任务队列）。  
  **原因**：进程内的 LLM/工具负载与宿主的并发模型（asyncio、多线程、Gunicorn 多进程等）高度相关；应在使用方用熟悉的原语，按**业务 SLA** 与**上游限流**来约束。
- 若你需要「最多 N 个 agent run 同时执行」，在应用侧使用 **`threading.Semaphore(N)`**、**`asyncio.Semaphore(N)`**、**有界 `Queue` + worker 池** 等即可；这些与 `AgentClient` 正交，无需改 SDK 源码。

## 同一 `AgentClient` / `Orchestrator` 上并发 `run()`

- `AgentClient.run` / `Orchestrator.run` 是**同步、可能长时间占用**的调用；**未对同一 `Orchestrator` 实例上的并发 `run` 做线程安全保证**（规划器、执行器、内部状态在设计上按「单次 run 占用」使用）。  
- **建议**：对**同一** `AgentClient` 要么**串行**调用 `run`（用锁，或把并发压成队列顺序执行），要么为每个并发工作单元**新建**一个 `create_client`（或独立 `build_orchestrator`），使每次 run 有**独立**的 `Orchestrator`。  
- `run_context` 使用 `contextvars`：在**不同 OS 线程**中并行 run 时，当前 run 的 `run_id` 等**按线程/协程**隔离，但**不能**因此假定共享的 `Planner` / `Executor` 等实现可在多线程下安全交叠，仍请避免对**同一** orchestrator 并发 `run`。
- 从清单加载的 [`load_agent_registry_from_file`](./sdk-agents.md) 为每个 `id` 注册**一个** client；若同一 id 的 `run` 需要**并行**执行，可在外部再建多个 `AgentConfig` / `create_client` 实例，或**串行**使用该 id 的 client。

## 模式速查

| 目标 | 做法 |
|------|------|
| asyncio 中调用同步 `run` | `await asyncio.to_thread(client.run, task, ...)`（或专用线程池执行器） |
| 限制同时进行的 run 数 | 业务层 `asyncio.Semaphore(N)` / `ThreadPoolExecutor(max_workers=N)`，在提交前后包裹 |
| 削峰、顺序执行 | `queue.Queue` / `asyncio.Queue` + 固定数量 worker 线程或任务 |
| 多进程隔离（重 CPU/工具侧） | 多进程时每个进程内各自 `create_client`；注意**不要**跨进程共享 client |
| 共享 `on_event` 回调 | 多 run 复用同一回调时，对共享输出（如写 WebSocket、同一 logger）**自行**加锁或按 `run_id` 分路 |

## LLM 与 I/O 资源

- 并发升高时，瓶颈通常在 **LLM/HTTP 配额**、**沙箱子进程/临时文件**、**磁盘**（`.uni-agent/runs` 等）。在应用层做 **N** 上线比扩大默认线程数更安全；必要时对 **OpenAI 兼容** 的 base URL 侧配置限流/重试。  
- `storage_namespace` 与多 agent 隔离见 [开发文档 §4.9 与 AgentConfig](./开发文档.md#49-programmatic-sdkuni_agentsdk)；**同一** workspace 下多 client 高并发时仍要注意 JSON 落盘等 I/O 争用，通常通过降低并发度或分目录解决。

## 另见

- 流式事件与多路复用：[`docs/sdk-streaming.md`](./sdk-streaming.md)  
- 多 agent 清单：[`docs/sdk-agents.md`](./sdk-agents.md)  
- SDK 与 `build_orchestrator` 边界、`.orchestrator`：[`docs/sdk-runtime.md`](./sdk-runtime.md)  
- 最小示例与清单示例：[`../examples/sdk_minimal.py`](../examples/sdk_minimal.py)、[`../examples/sdk_concurrency.py`](../examples/sdk_concurrency.py)
