from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from uni_agent.sandbox.runner import LocalSandbox
from uni_agent.tools.builtins import register_builtin_handlers, _resolve_workspace_write_path
from uni_agent.tools.registry import ToolRegistry


def test_file_write_creates_nested_file(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    registry = ToolRegistry()
    registry.register_builtin_tools()
    register_builtin_handlers(registry, workspace, LocalSandbox(workspace))

    registry.execute("file_write", {"path": "nested/note.txt", "content": "hello"})

    assert (workspace / "nested" / "note.txt").read_text(encoding="utf-8") == "hello"


def test_file_read_rejects_path_traversal(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("x", encoding="utf-8")
    registry = ToolRegistry()
    registry.register_builtin_tools()
    register_builtin_handlers(registry, workspace, LocalSandbox(workspace))

    with pytest.raises(ValueError):
        registry.execute("file_read", {"path": "../secret.txt"})


def test_file_write_rejects_path_traversal(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("x", encoding="utf-8")

    with pytest.raises(ValueError):
        _resolve_workspace_write_path(workspace, "../secret.txt")


@patch("uni_agent.tools.builtins.urlopen")
def test_http_fetch_returns_decoded_body(mock_urlopen) -> None:
    workspace = Path(".")
    registry = ToolRegistry()
    registry.register_builtin_tools()
    register_builtin_handlers(registry, workspace, LocalSandbox(workspace.resolve()))

    mock_resp = MagicMock()
    mock_resp.read.return_value = b"hello"
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    mock_urlopen.return_value = mock_resp

    output = registry.execute("http_fetch", {"url": "https://example.com"})

    assert "hello" in output
