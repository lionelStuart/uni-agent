from uni_agent.agent.llm import EnvLLMProvider
from uni_agent.agent.pydantic_planner import PydanticAIPlanner
from uni_agent.tools.registry import ToolRegistry


def test_pydantic_planner_falls_back_without_api_keys(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    registry = ToolRegistry()
    registry.register_builtin_tools()
    planner = PydanticAIPlanner(provider=EnvLLMProvider("openai:gpt-4.1-mini"), defer_model_check=True)

    plan = planner.create_plan("read README.md", [], registry.list_tools())

    assert plan
    assert plan[0].tool == "file_read"


def test_pydantic_planner_shell_exec_validation() -> None:
    planner = PydanticAIPlanner(provider=EnvLLMProvider("openai:gpt-4.1-mini"), defer_model_check=True)
    assert planner._arguments_valid("shell_exec", {"command": ["ls"]})
    assert planner._arguments_valid("shell_exec", {"command": ["ls", "-la"]})
    assert planner._arguments_valid("shell_exec", {"command": ["du", "-sh", "."]})
    assert not planner._arguments_valid("shell_exec", {"command": ["ls|wc"]})
    assert not planner._arguments_valid("shell_exec", {"command": ["ls", "a;b"]})
    assert not planner._arguments_valid("shell_exec", {"command": ["ls && echo"]})
