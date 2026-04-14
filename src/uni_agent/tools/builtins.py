from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from uni_agent.agent.llm import LLMProvider
from uni_agent.agent.memory_llm_search import run_memory_search_llm
from uni_agent.observability.local_memory import search_memory_directory
from uni_agent.sandbox.runner import LocalSandbox
from uni_agent.tools.http_fetch_policy import (
    assert_http_fetch_host_allowlist,
    assert_public_http_url,
    strip_url_fragment,
)

_RG_OK_NO_MATCH = frozenset({0, 1})


def register_builtin_handlers(
    tool_registry,
    workspace: Path,
    sandbox: LocalSandbox,
    *,
    http_fetch_max_bytes: int = 500_000,
    http_fetch_allow_private_networks: bool = False,
    http_fetch_allowed_hosts: frozenset[str] = frozenset(),
    http_fetch_timeout_seconds: int = 30,
    memory_dir: Path | None = None,
    memory_llm_provider: LLMProvider | None = None,
    memory_search_use_llm: bool = False,
    memory_search_max_hits: int = 12,
    memory_search_model_settings: dict[str, Any] | None = None,
    memory_search_keyword_retries: int = 1,
) -> None:
    resolved_workspace = workspace.resolve()
    resolved_memory_dir = (memory_dir or (resolved_workspace / ".uni-agent" / "memory")).resolve()

    def shell_exec(arguments: dict) -> str:
        command = arguments.get("command")
        if not isinstance(command, list) or not command:
            raise ValueError("shell_exec requires a non-empty 'command' list.")
        return sandbox.run([str(part) for part in command])

    def file_read(arguments: dict) -> str:
        path_value = arguments.get("path")
        if not path_value or not isinstance(path_value, str):
            raise ValueError("file_read requires a 'path' string.")
        target = _resolve_workspace_path(resolved_workspace, path_value)
        return _truncate(target.read_text(encoding="utf-8"))

    def file_write(arguments: dict) -> str:
        path_value = arguments.get("path")
        content = arguments.get("content")
        if not path_value or not isinstance(path_value, str):
            raise ValueError("file_write requires a 'path' string.")
        if not isinstance(content, str):
            raise ValueError("file_write requires a 'content' string.")
        target = _resolve_workspace_write_path(resolved_workspace, path_value)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} characters to {path_value}."

    def http_fetch(arguments: dict) -> str:
        url = arguments.get("url")
        if not url or not isinstance(url, str):
            raise ValueError("http_fetch requires a 'url' string.")
        url = strip_url_fragment(url.strip())
        if not url.startswith(("http://", "https://")):
            raise ValueError("http_fetch only supports http(s) URLs.")
        assert_public_http_url(url, allow_private_networks=http_fetch_allow_private_networks)
        parsed = urlparse(url)
        assert_http_fetch_host_allowlist(parsed.hostname, http_fetch_allowed_hosts)
        req = Request(url, headers={"User-Agent": "uni-agent/0.1"}, method="GET")
        try:
            with urlopen(req, timeout=http_fetch_timeout_seconds) as resp:
                body = resp.read(http_fetch_max_bytes + 1)
        except HTTPError as exc:
            raise ValueError(f"http_fetch failed with HTTP {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            raise ValueError(f"http_fetch failed: {exc.reason}") from exc
        if len(body) > http_fetch_max_bytes:
            body = body[:http_fetch_max_bytes]
            suffix = "\n... [truncated by max bytes]"
        else:
            suffix = ""
        text = body.decode("utf-8", errors="replace")
        return _truncate(f"{text}{suffix}")

    def memory_search(arguments: dict) -> str:
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("memory_search requires a non-empty 'query' string.")
        raw_limit = arguments.get("limit", 20)
        if raw_limit is None:
            limit = 20
        elif isinstance(raw_limit, int):
            limit = raw_limit
        else:
            try:
                limit = int(raw_limit)
            except (TypeError, ValueError):
                limit = 20
        limit = max(1, min(50, limit))
        max_entries = min(50, max(limit, memory_search_max_hits))
        if (
            memory_llm_provider is not None
            and memory_search_use_llm
            and memory_llm_provider.is_available()
        ):
            try:
                return run_memory_search_llm(
                    query.strip(),
                    resolved_memory_dir,
                    memory_llm_provider,
                    model_settings=memory_search_model_settings,
                    keyword_retries=memory_search_keyword_retries,
                    max_hits=max_entries,
                )
            except Exception:
                pass
        return search_memory_directory(resolved_memory_dir, query.strip(), limit=limit)

    def search_workspace(arguments: dict) -> str:
        query = arguments.get("query")
        if not isinstance(query, str):
            raise ValueError("search_workspace requires a 'query' string.")
        # Collapse whitespace/newlines so pasted prior-context blobs do not break ripgrep's pattern.
        needle = " ".join(query.strip().split())
        # ``*`` / ``.*`` are invalid or misleading as ripgrep regex; treat as "list files in workspace".
        broad = not needle or needle in ("*", "**", ".*")
        if broad:
            # ripgrep uses exit 1 for "no matches"; treat as success for listing/search UX.
            return sandbox.run(
                ["rg", "--files", str(resolved_workspace)],
                accept_exit_codes=_RG_OK_NO_MATCH,
            )
        # Fixed-string search avoids regex footguns from LLM output (e.g. bare ``*``).
        return sandbox.run(
            ["rg", "-n", "-F", "--", needle, str(resolved_workspace)],
            accept_exit_codes=_RG_OK_NO_MATCH,
        )

    tool_registry.attach_handler("shell_exec", shell_exec)
    tool_registry.attach_handler("file_read", file_read)
    tool_registry.attach_handler("file_write", file_write)
    tool_registry.attach_handler("http_fetch", http_fetch)
    tool_registry.attach_handler("search_workspace", search_workspace)
    tool_registry.attach_handler("memory_search", memory_search)


def _resolve_workspace_path(workspace: Path, raw_path: str) -> Path:
    candidate = (workspace / raw_path).resolve()
    if candidate != workspace and workspace not in candidate.parents:
        raise ValueError(f"Path '{raw_path}' is outside the workspace.")
    if not candidate.exists():
        raise FileNotFoundError(f"Path '{raw_path}' does not exist.")
    if not candidate.is_file():
        raise ValueError(f"Path '{raw_path}' is not a file.")
    return candidate


def _resolve_workspace_write_path(workspace: Path, raw_path: str) -> Path:
    candidate = (workspace / raw_path).resolve()
    if candidate != workspace and workspace not in candidate.parents:
        raise ValueError(f"Path '{raw_path}' is outside the workspace.")
    return candidate


def _truncate(content: str, max_chars: int = 4000) -> str:
    if len(content) <= max_chars:
        return content
    return f"{content[:max_chars]}... [truncated]"
