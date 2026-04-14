from __future__ import annotations

import re

from uni_agent.shared.models import PlanStep, SkillSpec, ToolSpec


class Planner:
    def create_plan(
        self,
        task: str,
        selected_skills: list[SkillSpec],
        available_tools: list[ToolSpec],
    ) -> list[PlanStep]:
        raise NotImplementedError


class HeuristicPlanner(Planner):
    _PATH_PATTERN = re.compile(r"(?P<path>[\w./-]+\.[A-Za-z0-9]+)")
    _URL_PATTERN = re.compile(r"(https?://[^\s\"'<>]+)", re.IGNORECASE)
    _WRITE_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(
            r'(?i)write\s+the\s+file\s+(?P<path>[\w./-]+\.[A-Za-z0-9]+)\s+with\s+content\s+"(?P<content>[^"]*)"'
        ),
        re.compile(
            r"(?i)write\s+the\s+file\s+(?P<path>[\w./-]+\.[A-Za-z0-9]+)\s+with\s+content\s+'(?P<content>[^']*)'"
        ),
        re.compile(r'(?i)(?:write|写入)\s+(?P<path>[\w./-]+\.[A-Za-z0-9]+)\s*[:=]\s*"(?P<content>[^"]*)"'),
        re.compile(r"(?i)(?:write|写入)\s+(?P<path>[\w./-]+\.[A-Za-z0-9]+)\s*[:=]\s*'(?P<content>[^']*)'"),
    )

    def create_plan(
        self,
        task: str,
        selected_skills: list[SkillSpec],
        available_tools: list[ToolSpec],
    ) -> list[PlanStep]:
        tool_names = {tool.name for tool in available_tools}
        allowed_tools = self._resolve_allowed_tools(selected_skills, tool_names)
        selected_skill = selected_skills[0].name if selected_skills else None

        steps: list[PlanStep] = []
        write_spec = self._extract_file_write(task)
        fetch_url = self._extract_fetch_url(task) if self._needs_http_fetch(task) else None

        if fetch_url and "http_fetch" in allowed_tools:
            steps.append(
                PlanStep(
                    id=f"step-{len(steps) + 1}",
                    description=f"Fetch remote content from {fetch_url}.",
                    tool="http_fetch",
                    skill=selected_skill,
                    arguments={"url": fetch_url},
                )
            )

        if write_spec and "file_write" in allowed_tools:
            write_path, write_content = write_spec
            steps.append(
                PlanStep(
                    id=f"step-{len(steps) + 1}",
                    description=f"Write workspace file {write_path}.",
                    tool="file_write",
                    skill=selected_skill,
                    arguments={"path": write_path, "content": write_content},
                )
            )

        path = self._extract_path(task)
        if path and "file_read" in allowed_tools:
            if not (write_spec and write_spec[0] == path):
                steps.append(
                    PlanStep(
                        id=f"step-{len(steps) + 1}",
                        description=f"Read the referenced file {path}.",
                        tool="file_read",
                        skill=selected_skill,
                        arguments={"path": path},
                    )
                )

        if self._needs_workspace_search(task) and "search_workspace" in allowed_tools:
            steps.append(
                PlanStep(
                    id=f"step-{len(steps) + 1}",
                    description="Search the workspace for relevant files or matches.",
                    tool="search_workspace",
                    skill=selected_skill,
                    arguments={"query": self._build_search_query(task, path)},
                )
            )

        if self._needs_shell_command(task) and "shell_exec" in allowed_tools:
            steps.append(
                PlanStep(
                    id=f"step-{len(steps) + 1}",
                    description="Inspect the workspace with a safe shell command.",
                    tool="shell_exec",
                    skill=selected_skill,
                    arguments={"command": self._default_shell_command(task)},
                )
            )

        if not steps:
            if "search_workspace" in allowed_tools:
                steps.append(
                    PlanStep(
                        id="step-1",
                        description="Search the workspace using the full task as context.",
                        tool="search_workspace",
                        skill=selected_skill,
                        arguments={"query": self._build_search_query(task, path)},
                    )
                )
            elif "shell_exec" in allowed_tools:
                steps.append(
                    PlanStep(
                        id="step-1",
                        description="List the workspace root for basic context.",
                        tool="shell_exec",
                        skill=selected_skill,
                        arguments={"command": ["pwd"]},
                    )
                )
        return steps

    def _extract_file_write(self, task: str) -> tuple[str, str] | None:
        for pattern in self._WRITE_PATTERNS:
            match = pattern.search(task)
            if match:
                return match.group("path"), match.group("content")
        return None

    def _needs_http_fetch(self, task: str) -> bool:
        if self._URL_PATTERN.search(task):
            return True
        markers = ("fetch", "http fetch", "下载", "curl ", "wget ")
        task_lower = task.lower()
        return any(marker in task_lower for marker in markers)

    def _extract_fetch_url(self, task: str) -> str | None:
        match = self._URL_PATTERN.search(task)
        if not match:
            return None
        return match.group(1).rstrip(").,;]")

    def _resolve_allowed_tools(self, selected_skills: list[SkillSpec], tool_names: set[str]) -> set[str]:
        if not selected_skills:
            return set(tool_names)

        allowed: set[str] = set()
        for skill in selected_skills:
            if skill.allowed_tools:
                allowed.update(skill.allowed_tools)
        return allowed or set(tool_names)

    def _extract_path(self, task: str) -> str | None:
        match = self._PATH_PATTERN.search(task)
        if not match:
            return None
        return match.group("path")

    def _needs_workspace_search(self, task: str) -> bool:
        markers = ("search", "find", "look for", "grep", "where", "查看", "查找", "搜索", "进度")
        task_lower = task.lower()
        return any(marker in task_lower for marker in markers) or any(marker in task for marker in ("查看", "查找", "搜索", "进度"))

    def _needs_shell_command(self, task: str) -> bool:
        markers = ("pwd", "ls", "list", "目录", "文件列表")
        task_lower = task.lower()
        return any(marker in task_lower for marker in markers) or any(marker in task for marker in ("目录", "文件列表"))

    def _build_search_query(self, task: str, path: str | None) -> str:
        query = task.strip()
        if path:
            query = query.replace(path, "").strip()
        return query or "TODO"

    def _default_shell_command(self, task: str) -> list[str]:
        if "pwd" in task.lower():
            return ["pwd"]
        return ["ls"]
