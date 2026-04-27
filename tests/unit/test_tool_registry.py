from uni_agent.tools.registry import ToolRegistry
from uni_agent.shared.models import ToolResult, ToolSpec


def test_builtin_tools_are_registered() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    assert "shell_exec" in registry.names()
    assert "search_workspace" in registry.names()
    assert "command_lookup" in registry.names()
    assert "web_search" in registry.names()
    assert "run_python" in registry.names()
    assert "delegate_task" in registry.names()


def test_execute_result_wraps_string_handler() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(name="x", description="x"), lambda _: "hello\nworld")

    result = registry.execute_result("x", {})

    assert result.text == "hello\nworld"
    assert result.summary == "hello"
    assert registry.execute("x", {}) == "hello\nworld"


def test_execute_result_accepts_structured_tool_result() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="x", description="x"),
        lambda _: ToolResult(summary="created", text="done", artifacts=["out.txt"]),
    )

    result = registry.execute_result("x", {})

    assert result.summary == "created"
    assert result.text == "done"
    assert result.artifacts == ["out.txt"]
