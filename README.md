# uni-agent

可加载可插拔 **Skills** 的通用 **Agent Client**，同时提供：

- 命令行入口：`uni-agent run|client|replay|skills`
- 进程内 SDK：`uni_agent.sdk`
- 本地沙箱执行：`LocalSandbox`
- 基于本地目录的 skill 自动发现与注入

## 核心组成

- **Agent Runtime**：`Orchestrator` + `Planner`（启发式 / PydanticAI）+ `Executor`
- **Sandbox**：`LocalSandbox`，支持命令白名单、超时、可选交互批准
- **Skills**：从本地 `skills/<name>/` 自动加载；优先读取 `SKILL.md`，否则回退到 `skill.yaml` + `entry`
- **Observability**：任务落盘、历史回放、交互 session、本地记忆目录

## 当前能力

- `uni-agent run "<任务>"`：自动规划并执行工具，可通过 `--plan` 使用静态计划文件
- `uni-agent replay <run_id>`：从 `.uni-agent/runs/` 回放已落盘的 `TaskResult`
- 多轮重规划：执行失败后带执行日志继续规划；可选 goal check 判定任务是否真正完成
- 交互客户端：`uni-agent client` 提供 REPL、session 落盘、会话重载和本地记忆提取
- 流式事件：CLI `--stream` 和 SDK `on_event=` 共用同一套 NDJSON 事件模型
- 本地记忆：`memory_search`、交互式 `memory search`、空闲自动抽取到 `.uni-agent/memory`
- DuckDuckGo 网页搜索：`web_search` 内置工具可返回标题、URL 和摘要片段
- 子代理委派：`delegate_task` 启动单层子 `Orchestrator.run`，支持只读工具集
- 历史结论：结果中包含 `conclusion` 字段，支持规则摘要和可选 LLM 结论

## 内置工具

- `shell_exec`
- `file_read`
- `file_write`
- `http_fetch`
- `web_search`
- `search_workspace`
- `command_lookup`
- `run_python`
- `memory_search`
- `delegate_task`

其中：

- `search_workspace` 基于 `ripgrep` 固定字符串搜索；无匹配不视为失败
- `web_search` 当前以 DuckDuckGo HTML 搜索页为后端，不需要 API key，但属于实验性实现，可能受反爬或页面结构变更影响
- `run_python` 在 workspace 沙箱内运行短脚本，临时文件落在 `.uni-agent/code_run/`
- `delegate_task` 的子 run 可通过 `UNI_AGENT_DELEGATE_TOOL_PROFILE=readonly` 限制为只读工具集

## Skills 约定

- skill 根目录为 `skills/`
- 每层子目录视为一个 skill
- 优先加载 `SKILL.md`，支持 YAML frontmatter + Markdown 正文
- 若无 `SKILL.md`，则读取 `skill.yaml` 与其 `entry` 指向的 Markdown
- 可选合并 `references/`、`reference.md`、`examples.md`、`scripts/` 内容为 `instruction_text`
- `skills_dir` 对应环境变量 `UNI_AGENT_SKILLS_DIR`
- 加载器用 `UNI_AGENT_WORKSPACE` 作为 `file_read` 相对路径基准

## SDK

进程内 SDK 入口：

```python
from uni_agent.sdk import (
    AgentConfig,
    AgentClient,
    AgentRegistry,
    create_client,
    load_agent_configs_from_file,
    load_agent_registry_from_file,
)
```

### SDK 提供的能力

- `AgentConfig`：显式描述 `workspace`、`skills_dir`、模型、提示词和多 agent 隔离配置
- `create_client(config, on_event=...)`：构建一个 `AgentClient`
- `AgentClient.run(task, plan_override=None, session_context=None)`：执行任务
- `AgentClient.replay(run_id)`：回放某次 run
- `AgentClient.orchestrator`：暴露同一实例的 `Orchestrator` 作为逃生舱
- `AgentRegistry`：按 `agent_id` 缓存和复用 `AgentClient`
- `load_agent_configs_from_file(path)`：只解析 manifest，不创建运行时
- `load_agent_registry_from_file(path, on_event=...)`：从 manifest 一次性注册多个 agent

### `AgentConfig` 常用字段

