from uni_agent.tools.registry import ToolRegistry


def test_builtin_tools_are_registered() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    assert "shell_exec" in registry.names()
    assert "search_workspace" in registry.names()
    assert "command_lookup" in registry.names()
    assert "web_search" in registry.names()
    assert "run_python" in registry.names()
    assert "delegate_task" in registry.names()
