# 正向案例：交互客户端「项目说明」+ `git status`（沙箱批准）

记录日期：2026-04-17。CLI 入口为 **`uni-agent client`**；规划后端为 **PydanticAI + OpenAI 兼容网关**（本例日志中出现对 `chat/completions` 的调用）。工作区为 **本仓库根目录**。

## 场景

用户在 REPL 中连续发起两轮任务：

1. **「看下这个项目做什么的」** — 期望从仓库内文档理解项目定位，而非空泛回答。
2. **「查看当前项目进度和 git 的状态」** — 期望看到当前分支与工作区变更（用户口述略有笔误，模型仍理解为 git 状态）。

会话结束后执行 `exit`，会话落盘；空闲触发展示 **memory updated**（L0/L1 增量写入）。

## 观察到的正向行为

### 第一轮：README / 工作区理解

- **规划**：单轮两步 — `search_workspace`（`query` 经规范化后等价于列文件）→ `file_read`（`README.md`）。
- **执行**：两步均 `completed`；stderr 人类可读进度与最终 **conclusion** 一致概括了 README 中的项目名、定位、核心组成与能力摘要（含 `uni-agent run/client/replay`、`delegate_task` 等文档要点）。
- **落盘**：`TaskResult` 写入 `.uni-agent/runs/`；`available_tools` 含完整内置集（含 `delegate_task`）。

### 第二轮：Git 状态

- **规划**：单步 `shell_exec`，`argv` 为 `git` + `status`（无 shell 拼接）。
- **沙箱**：`git` 不在默认白名单，触发 **TTY 一次性批准**（`Allow this command once? [y/N]`）；用户输入 `y` 后执行成功。
- **结论**：`conclusion` 正确摘要分支名、modified / untracked 文件规模及「未暂存」状态，与 `git status` 输出一致。

### 记忆与交互

- 第一轮任务后，在提示符空闲时出现 **── memory updated ──**，向 `.uni-agent/memory` 写入与当次 `run_id` 关联的 L1 记录，L0 预览含任务与结论摘要 — 说明 **REPL 空闲落盘链路** 工作正常。

## 可复用的结论

- **「项目是干什么的」** 类问题在结构化规划下可走 **search_workspace（建立文件上下文）+ file_read（README）**，比直接 `echo` 更贴近真实仓库。
- **Git 类命令** 依赖 **`git` 入白名单** 或 **交互批准**；自动化/非 TTY 场景需提前配置 `UNI_AGENT_SANDBOX_ALLOWED_COMMANDS`（或关闭批准并收紧策略）。
- 用户输入存在轻微错别字时，模型仍可生成合理计划（本例「进git」→ `git status`）。

## 与测试/文档的对照

- 行为与 [README 能力摘要](../../README.md) 中「交互客户端」「沙箱批准」「本地记忆」描述一致。
- `run_id`、`HTTP` 日志 URL 与完整文件列表可按需脱敏后再对外分享；本文件保留足够结构供内部回归参照。
