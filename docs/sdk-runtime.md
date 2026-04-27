# `uni_agent.sdk` 与运行时关系

本文件说明**进程内 SDK 包**（`import uni_agent.sdk`）与**装配入口**、**CLI** 及 **`Orchestrator`** 之间的边界。实现以仓库源码为准，路径均相对于仓库根。

## 唯一装配面：`build_orchestrator`

- **推荐且唯一**用于组装可执行 `Orchestrator` 的公共入口是 `uni_agent.bootstrap.build_orchestrator`。
- `uni_agent.sdk.create_client` / `AgentClient` **不复制**第二套「运行时」；内部调用：

  `build_orchestrator(settings=config.to_settings(), stream_event=on_event)`，

  与 CLI、子代理子 run 在**同一条装配线**上（同一函数、显式 `Settings` 与 `stream_event` 语义）。
- SDK **不**再提供并行的、行为不一致的 `bootstrap_sdk` 等入口；多 agent 仅通过**多个** `AgentConfig` / `create_client` / 清单，各自对应一次 `build_orchestrator`（见 [sdk-agents.md](./sdk-agents.md)）。

## `AgentClient` 的职责

- **默认路径**：`create_client` → 内部 `build_orchestrator` → 对外只暴露高层的 `run` / `replay`（与 `on_event` 流式，见 [sdk-streaming.md](./sdk-streaming.md)）。
- **配置**：来自 `AgentConfig.to_settings()`，避免与进程级 `get_settings()` 环境变量隐式混用；同一进程内多 agent 时每个 client 有独立 `Settings` 派生值（含 `task_log_dir` / `memory_dir` 等）。

## 逃生舱：`AgentClient.orchestrator`

- 属性 **`.orchestrator`** 返回本次 client 在构造时绑定的 `Orchestrator` 实例（与 `run` / `replay` 为**同一**对象）。
- **用途**（高级/集成）：直接访问 `skill_loader`、`tool_registry`、`planner`、`task_store` 等，用于可观测、测试、或本库尚未暴露能力的内部试验。
- **注意**：
  - 若需**不同**的 `stream_event`（每调用独立回调），应 **新建** `create_client`（新 `build_orchestrator`），而不是在运行时给已有 `Orchestrator` 换回调；当前装配未设计「每 run 可替换的 stream 回调」热更新。
  - 对 `.orchestrator` 的并发使用仍遵循 [sdk-concurrency.md](./sdk-concurrency.md)。

## 测试注入

- `AgentClient(config, orchestrator=mock_orchestrator, ...)` 可传入**已构造**的 `Orchestrator`（或 `MagicMock`），**跳过**内部 `build_orchestrator`，用于单元测试或桩对象。`on_event` 在传入自定义 `orchestrator` 时**不会**被再次用于构建（以注入实例为准）。生产路径一般省略该参数，由 `build_orchestrator` 完成装配。

## Langfuse 可观测透传

- `AgentConfig` 的以下字段会透传到 `Settings` 并在 `build_orchestrator` 中参与 `stream_event` 组合：
  `observability_langfuse_enabled`, `observability_langfuse_host`,
  `observability_langfuse_public_key`, `observability_langfuse_secret_key`,
  `observability_langfuse_debug`, `observability_langfuse_trace_name`,
  `observability_langfuse_trace_input_max_chars`。
- 若 `observability_langfuse_enabled=true` 且 `langfuse` 依赖与凭据可用，`build_orchestrator` 会自动把 Langfuse sink 与用户 `stream_event` 合并；子代理流事件也会通过 delegate 包装元数据后走同样通道。

## 与 CLI 的关系

- `uni-agent run` / 交互式 client 经 CLI 组装的运行时也使用 `build_orchestrator`；与 SDK 的差异主要在**参数来源**（CLI 从标志/环境变量组 `Settings`，SDK 从 `AgentConfig`）。**事件形态、工具集、沙箱、规划后端**在相同 `Settings` 语义下应一致；SDK 的显式 `Settings` 正是为了对齐而避免隐式差分。

## 包内结构（速览）

| 模块 | 作用 |
|------|------|
| `uni_agent.sdk.config` | `AgentConfig`、`to_settings()` |
| `uni_agent.sdk.client` | `create_client`、`AgentClient`（`.orchestrator`） |
| `uni_agent.sdk.registry` | `AgentRegistry`（按 id 复用 `AgentClient`） |
| `uni_agent.sdk.loader` | 清单 → 多 `AgentConfig` / `AgentRegistry` |

## 契约与回归测试（Round 6）

- **快照**：`tests/fixtures/sdk/to_settings_non_path.json` 与 `tests/unit/test_sdk_to_settings_snapshot.py` 校验 `AgentConfig.to_settings()` 对非路径字段的稳定映射（变更 `to_settings` 时需同步 fixture）。
- **Registry**：`tests/unit/test_registry_contract.py`（同 id 单实例、`register`/`get`、缺失 `get` 抛错等）。
- **集成**：`tests/integration/test_sdk_contract.py` — 不经 mock 的 `create_client` + 启发式 `run` 读 workspace 文件。

## 另见

- 流式：[sdk-streaming.md](./sdk-streaming.md)  
- 多 agent 清单：[sdk-agents.md](./sdk-agents.md)  
- 并发：[sdk-concurrency.md](./sdk-concurrency.md)  
- 可运行：[`../examples/sdk_minimal.py`](../examples/sdk_minimal.py)、[`../examples/sdk_orchestrator_escape.py`](../examples/sdk_orchestrator_escape.py)
