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


def test_pydantic_planner_delegate_task_validation() -> None:
    planner = PydanticAIPlanner(provider=EnvLLMProvider("openai:gpt-4.1-mini"), defer_model_check=True)
    assert planner._arguments_valid("delegate_task", {"task": "read README.md and summarize"})
    assert planner._arguments_valid(
        "delegate_task",
        {"task": "sub", "context": "paths under docs/", "include_session": False},
    )
    assert not planner._arguments_valid("delegate_task", {})
    assert not planner._arguments_valid("delegate_task", {"task": ""})
    assert not planner._arguments_valid("delegate_task", {"task": "x", "context": 1})
    assert not planner._arguments_valid("delegate_task", {"task": "x", "include_session": "yes"})


def test_pydantic_planner_web_search_validation() -> None:
    planner = PydanticAIPlanner(provider=EnvLLMProvider("openai:gpt-4.1-mini"), defer_model_check=True)
    assert planner._arguments_valid("web_search", {"query": "Python docs"})
    assert planner._arguments_valid(
        "web_search",
        {"query": "Python docs", "count": 5, "region": "us-en", "safe_search": "moderate"},
    )
    assert not planner._arguments_valid("web_search", {})
    assert not planner._arguments_valid("web_search", {"query": ""})
    assert not planner._arguments_valid("web_search", {"query": "x", "count": 99})
    assert not planner._arguments_valid("web_search", {"query": "x", "safe_search": "maybe"})


def test_pydantic_planner_falls_back_when_run_sync_raises(monkeypatch) -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    planner = PydanticAIPlanner(provider=EnvLLMProvider("openai:gpt-4.1-mini"), defer_model_check=True)

    class _Boom:
        def run_sync(self, _prompt):
            raise RuntimeError("Exceeded maximum retries (1) for output validation")

    monkeypatch.setattr(planner, "_agent", _Boom())

    plan = planner.create_plan("read README.md", [], registry.list_tools())

    assert plan
    assert plan[0].tool == "file_read"
