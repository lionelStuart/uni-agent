from __future__ import annotations

from uni_agent.shared.models import ToolSpec


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

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
            self._tools[tool.name] = tool

    def list_tools(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return [tool.name for tool in self.list_tools()]

