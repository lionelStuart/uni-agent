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
                description="Execute an allowlisted shell command in the sandbox.",
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
                description="Search files inside the workspace.",
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
