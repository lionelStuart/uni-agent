# uni-agent

一个可加载可插拔 Skills 的通用 Agent Client。

项目核心由三部分组成：

- Agent Runtime
- 通用 Sandbox
- Skills 插件机制

当前仓库处于设计阶段，已完成首版客户端文档：

- [设计文档](/Users/a1021500406/private/uni-agent/docs/设计文档.md)
- [开发文档](/Users/a1021500406/private/uni-agent/docs/开发文档.md)
- [进度文档](/Users/a1021500406/private/uni-agent/docs/进度文档.md)

并已初始化第一版 Python 工程骨架：

- `typer` CLI
- `pydantic` 配置和模型
- `SkillLoader`
- `ToolRegistry`
- 本地 `LocalSandbox` 雏形

## 开发约束

后续开发必须遵循以下文档：

- [设计文档](/Users/a1021500406/private/uni-agent/docs/设计文档.md)
- [开发文档](/Users/a1021500406/private/uni-agent/docs/开发文档.md)
- [进度文档](/Users/a1021500406/private/uni-agent/docs/进度文档.md)

其中：

- 设计文档定义项目边界和架构原则
- 开发文档定义技术栈、模块拆解、实现步骤和测试项
- 进度文档定义开发计划、每轮进展和下一轮 TODO

如果实现与文档不一致，应先更新文档，再继续开发。

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
