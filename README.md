# uni-agent

可加载可插拔 **Skills** 的通用 **Agent Client**（Python CLI）。

核心组成：

- **Agent Runtime**：`Orchestrator` + `Planner`（启发式 / PydanticAI）+ `Executor`
- **通用 Sandbox**：`LocalSandbox`（命令白名单、超时、可选交互批准）
- **Skills**：本地 `skills/` 目录加载与匹配

详细设计见：

- [设计文档](docs/设计文档.md)
- [开发文档](docs/开发文档.md)
- [进度文档](docs/进度文档.md)

## 能力摘要（当前实现）

- `agent run "<任务>"`：自动规划并执行工具；支持 `--plan` 静态计划文件
- **多轮重规划**：失败后带执行日志再规划（`UNI_AGENT_ORCHESTRATOR_MAX_FAILED_ROUNDS`）
- **内置工具**：`shell_exec`、`file_read`、`file_write`、`http_fetch`、`search_workspace`（ripgrep 固定字符串；无匹配不视为失败）
- **OpenAI 兼容 API**：`UNI_AGENT_OPENAI_BASE_URL` / `UNI_AGENT_OPENAI_API_KEY`；适配 Qwen 等网关的 `tool_choice` 行为
- **交互客户端**：`agent client` 进入 REPL（默认按时间新建 session，落盘在 `UNI_AGENT_SESSION_DIR`）；每轮任务结束后追加写入 session；支持 `load <id>`、`sessions`、`new`；进度用人类可读格式打在 stderr
- **流式过程**：默认 `agent run ... --stream` 在 **stderr** 输出 NDJSON 事件；`--no-stream` 关闭；**stdout** 仍为最终完整 JSON
- **运行结论**：结果中含 `conclusion` 字段（规则摘要 + 可选 LLM）
- **任务落盘**：`.uni-agent/runs/`（已 `.gitignore`，不提交）

## 开发约束

实现与文档不一致时，**先改文档再改代码**。协作流程见 [进度文档](docs/进度文档.md) 中的记录规范。

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

agent skills
agent run "read README.md"
# 仅看最终 JSON、不要 stderr 流式事件：
# agent run "read README.md" --no-stream

pytest
```

配置示例见仓库根目录 `.env.example`。

## 测试

```bash
python -m pytest -q
```

（当前仓库约 **51** 个用例，以 `pytest` 输出为准。）
