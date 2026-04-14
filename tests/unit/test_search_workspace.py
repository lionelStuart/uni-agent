from pathlib import Path

from uni_agent.sandbox.runner import LocalSandbox
from uni_agent.tools.builtins import register_builtin_handlers
from uni_agent.tools.registry import ToolRegistry


def _registry(workspace: Path) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    register_builtin_handlers(registry, workspace, LocalSandbox(workspace))
    return registry


def test_search_workspace_star_lists_files(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "alpha.txt").write_text("content", encoding="utf-8")
    registry = _registry(workspace)

    output = registry.execute("search_workspace", {"query": "*"})

    assert "alpha.txt" in output


def test_search_workspace_fixed_string_matches_line(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "note.txt").write_text("hello TODO world", encoding="utf-8")
    registry = _registry(workspace)

    output = registry.execute("search_workspace", {"query": "TODO"})

    assert "note.txt" in output
    assert "TODO" in output


def test_search_workspace_treats_regex_specials_as_literal_with_fixed_strings(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "x.txt").write_text("a*b pattern", encoding="utf-8")
    registry = _registry(workspace)

    output = registry.execute("search_workspace", {"query": "a*b"})

    assert "x.txt" in output
