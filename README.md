# uni-agent

可加载可插拔 **Skills** 的通用 **Agent Client**（Python CLI）。

核心组成：

- **Agent Runtime**：`Orchestrator` + `Planner`（启发式 / PydanticAI）+ `Executor`
- **通用 Sandbox**：`LocalSandbox`（命令白名单、超时、可选交互批准）
- **Skills**：本地 `skills/<name>/` 自动加载（**每层子目录一项 skill**）：优先 **`SKILL.md`**（YAML frontmatter + 正文，对齐 Codex / Claude Code / Cursor）；否则 **`skill.yaml`** + `entry` 指向的 Markdown。可选 **`references/`、`reference.md`、`examples.md`** 与 **`scripts/`**，合并为 `instruction_text`；小参考文件可内联进提示。`UNI_AGENT_SKILLS_DIR` 对应 `skills_dir`，加载器使用 **`UNI_AGENT_WORKSPACE`** 计算 `file_read` 用的相对路径

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
- **LLM 系统提示词**：内置默认文案（`agent/system_prompts.py`）；可通过 `UNI_AGENT_GLOBAL_SYSTEM_PROMPT`、`UNI_AGENT_PLANNER_INSTRUCTIONS`、`UNI_AGENT_CONCLUSION_SYSTEM_PROMPT` 覆盖或加前缀（见 `.env.example`）
- **上下文与输出截断**：交互 session 对历史任务做规则化摘要（`compress_task_result_for_session`）；重规划时的 `prior_context` 与工具返回（如 `file_read` / sandbox）均有字符上限截断
- **本地记忆夹**：默认目录 **`$UNI_AGENT_WORKSPACE/.uni-agent/memory`**（`UNI_AGENT_MEMORY_DIR` 相对路径亦以 workspace 为基准，避免 shell cwd 与项目根不一致时读写/检索分叉）；**`memory_index.json`** 存 **L0** 与 **`l1/*.json`** 路径；**`memory_search`**（工具与 REPL `memory search`）在配置 LLM 时：**由模型根据问题生成关键词 → 在 L0 上做子串匹配 → 将命中条目的 L1 交给模型整理回答**（关键词 LLM 失败时仍用用户原问句参与匹配）；关闭 `UNI_AGENT_MEMORY_SEARCH_USE_LLM` 时退化为 L0 字面子串检索
- **规划侧「回忆」路由**：任务含 **我是谁 / 我叫什么 / 还记得我吗 / who am i** 等短语时，**启发式与 PydanticAI 规划器**均优先单步 **`memory_search`**（再走 L0/L1），避免被默认「闲聊 → echo」规则带偏
- **任务落盘**：`.uni-agent/runs/`（已 `.gitignore`，不提交）

## 开发约束

实现与文档不一致时，**先改文档再改代码**。协作流程见 [进度文档](docs/进度文档.md) 中的记录规范。

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

# 若出现 certificate verify failed（访问 pypi.org 失败），可临时放宽校验（仅当你信任当前网络环境）：
# pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -e '.[dev]'

agent skills
agent run "read README.md"
# 仅看最终 JSON、不要 stderr 流式事件：
# agent run "read README.md" --no-stream

pytest
```

配置示例见仓库根目录 `.env.example`。

若环境变量里使用 **SOCKS** 代理（如 `ALL_PROXY=socks5://...`），依赖里已包含 `socksio`（供 httpx 使用）；更新代码后请重新执行 `pip install -e '.[dev]'`。

**根因修复（优先于 `--trusted-host`）**：公司设备请把企业根证书导入系统钥匙串 / 使用 IT 提供的 `PIP_CERT` 或 `SSL_CERT_FILE`；macOS 官方 Python 可运行 `/Applications/Python 3.x/Install Certificates.command`（若存在）。

## 测试

```bash
python -m pytest -q
```

（当前仓库约 **76** 个用例，以 `pytest` 输出为准。）
