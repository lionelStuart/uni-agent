# 多 agent 清单（YAML / JSON）

在单进程内注册多个 `AgentConfig` 时，可用清单文件 + **`load_agent_configs_from_file`** 或一键 **`load_agent_registry_from_file`**，避免手写大量 `Settings`。

## 清单格式

- 根对象须含 **`agents`**：非空数组。
- 每一项至少包含： **`id`**、**`workspace`**、**`skills_dir`**（含义与 [`AgentConfig`](../src/uni_agent/sdk/config.py) 一致）。

**相对路径**（`workspace`）相对于**清单文件所在目录**；**`skills_dir`** 若为相对路径，则相对于该 agent 的 **`workspace`** 解析为绝对路径后再交给 `AgentConfig`。

可选字段与 `AgentConfig` 对齐，例如 `name`、`description`、`storage_namespace`、`planner_backend`、`model_name`、`global_system_prompt` 等。字段映射见 `src/uni_agent/sdk/loader.py` 中 ``_one_config``。

## 示例文件

- 清单：[examples/agents.example.yaml](../examples/agents.example.yaml)
- 脚本：[examples/sdk_multi_agent.py](../examples/sdk_multi_agent.py)（对 `agent-readonly` 执行一次 `read README.md`）

## API

| 函数 | 说明 |
|------|------|
| `load_agent_configs_from_file(path) -> dict[str, AgentConfig]` | 只解析配置，不创建 `Orchestrator`；重复 `id` 会 `ValueError` |
| `load_agent_registry_from_file(path, on_event=...) -> AgentRegistry` | 为每个 `id` 注册一个 `create_client(config, on_event=...)` |

扩展名支持：`.json`、`.yaml`、`.yml`。

## `id` 规则

`id` 须匹配 `^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$`（与 manifest 中常见 slug 风格一致）。

## 与并发

多 agent 共进程、清单加载后的调度与限流，见 [sdk-concurrency.md](./sdk-concurrency.md)（不默认提供全局限流；由业务层使用 `asyncio` / 线程池等）。

## 与装配

每个 manifest 条目对应一次 `build_orchestrator`；与 CLI 的装配关系见 [sdk-runtime.md](./sdk-runtime.md)。
