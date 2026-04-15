from __future__ import annotations

import re

from uni_agent.shared.models import PlanStep, SkillSpec, ToolSpec


class Planner:
    def create_plan(
        self,
        task: str,
        selected_skills: list[SkillSpec],
        available_tools: list[ToolSpec],
        *,
        prior_context: str | None = None,
        session_context: str | None = None,
    ) -> list[PlanStep]:
        raise NotImplementedError


class HeuristicPlanner(Planner):
    _MEMORY_SEARCH_EN = re.compile(r"(?i)^memory\s+search(?:\s+for)?\s+(.+)$")
    _MEMORY_SEARCH_CN = re.compile(r"(?:^|\s)(?:搜索|查找|查询)\s*记忆\s*[：:]\s*(.+)$")
    # Prefer persisted session memory over generic chat (planner LLM otherwise tends to shell_exec+echo).
    _RECALL_SELF = re.compile(
        r"(?i)(?:^|[\s，,])"
        r"(?:我是谁|我叫什么|你认识我吗|还记得我吗|"
        r"我之前说过(?:什么)?|我以前说过(?:什么)?|"
        r"who\s+am\s+i|what(?:'s|\s+is)\s+my\s+name|do\s+you\s+remember\s+me)"
    )
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
        *,
        prior_context: str | None = None,
        session_context: str | None = None,
    ) -> list[PlanStep]:
        effective_task = task
        if session_context:
            effective_task = (
                f"{effective_task}\n\n--- Client session memory (compressed prior turns) ---\n{session_context}"
            )
        if prior_context:
            effective_task = f"{effective_task}\n\n--- Prior execution log (this run) ---\n{prior_context}"
        tool_names = {tool.name for tool in available_tools}
        allowed_tools = self._resolve_allowed_tools(selected_skills, tool_names)
        selected_skill = selected_skills[0].name if selected_skills else None

        mem_q = self._memory_search_query(task.strip())
        if mem_q is not None and "memory_search" in allowed_tools:
            return [
                PlanStep(
                    id="step-1",
                    description=f"Search saved session memory for: {mem_q[:120]!r}.",
                    tool="memory_search",
                    skill=selected_skill,
                    arguments={"query": mem_q},
                )
            ]

        steps: list[PlanStep] = []
        write_spec = self._extract_file_write(effective_task)
        fetch_url = self._extract_fetch_url(effective_task) if self._needs_http_fetch(effective_task) else None

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

        path = self._extract_path(effective_task)
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

        if self._needs_disk_usage_summary(effective_task) and "shell_exec" in allowed_tools:
            steps.append(
                PlanStep(
                    id=f"step-{len(steps) + 1}",
                    description=(
                        "Compare sizes of immediate subdirectories under the workspace root "
                        "(du one level deep; pick the largest line)."
                    ),
                    tool="shell_exec",
                    skill=selected_skill,
                    # BSD/macOS du rejects -s together with -d; -h -d 1 is portable (GNU + BSD).
                    arguments={"command": ["du", "-h", "-d", "1", "."]},
                )
            )

        if self._needs_workspace_search(effective_task) and "search_workspace" in allowed_tools:
            steps.append(
                PlanStep(
                    id=f"step-{len(steps) + 1}",
                    description="Search the workspace for relevant files or matches.",
                    tool="search_workspace",
                    skill=selected_skill,
                    arguments={"query": self._build_search_query(effective_task, path)},
                )
            )

        if self._needs_shell_command(effective_task) and "shell_exec" in allowed_tools:
            steps.append(
                PlanStep(
                    id=f"step-{len(steps) + 1}",
                    description="Inspect the workspace with a safe shell command.",
                    tool="shell_exec",
                    skill=selected_skill,
                    arguments={"command": self._default_shell_command(effective_task)},
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
                        arguments={"query": self._build_search_query(effective_task, path)},
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

    def _memory_search_query(self, task: str) -> str | None:
        t = task.strip()
        m = self._MEMORY_SEARCH_EN.match(t)
        if m:
            q = m.group(1).strip()
            return q if q else None
        m2 = self._MEMORY_SEARCH_CN.search(t)
        if m2:
            q = m2.group(1).strip()
            return q if q else None
        if self._RECALL_SELF.search(t):
            return t
        return None

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
        """Built-in tools are always offered to the planner; skills add ``instruction_text`` only.

        ``SkillSpec.allowed_tools`` does **not** narrow the palette (see design: tools match capabilities).
        """
        return set(tool_names)

    def _extract_path(self, task: str) -> str | None:
        match = self._PATH_PATTERN.search(task)
        if not match:
            return None
        return match.group("path")

    def _needs_disk_usage_summary(self, task: str) -> bool:
        """Largest folder / disk usage style questions need ``du``, not a text search of the task string."""
        task_l = task.lower()
        cn_dir = any(m in task for m in ("文件夹", "目录", "子目录"))
        cn_size = any(m in task for m in ("最大", "哪个大", "磁盘", "空间", "占用"))
        en = any(
            phrase in task_l
            for phrase in (
                "largest folder",
                "largest directory",
                "biggest folder",
                "disk usage",
                "folder size",
                "directory size",
            )
        )
        return (cn_dir and cn_size) or en or "du " in task_l

    def _needs_workspace_search(self, task: str) -> bool:
        if self._needs_disk_usage_summary(task):
            return False
        markers = ("search", "find", "look for", "grep", "where", "查看", "查找", "搜索", "进度", "找到")
        task_lower = task.lower()
        return any(marker in task_lower for marker in markers) or any(
            marker in task for marker in ("查看", "查找", "搜索", "进度", "找到")
        )

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
