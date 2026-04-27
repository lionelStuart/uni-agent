from __future__ import annotations

import re
from collections.abc import Callable

from uni_agent.shared.models import PlanStep

DELEGATE_USER_INTENT_PATTERN = re.compile(r"(?i)(delegate_task|子代理|sub-agent|\bsubagent\b)")


class IntentRouter:
    def __init__(
        self,
        *,
        memory_query: Callable[[str], str | None],
        web_query: Callable[[str], str | None],
    ) -> None:
        self._memory_query = memory_query
        self._web_query = web_query

    def route(
        self,
        task: str,
        *,
        allowed_tools: set[str],
        selected_skill: str | None,
    ) -> list[PlanStep] | None:
        stripped_task = task.strip()
        mem_q = self._memory_query(stripped_task)
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

        if DELEGATE_USER_INTENT_PATTERN.search(stripped_task) and "delegate_task" in allowed_tools:
            return [
                PlanStep(
                    id="step-1",
                    description="Run nested agent (user explicitly requested sub-agent / delegate_task).",
                    tool="delegate_task",
                    skill=selected_skill,
                    arguments={"task": stripped_task},
                )
            ]

        web_q = self._web_query(stripped_task)
        if web_q is not None and "web_search" in allowed_tools:
            return [
                PlanStep(
                    id="step-1",
                    description=f"Search the public web for: {web_q[:120]!r}.",
                    tool="web_search",
                    skill=selected_skill,
                    arguments={"query": web_q},
                )
            ]
        return None
