from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from uni_agent.agent.llm import LLMProvider, build_planner_model
from uni_agent.agent.planner import HeuristicPlanner, Planner
from uni_agent.shared.models import PlanStep, SkillSpec, ToolSpec


class LLMPlanStep(BaseModel):
    id: str = Field(description="Stable step id, e.g. step-1.")
    description: str = Field(description="What this step accomplishes.")
    tool: str = Field(description="Tool name from the allowed list.")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Arguments for the tool call.")


class LLMStructuredPlan(BaseModel):
    steps: list[LLMPlanStep] = Field(description="Ordered executable steps.")


_DEFAULT_PLANNER_INSTRUCTIONS = (
    "You produce a short, executable plan for a local coding agent. "
    "Use only the tools listed in the user message. "
    "Prefer file_read for reading files, search_workspace to locate code, "
    "file_write only when the user explicitly needs new or updated file content, "
    "http_fetch only for clear http(s) retrieval needs, "
    "and shell_exec only for trivial inspection (pwd, ls) using "
    '{"command": ["ls"]} or {"command": ["pwd"]} style arguments.'
)


class PydanticAIPlanner(Planner):
    """Uses PydanticAI structured output to build a plan; falls back when unavailable."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        fallback: HeuristicPlanner | None = None,
        defer_model_check: bool = True,
        planner_instructions: str | None = None,
        model_settings: ModelSettings | None = None,
        retries: int = 1,
    ) -> None:
        self._provider = provider
        self._fallback = fallback or HeuristicPlanner()
        instructions = planner_instructions or _DEFAULT_PLANNER_INSTRUCTIONS
        agent_kwargs: dict = {
            "output_type": LLMStructuredPlan,
            "instructions": instructions,
            "defer_model_check": defer_model_check,
            "retries": retries,
        }
        if model_settings:
            agent_kwargs["model_settings"] = model_settings
        resolved_model = build_planner_model(
            provider.model_id,
            openai_base_url=getattr(provider, "openai_base_url", None),
            openai_api_key=getattr(provider, "openai_api_key", None),
        )
        self._agent: Agent[None, LLMStructuredPlan] = Agent(resolved_model, **agent_kwargs)

    def create_plan(
        self,
        task: str,
        selected_skills: list[SkillSpec],
        available_tools: list[ToolSpec],
    ) -> list[PlanStep]:
        if not self._provider.is_available():
            return self._fallback.create_plan(task, selected_skills, available_tools)

        tool_names_set = {tool.name for tool in available_tools}
        allowed = self._resolve_allowed_tools(selected_skills, tool_names_set)
        tool_lines = "\n".join(f"- {t.name}: {t.description}" for t in available_tools if t.name in allowed)
        user_prompt = (
            f"Task:\n{task}\n\n"
            f"Allowed tool names: {sorted(allowed)}\n"
            f"Tool details:\n{tool_lines}\n"
            "Return at least one step when possible."
        )
        result = self._agent.run_sync(user_prompt)
        normalized = self._normalize_plan(result.output, allowed, selected_skills)
        if not normalized:
            return self._fallback.create_plan(task, selected_skills, available_tools)
        return normalized

    def _resolve_allowed_tools(self, selected_skills: list[SkillSpec], tool_names: set[str]) -> set[str]:
        if not selected_skills:
            return set(tool_names)
        restricted: set[str] = set()
        for skill in selected_skills:
            if skill.allowed_tools:
                restricted.update(skill.allowed_tools)
        base = restricted or tool_names
        resolved = base & tool_names
        return resolved if resolved else set(tool_names)

    def _normalize_plan(
        self,
        structured: LLMStructuredPlan,
        allowed_tools: set[str],
        selected_skills: list[SkillSpec],
    ) -> list[PlanStep]:
        selected_skill = selected_skills[0].name if selected_skills else None
        steps: list[PlanStep] = []
        for raw in structured.steps:
            if raw.tool not in allowed_tools:
                continue
            if not self._arguments_valid(raw.tool, raw.arguments):
                continue
            steps.append(
                PlanStep(
                    id=f"step-{len(steps) + 1}",
                    description=raw.description,
                    tool=raw.tool,
                    skill=selected_skill,
                    arguments=raw.arguments,
                )
            )
        return steps

    def _arguments_valid(self, tool: str, arguments: dict[str, Any]) -> bool:
        if tool == "shell_exec":
            command = arguments.get("command")
            return isinstance(command, list) and all(isinstance(part, str) for part in command) and bool(command)
        if tool == "file_read":
            return isinstance(arguments.get("path"), str) and bool(arguments.get("path"))
        if tool == "file_write":
            return isinstance(arguments.get("path"), str) and isinstance(arguments.get("content"), str)
        if tool == "http_fetch":
            return isinstance(arguments.get("url"), str) and bool(arguments.get("url"))
        if tool == "search_workspace":
            return isinstance(arguments.get("query"), str)
        return False
