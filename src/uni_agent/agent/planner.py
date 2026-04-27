from __future__ import annotations

import re

from uni_agent.agent.intent_router import DELEGATE_USER_INTENT_PATTERN, IntentRouter
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
        outcome_feedback: str | None = None,
    ) -> list[PlanStep]:
        raise NotImplementedError


class HeuristicPlanner(Planner):
    _CURATED_CN_NEWS_URLS: tuple[str, ...] = (
        "https://www.chinanews.com.cn/china.shtml",
        "https://news.cctv.com/china/",
        "https://www.thepaper.cn/",
    )
    _CURATED_CN_AI_NEWS_URLS: tuple[str, ...] = (
        "https://www.aibase.com/zh/daily",
        "https://news.softunis.com/ai",
    )
    _MEMORY_SEARCH_EN = re.compile(r"(?i)^memory\s+search(?:\s+for)?\s+(.+)$")
    _MEMORY_SEARCH_CN = re.compile(r"(?:^|\s)(?:搜索|查找|查询)\s*记忆\s*[：:]\s*(.+)$")
    # Prefer persisted session memory over generic chat (planner LLM otherwise tends to shell_exec+echo).
    _RECALL_SELF = re.compile(
        r"(?i)(?:^|[\s，,])"
        r"(?:我是谁|我叫什么|你认识我吗|还记得我吗|"
        r"我之前说过(?:什么)?|我以前说过(?:什么)?|"
        r"who\s+am\s+i|what(?:'s|\s+is)\s+my\s+name|do\s+you\s+remember\s+me)"
    )
    _WEB_SEARCH_EN = re.compile(
        r"(?i)(?:^|\b)(?:web\s+search|search\s+the\s+web|search\s+web|look\s+up|search\s+online)\b"
    )
    _WEB_SEARCH_CN = re.compile(r"(联网搜索|网页搜索|搜索网页|上网查|在线搜索|查官网|搜官网)")
    _PUBLIC_WEB_NEWS_EN = re.compile(
        r"(?i)(?:\b(?:hot|top|trending|breaking|latest|recent|current)\s+(?:news|headlines?)\b|"
        r"\b(?:today(?:'s)?\s+(?:news|headlines?)|(?:news|headlines?)\s+(?:today|now|latest))\b)"
    )
    _PUBLIC_WEB_NEWS_CN = re.compile(
        r"(今天的?(?:热点|热搜|新闻|头条)|今日(?:热点|热搜|新闻|头条)|热点新闻|热搜新闻|最新新闻|新闻热点|今日头条|今天头条)"
    )
    _WEB_RESULT_URL_RE = re.compile(r'"url"\s*:\s*"(?P<url>https?://[^"]+)"', re.IGNORECASE)
    _WEB_RESULT_ENTRY_RE = re.compile(
        r'\{\s*"title"\s*:\s*"(?P<title>[^"]+)"\s*,\s*"url"\s*:\s*"(?P<url>https?://[^"]+)"\s*,\s*"snippet"\s*:\s*"(?P<snippet>[^"]*)"',
        re.IGNORECASE,
    )
    _CONTENT_SEEK_EN = re.compile(
        r"(?i)\b("
        r"news|headline|headlines|latest|today|recent|current|summary|summarize|what happened|"
        r"docs?|documentation|api|reference|tutorial|guide|install|usage|how to|what is|official"
        r")\b"
    )
    _CONTENT_SEEK_CN = re.compile(r"(新闻|头条|最新|今天|今日|近况|发生了什么|总结|摘要|文档|官网|教程|指南|说明|用法|API|是什么|如何)")
    _DOC_LOOKUP_EN = re.compile(r"(?i)\b(docs?|documentation|api|reference|tutorial|guide|install|usage)\b")
    _DOC_LOOKUP_CN = re.compile(r"(文档|教程|指南|说明|用法|API)")
    _OFFICIAL_SITE_EN = re.compile(r"(?i)\b(official\s+(?:site|website)|homepage)\b")
    _RECENCY_HINT_EN = re.compile(r"(?i)\b(today|latest|breaking|recent|current|minutes?\s+ago|hours?\s+ago)\b")
    _RECENCY_HINT_CN = re.compile(r"(今天|今日|最新|刚刚|分钟前|小时前|刚发布|快讯|滚动)")
    _NEWS_LIST_HINT_EN = re.compile(r"(?i)\b(top stories|headline|headlines|latest news|breaking news|live updates?)\b")
    _NEWS_LIST_HINT_CN = re.compile(r"(滚动|头条|热榜|热点|快讯|要闻|最新资讯)")
    _DOC_PATH_HINT = re.compile(r"(?i)/(?:docs?|doc|api|reference|tutorial|guide|learn)(?:/|$)")
    _HOMEPAGE_PENALTY_EN = re.compile(r"(?i)\b(home|homepage|official site|official website)\b")
    _HOMEPAGE_PENALTY_CN = re.compile(r"(官网|首页)")
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

    def __init__(self) -> None:
        self._intent_router = IntentRouter(
            memory_query=self._memory_search_query,
            web_query=self._web_search_query,
        )

    def create_plan(
        self,
        task: str,
        selected_skills: list[SkillSpec],
        available_tools: list[ToolSpec],
        *,
        prior_context: str | None = None,
        session_context: str | None = None,
        outcome_feedback: str | None = None,
    ) -> list[PlanStep]:
        effective_task = task
        if session_context:
            effective_task = (
                f"{effective_task}\n\n--- Client session memory (compressed prior turns) ---\n{session_context}"
            )
        if prior_context:
            effective_task = f"{effective_task}\n\n--- Prior execution log (this run) ---\n{prior_context}"
        if outcome_feedback:
            effective_task = (
                f"{effective_task}\n\n"
                "--- Outcome review (previous batch completed but task may be incomplete; revise the plan) ---\n"
                f"{outcome_feedback}"
            )
        tool_names = {tool.name for tool in available_tools}
        allowed_tools = self._resolve_allowed_tools(selected_skills, tool_names)
        selected_skill = selected_skills[0].name if selected_skills else None

        skip_shortcuts = bool(prior_context or outcome_feedback)
        if not skip_shortcuts:
            routed = self._intent_router.route(
                task,
                allowed_tools=allowed_tools,
                selected_skill=selected_skill,
            )
            if routed is not None:
                return routed

        steps: list[PlanStep] = []
        follow_up_urls = self._extract_follow_up_fetch_urls(task, prior_context)
        if follow_up_urls and "http_fetch" in allowed_tools:
            return [
                PlanStep(
                    id=f"step-{idx}",
                    description=f"Fetch remote content from {url}.",
                    tool="http_fetch",
                    skill=selected_skill,
                    arguments={"url": url},
                )
                for idx, url in enumerate(follow_up_urls, start=1)
            ]
        fallback_urls = self._preferred_direct_http_fetch_urls(task, prior_context)
        if fallback_urls and "http_fetch" in allowed_tools:
            return [
                PlanStep(
                    id=f"step-{idx}",
                    description=f"Fetch remote content from {url}.",
                    tool="http_fetch",
                    skill=selected_skill,
                    arguments={"url": url},
                )
                for idx, url in enumerate(fallback_urls, start=1)
            ]
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

    def _extract_follow_up_fetch_urls(self, task: str, prior_context: str | None) -> list[str]:
        if not prior_context or "web_search completed" not in prior_context:
            return []
        limit = self._follow_up_fetch_limit(task)
        if limit <= 0:
            return []
        ranked = self._rank_web_result_candidates(task, prior_context)
        return [url for url, _score in ranked[:limit]]

    def _rank_web_result_candidates(self, task: str, prior_context: str) -> list[tuple[str, int]]:
        scored: list[tuple[str, int]] = []
        seen: set[str] = set()
        for match in self._WEB_RESULT_ENTRY_RE.finditer(prior_context):
            title = match.group("title").strip()
            url = match.group("url").strip()
            snippet = match.group("snippet").strip()
            if url in seen:
                continue
            seen.add(url)
            scored.append((url, self._score_web_result(task, title, url, snippet)))
        if not scored:
            for match in self._WEB_RESULT_URL_RE.finditer(prior_context):
                url = match.group("url").strip()
                if url in seen:
                    continue
                seen.add(url)
                scored.append((url, 0))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored

    def _score_web_result(self, task: str, title: str, url: str, snippet: str) -> int:
        text = f"{title}\n{snippet}"
        score = 0
        if self._PUBLIC_WEB_NEWS_EN.search(task) or self._PUBLIC_WEB_NEWS_CN.search(task):
            if self._RECENCY_HINT_EN.search(text) or self._RECENCY_HINT_CN.search(text):
                score += 5
            if self._NEWS_LIST_HINT_EN.search(text) or self._NEWS_LIST_HINT_CN.search(text):
                score += 4
            if any(host in url for host in ("chinanews.com.cn", "cctv.com", "thepaper.cn", "news.sina.com.cn")):
                score += 3
        if self._DOC_LOOKUP_EN.search(task) or self._DOC_LOOKUP_CN.search(task):
            if self._DOC_PATH_HINT.search(url):
                score += 5
            if re.search(r"(?i)^https?://docs\.", url):
                score += 4
            if re.search(r"(?i)^https?://docs\.[^/]+/?$", url) or re.search(r"(?i)^https?://www\.[^/]+/doc/?$", url):
                score += 2
            if self._DOC_LOOKUP_EN.search(text) or self._DOC_LOOKUP_CN.search(text):
                score += 4
            if "tutorial" not in task.lower() and "教程" not in task:
                if re.search(r"(?i)(tutorial|/tutorial/)", f"{title}\n{url}"):
                    score -= 3
        if "官网" in task or self._OFFICIAL_SITE_EN.search(task):
            if self._HOMEPAGE_PENALTY_EN.search(title) or self._HOMEPAGE_PENALTY_CN.search(title):
                score += 2
            if re.search(r"^https?://[^/]+/?$", url):
                score += 2
        if self._HOMEPAGE_PENALTY_EN.search(text) or self._HOMEPAGE_PENALTY_CN.search(text):
            score -= 1
        if "duckduckgo.com/" in url:
            score -= 10
        return score

    def _preferred_direct_http_fetch_urls(self, task: str, prior_context: str | None) -> list[str]:
        stripped = task.strip()
        if self._URL_PATTERN.search(stripped) or not prior_context:
            return []
        if "web_search failed" not in prior_context:
            return []
        if "DuckDuckGo returned a bot-detection challenge" not in prior_context:
            return []
        if self._PUBLIC_WEB_NEWS_CN.search(stripped):
            if "AI" in stripped or "ai" in stripped or "人工智能" in stripped:
                return list(self._CURATED_CN_AI_NEWS_URLS)
            return list(self._CURATED_CN_NEWS_URLS)
        return []

    def _follow_up_fetch_limit(self, task: str) -> int:
        if self._PUBLIC_WEB_NEWS_EN.search(task) or self._PUBLIC_WEB_NEWS_CN.search(task):
            return 3
        if self._DOC_LOOKUP_EN.search(task) or self._DOC_LOOKUP_CN.search(task):
            return 2
        if "官网" in task or self._OFFICIAL_SITE_EN.search(task):
            return 1
        if self._CONTENT_SEEK_EN.search(task) or self._CONTENT_SEEK_CN.search(task):
            return 2
        return 0

    def _extract_file_write(self, task: str) -> tuple[str, str] | None:
        for pattern in self._WRITE_PATTERNS:
            match = pattern.search(task)
            if match:
                return match.group("path"), match.group("content")
        return None

    def _web_search_query(self, task: str) -> str | None:
        stripped = task.strip()
        if self._URL_PATTERN.search(stripped):
            return None
        if self._WEB_SEARCH_EN.search(stripped) or self._WEB_SEARCH_CN.search(stripped):
            return stripped
        if self._PUBLIC_WEB_NEWS_EN.search(stripped) or self._PUBLIC_WEB_NEWS_CN.search(stripped):
            return stripped
        if "官网" in stripped:
            return stripped
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
