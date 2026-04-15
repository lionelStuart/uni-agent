from __future__ import annotations

from collections.abc import Callable

from uni_agent.shared.models import ToolSpec


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._handlers: dict[str, Callable[[dict], str]] = {}

    def register(self, tool: ToolSpec, handler: Callable[[dict], str] | None = None) -> None:
        self._tools[tool.name] = tool
        if handler is not None:
            self._handlers[tool.name] = handler

    def register_builtin_tools(self) -> None:
        for tool in (
            ToolSpec(
                name="shell_exec",
                description=(
                    "Run one program via argv only (JSON list of strings); "
                    "no shell, pipes, or operators — the first string is the executable name. "
                    "Binaries not on the sandbox allowlist may require interactive approval (CLI)."
                ),
                risk_level="high",
            ),
            ToolSpec(
                name="file_read",
                description="Read a file from the workspace.",
            ),
            ToolSpec(
                name="file_write",
                description="Write a file inside the workspace.",
                risk_level="high",
            ),
            ToolSpec(
                name="http_fetch",
                description="Fetch a remote resource when network access is allowed.",
                risk_level="medium",
            ),
            ToolSpec(
                name="search_workspace",
                description=(
                    "Search file contents: `query` is a literal substring (ripgrep fixed-string, not regex). "
                    "Whitespace is normalized to single spaces (do not paste multi-line logs into `query`). "
                    "Queries `*`, `**`, `.*`, or whitespace-only list files in the workspace."
                ),
            ),
            ToolSpec(
                name="command_lookup",
                description=(
                    "Discover local CLI programs on PATH before using shell_exec. "
                    "Two modes: (1) `name` — resolve one command via which, optional `include_help` (default true) "
                    "captures --help or -h from the resolved binary (timeout capped). "
                    "(2) `prefix` — list executable basenames on PATH starting with `prefix` (optional `max_list`, default 60). "
                    "Provide either `name` or `prefix` (if both, `name` wins). Does not modify workspace files."
                ),
                risk_level="low",
            ),
            ToolSpec(
                name="run_python",
                description=(
                    "Execute a Python snippet in the workspace sandbox: writes a temporary `.py` under "
                    "`.uni-agent/code_run/`, runs `python3` or `python` with cwd=workspace (so imports can use "
                    "project packages), then deletes the file. Args: `source` (required), optional `timeout_seconds` "
                    "(1–120, default 30). Stderr is appended on success when non-empty. Non-zero exit raises."
                ),
                risk_level="high",
            ),
            ToolSpec(
                name="memory_search",
                description=(
                    "Recall saved client-session memory: when an LLM is configured, expands `query` into keywords, "
                    "matches L0 index lines, then reads matching L1 records and returns a synthesized answer; "
                    "otherwise substring search on the index. Optional `limit` (1–50) caps rows considered."
                ),
            ),
        ):
            self.register(tool)

    def list_tools(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return [tool.name for tool in self.list_tools()]

    def attach_handler(self, tool_name: str, handler: Callable[[dict], str]) -> None:
        if tool_name not in self._tools:
            raise KeyError(f"Tool '{tool_name}' is not registered.")
        self._handlers[tool_name] = handler

    def execute(self, tool_name: str | None, arguments: dict) -> str:
        if not tool_name:
            raise ValueError("Plan step does not define a tool.")
        handler = self._handlers.get(tool_name)
        if handler is None:
            raise KeyError(f"Tool '{tool_name}' has no execution handler.")
        return handler(arguments)