- `name`
- `description`
- `workspace`
- `skills_dir`
- `storage_namespace`
- `planner_backend`
- `model_name`
- `context_window_tokens`
- `openai_base_url`
- `openai_api_key`
- `ca_bundle`
- `skip_tls_verify`
- `plan_goal_check_enabled`
- `global_system_prompt`
- `planner_instructions`
- `conclusion_system_prompt`
- `run_conclusion_llm`

说明：

- `to_settings()` 会生成显式 `Settings`，避免多 agent 共进程时混用同一套环境变量
- `storage_namespace` 会把任务日志与 memory 目录隔离到 `<workspace>/.uni-agent/.../<namespace>/`
- 当 `global_system_prompt` 未设置时，会基于 `name` 与 `description` 生成默认人设前缀
- `ca_bundle` 用于给 `http_fetch` / `web_search` 提供显式 CA bundle；相对路径以 `workspace` 为基准
- `context_window_tokens` 默认是 `256000`；用于推导 `session_context`、`prior_context`、goal-check 和 conclusion 的 token 压缩预算
- `skip_tls_verify` 默认开启，`http_fetch` / `web_search` 会跳过 TLS 证书校验；如需恢复严格校验，可显式设为 `false` 或改用 `ca_bundle`
- `plan_goal_check_enabled` 默认开启；当一轮工具都执行成功但答案仍不完整时，会触发一次 LLM 复核并推动后续重规划

### `AgentRegistry` 语义

- 同一个 `agent_id` 对应同一个缓存的 `AgentClient`
- `get_or_create()` 在已有同名 client 时不会替换旧实例
- 若需要不同 `on_event` 或不同装配结果，应新建 `agent_id` 或直接重新 `create_client`

### Manifest 加载

manifest 支持 `.json`、`.yaml`、`.yml`，根对象必须包含非空 `agents` 数组。

每个条目至少需要：

- `id`
- `workspace`
- `skills_dir`

路径规则：

- 相对 `workspace` 以 manifest 文件所在目录为基准
- 相对 `skills_dir` 以该 agent 的 `workspace` 为基准

`id` 必须匹配：

```text
^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$
```

### SDK 与运行时的关系

- SDK 与 CLI 共用同一条运行时装配链：`build_orchestrator(settings=..., stream_event=...)`
- `AgentClient.orchestrator` 与 `run()` / `replay()` 使用的是同一个 `Orchestrator`
- 不建议在同一个 `Orchestrator` 实例上并发执行多个 `run()`

并发与多路流式的细节见：

- [docs/sdk-concurrency.md](docs/sdk-concurrency.md)
- [docs/sdk-streaming.md](docs/sdk-streaming.md)
- [docs/sdk-runtime.md](docs/sdk-runtime.md)
- [docs/sdk-agents.md](docs/sdk-agents.md)

## 可运行示例

- 最小 SDK 示例：[examples/sdk_minimal.py](examples/sdk_minimal.py)
- 多 agent manifest + registry：[examples/agents.example.yaml](examples/agents.example.yaml)、[examples/sdk_multi_agent.py](examples/sdk_multi_agent.py)
- 并发使用方式：[examples/sdk_concurrency.py](examples/sdk_concurrency.py)
- 运行时逃生舱 `.orchestrator`：[examples/sdk_orchestrator_escape.py](examples/sdk_orchestrator_escape.py)

## CLI

入口命令：

- `uni-agent run`
- `uni-agent client`
- `uni-agent replay`
- `uni-agent skills`

### `run`

```bash
uni-agent run "read README.md"
```

- 默认可通过 `--stream` 在 `stderr` 输出 NDJSON 事件
- `--no-stream` 关闭流式事件
- `stdout` 保持输出最终完整 JSON
- 可通过 `--plan` 使用静态计划文件

### `replay`

```bash
uni-agent replay <run_id> --format steps
```

支持：

- `--format full|steps|jsonl`
- `--verbose`：在 `full` 模式下额外打印步骤摘要

### `client`

`uni-agent client` 进入交互式 REPL，支持：

- `load <id>`
- `sessions`
- `new`
- `status`
- `help` / `?`
- `exit` / `quit` / `:q`
- `memory search <q>`
- `memory status`
- `memory extract`

session 默认落盘到 `UNI_AGENT_SESSION_DIR`，记忆默认落盘到 `UNI_AGENT_MEMORY_DIR`。

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

