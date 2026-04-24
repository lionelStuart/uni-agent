import json
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


@patch("uni_agent.tools.builtins.urlopen")
def test_http_fetch_normalizes_html_into_readable_text(mock_urlopen) -> None:
    workspace = Path(".")
    registry = ToolRegistry()
    registry.register_builtin_tools()
    register_builtin_handlers(registry, workspace, LocalSandbox(workspace.resolve()))

    html = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>Example News</title>
        <meta name="description" content="Top story summary">
      </head>
      <body>
        <article>
          <h1>Breaking headline</h1>
          <p>Today something important happened.</p>
        </article>
      </body>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.read.return_value = html.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    mock_urlopen.return_value = mock_resp

    output = registry.execute("http_fetch", {"url": "https://example.com"})

    assert "Title: Example News" in output
    assert "Description: Top story summary" in output
    assert "Page Type: article" in output
    assert "Key Points:" in output
    assert "Text: Example News Breaking headline Today something important happened." in output


@patch("uni_agent.tools.builtins.urlopen")
def test_web_search_returns_structured_results(mock_urlopen) -> None:
    workspace = Path(".")
    registry = ToolRegistry()
    registry.register_builtin_tools()
    register_builtin_handlers(registry, workspace, LocalSandbox(workspace.resolve()))

    html = """
    <html><body>
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fdocs">Example Docs</a>
      <a class="result__snippet">Official documentation home page</a>
    </body></html>
    """
    mock_resp = MagicMock()
    mock_resp.read.return_value = html.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    mock_urlopen.return_value = mock_resp

    output = registry.execute("web_search", {"query": "example docs", "count": 3})
    payload = json.loads(output)

    assert payload["provider"] == "duckduckgo"
    assert payload["query"] == "example docs"
    assert payload["count"] == 1
    assert payload["results"][0]["title"] == "Example Docs"
    assert payload["results"][0]["url"] == "https://example.com/docs"
    assert "Official documentation" in payload["results"][0]["snippet"]


@patch("uni_agent.tools.builtins.urlopen")
def test_web_search_decodes_duckduckgo_ad_redirect_urls(mock_urlopen) -> None:
    workspace = Path(".")
    registry = ToolRegistry()
    registry.register_builtin_tools()
    register_builtin_handlers(registry, workspace, LocalSandbox(workspace.resolve()))

    html = """
    <html><body>
      <a class="result__a" href="https://duckduckgo.com/y.js?u3=https%3A%2F%2Fexample.com%2Farticle">Example Article</a>
      <a class="result__snippet">Decoded target page</a>
    </body></html>
    """
    mock_resp = MagicMock()
    mock_resp.read.return_value = html.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    mock_urlopen.return_value = mock_resp

    output = registry.execute("web_search", {"query": "example article", "count": 3})
    payload = json.loads(output)

    assert payload["count"] == 1
    assert payload["results"][0]["url"] == "https://example.com/article"


@patch("uni_agent.tools.builtins.ssl.create_default_context")
@patch("uni_agent.tools.builtins.urlopen")
def test_http_fetch_uses_configured_ca_bundle(mock_urlopen, mock_create_default_context, tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    ca_bundle = tmp_path / "certs" / "corp-root.pem"
    ca_bundle.parent.mkdir(parents=True)
    ca_bundle.write_text("dummy", encoding="utf-8")

    ssl_context = object()
    mock_create_default_context.return_value = ssl_context
    registry = ToolRegistry()
    registry.register_builtin_tools()
    register_builtin_handlers(
        registry,
        workspace,
        LocalSandbox(workspace),
        ca_bundle_path=ca_bundle,
    )

    mock_resp = MagicMock()
    mock_resp.read.return_value = b"hello"
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    mock_urlopen.return_value = mock_resp

    registry.execute("http_fetch", {"url": "https://example.com"})

    mock_create_default_context.assert_called_once_with(cafile=str(ca_bundle))
    assert mock_urlopen.call_args.kwargs["context"] is ssl_context


@patch("uni_agent.tools.builtins.ssl._create_unverified_context")
@patch("uni_agent.tools.builtins.ssl.create_default_context")
@patch("uni_agent.tools.builtins.urlopen")
def test_http_fetch_can_skip_tls_verification(
    mock_urlopen, mock_create_default_context, mock_create_unverified_context, tmp_path: Path
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()

    insecure_context = object()
    mock_create_unverified_context.return_value = insecure_context
    registry = ToolRegistry()
    registry.register_builtin_tools()
    register_builtin_handlers(
        registry,
        workspace,
        LocalSandbox(workspace),
        skip_tls_verify=True,
    )

    mock_resp = MagicMock()
    mock_resp.read.return_value = b"hello"
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    mock_urlopen.return_value = mock_resp

    registry.execute("http_fetch", {"url": "https://example.com"})

    mock_create_unverified_context.assert_called_once_with()
    mock_create_default_context.assert_not_called()
    assert mock_urlopen.call_args.kwargs["context"] is insecure_context


@patch("uni_agent.tools.builtins.ssl._create_unverified_context")
@patch("uni_agent.tools.builtins.ssl.create_default_context")
def test_skip_tls_verify_takes_precedence_over_ca_bundle(
    mock_create_default_context, mock_create_unverified_context, tmp_path: Path
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    ca_bundle = tmp_path / "certs" / "corp-root.pem"
    ca_bundle.parent.mkdir(parents=True)
    ca_bundle.write_text("dummy", encoding="utf-8")

    registry = ToolRegistry()
    registry.register_builtin_tools()
    register_builtin_handlers(
        registry,
        workspace,
        LocalSandbox(workspace),
        ca_bundle_path=ca_bundle,
        skip_tls_verify=True,
    )

    mock_create_unverified_context.assert_called_once_with()
    mock_create_default_context.assert_not_called()


def test_register_builtin_handlers_rejects_missing_ca_bundle(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    registry = ToolRegistry()
    registry.register_builtin_tools()

    with pytest.raises(ValueError, match="Configured CA bundle does not exist"):
        register_builtin_handlers(
            registry,
            workspace,
            LocalSandbox(workspace),
            ca_bundle_path=tmp_path / "missing.pem",
        )
