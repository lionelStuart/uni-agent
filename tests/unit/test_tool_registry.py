from uni_agent.tools.registry import ToolRegistry


def test_builtin_tools_are_registered() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    assert "shell_exec" in registry.names()
    assert "search_workspace" in registry.names()

