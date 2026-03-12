from __future__ import annotations

from pathlib import Path

from uni_agent.sandbox.runner import LocalSandbox


def register_builtin_handlers(tool_registry, workspace: Path, sandbox: LocalSandbox) -> None:
    resolved_workspace = workspace.resolve()

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

    def search_workspace(arguments: dict) -> str:
        query = arguments.get("query")
        if not query or not isinstance(query, str):
            raise ValueError("search_workspace requires a non-empty 'query' string.")
        return sandbox.run(["rg", "-n", query, str(resolved_workspace)])

    tool_registry.attach_handler("shell_exec", shell_exec)
    tool_registry.attach_handler("file_read", file_read)
    tool_registry.attach_handler("search_workspace", search_workspace)


def _resolve_workspace_path(workspace: Path, raw_path: str) -> Path:
    candidate = (workspace / raw_path).resolve()
    if candidate != workspace and workspace not in candidate.parents:
        raise ValueError(f"Path '{raw_path}' is outside the workspace.")
    if not candidate.exists():
        raise FileNotFoundError(f"Path '{raw_path}' does not exist.")
    if not candidate.is_file():
        raise ValueError(f"Path '{raw_path}' is not a file.")
    return candidate


def _truncate(content: str, max_chars: int = 4000) -> str:
    if len(content) <= max_chars:
        return content
    return f"{content[:max_chars]}... [truncated]"