uni-agent skills
uni-agent run "read README.md"
pytest
```

如果访问 PyPI 时遇到证书问题，可临时使用：

```bash
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -e '.[dev]'
```

这只是临时绕过。更推荐：

- 导入企业根证书
- 配置 `PIP_CERT` 或 `SSL_CERT_FILE`
- 在 macOS 官方 Python 环境执行 `Install Certificates.command`

如果使用 SOCKS 代理，例如 `ALL_PROXY=socks5://...`，依赖中已包含 `socksio` 供 `httpx` 使用。代码更新后请重新执行 `pip install -e '.[dev]'`。

## 关键配置

完整示例见 [.env.example](.env.example)。

常用项：

- `UNI_AGENT_MODEL_NAME`
- `UNI_AGENT_OPENAI_BASE_URL`
- `UNI_AGENT_OPENAI_API_KEY`
- `UNI_AGENT_WORKSPACE`
- `UNI_AGENT_SKILLS_DIR`
- `UNI_AGENT_TASK_LOG_DIR`
- `UNI_AGENT_SESSION_DIR`
- `UNI_AGENT_MEMORY_DIR`
- `UNI_AGENT_CA_BUNDLE`
- `UNI_AGENT_SKIP_TLS_VERIFY`
- `UNI_AGENT_MEMORY_EXTRACT_ENABLED`
- `UNI_AGENT_MEMORY_IDLE_EXTRACT_SECONDS`
- `UNI_AGENT_MEMORY_SEARCH_USE_LLM`
- `UNI_AGENT_ORCHESTRATOR_MAX_FAILED_ROUNDS`
- `UNI_AGENT_PLAN_GOAL_CHECK_ENABLED`
- `UNI_AGENT_PLAN_GOAL_CHECK_MAX_REPLAN_ROUNDS`
- `UNI_AGENT_PLAN_GOAL_CHECK_SYSTEM_PROMPT`
- `UNI_AGENT_DELEGATE_MAX_FAILED_ROUNDS`
- `UNI_AGENT_DELEGATE_TOOL_PROFILE`
- `UNI_AGENT_GLOBAL_SYSTEM_PROMPT`
- `UNI_AGENT_PLANNER_INSTRUCTIONS`
- `UNI_AGENT_CONCLUSION_SYSTEM_PROMPT`

其中：

- `UNI_AGENT_MEMORY_DIR` 默认以 `UNI_AGENT_WORKSPACE` 为基准，而不是 shell cwd
- `UNI_AGENT_CA_BUNDLE` 当前作用于 `http_fetch` 与 `web_search` 的 HTTPS 校验；适用于企业代理、自签根证书等场景
- `UNI_AGENT_SKIP_TLS_VERIFY` 默认是 `true`，会让 `http_fetch` 与 `web_search` 忽略 TLS 证书错误；如需严格校验，请显式设为 `false`，并优先使用 `UNI_AGENT_CA_BUNDLE`
- `UNI_AGENT_DELEGATE_TOOL_PROFILE=readonly` 时，子代理只暴露只读工具
- `UNI_AGENT_PLAN_GOAL_CHECK_ENABLED` 默认是 `true`；每轮全成功执行后会额外做一次 LLM 目标检查，不满足时继续重规划

## 输出目录

默认目录均在 workspace 下的 `.uni-agent/`：

- `runs/`：任务 JSON 落盘
- `sessions/`：交互 client session
- `memory/`：本地记忆与索引
- `code_run/`：`run_python` 临时文件

这些目录已加入 `.gitignore`，不应提交。

## 文档索引

- [docs/设计文档.md](docs/设计文档.md)
- [docs/开发文档.md](docs/开发文档.md)
- [docs/进度文档.md](docs/进度文档.md)
- [docs/Skills目录与SKILL说明.md](docs/Skills目录与SKILL说明.md)
- [docs/Agent运行流程与领域模型.md](docs/Agent运行流程与领域模型.md)
- [docs/sdk-streaming.md](docs/sdk-streaming.md)
- [docs/sdk-agents.md](docs/sdk-agents.md)
- [docs/sdk-concurrency.md](docs/sdk-concurrency.md)
- [docs/sdk-runtime.md](docs/sdk-runtime.md)

## 开发约束

实现与文档不一致时，先改文档再改代码。

功能迭代收尾时，应同步检查：

- `tests/`
- `examples/`
- `README.md`
- 对应专题文档

## 测试

```bash
python -m pytest -q
```

当前仓库测试规模以实际 `pytest` 输出为准。
