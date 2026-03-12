# uni-agent

一个可加载可插拔 Skills 的通用 Agent Client。

项目核心由三部分组成：

- Agent Runtime
- 通用 Sandbox
- Skills 插件机制

当前仓库处于设计阶段，已完成首版客户端文档：

- [设计文档](/Users/a1021500406/private/uni-agent/docs/设计文档.md)
- [开发文档](/Users/a1021500406/private/uni-agent/docs/开发文档.md)

并已初始化第一版 Python 工程骨架：

- `typer` CLI
- `pydantic` 配置和模型
- `SkillLoader`
- `ToolRegistry`
- 本地 `LocalSandbox` 雏形

## 当前定位

这不是平台项目，而是一个 Client：

- 通过 CLI 或本地接口接收任务
- 通过加载 Skills 获得不同场景能力
- 通过工具系统和沙盒执行实际动作

## 建议下一步

1. 接入真实 `PydanticAI` planner
2. 把 `ToolRegistry` 接到真实执行器
3. 补 `agent replay` 和任务日志存储
4. 增加更多 Skills 和冲突处理策略
5. 演进到 Docker 沙盒

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
agent skills
agent run "summarize the workspace"
pytest
```
