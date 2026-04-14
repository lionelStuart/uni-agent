from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from uni_agent.agent.llm import LLMProvider, build_planner_model
from uni_agent.agent.planner import HeuristicPlanner, Planner
from uni_agent.config.settings import DEFAULT_SANDBOX_ALLOWED_COMMANDS, parse_sandbox_allowed_commands
from uni_agent.shared.models import PlanStep, SkillSpec, ToolSpec

_DEFAULT_ALLOWED_SHELL = frozenset(parse_sandbox_allowed_commands(DEFAULT_SANDBOX_ALLOWED_COMMANDS))


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
    "and shell_exec only when needed. "
    "For 'largest folder', 'disk usage', or similar, use shell_exec with du as argv "
    '(e.g. {"command": ["du", "-h", "-d", "1", "."]} from workspace root; '
    "never combine -sh with -d on macOS/BSD). "
    "Do not use search_workspace on the question text for this. "
    "For shell_exec you MUST pass a JSON argv list: each element is one argument; "
    "there is no shell — pipes, redirects, semicolons, &&/||, command substitution, "
    "or a single string containing multiple tokens are invalid. "
    "The first element is the program name (one token, no spaces). "
    "Programs on the pre-approved list in the user message run immediately; "
    "others may require interactive user approval at execution time."
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
        allowed_shell_commands: frozenset[str] | None = None,
    ) -> None:
        self._provider = provider
        self._fallback = fallback or HeuristicPlanner()
        self._allowed_shell = allowed_shell_commands or _DEFAULT_ALLOWED_SHELL
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
        *,
        prior_context: str | None = None,
    ) -> list[PlanStep]:
        if not self._provider.is_available():
            return self._fallback.create_plan(
                task, selected_skills, available_tools, prior_context=prior_context
            )

        tool_names_set = {tool.name for tool in available_tools}
        allowed = self._resolve_allowed_tools(selected_skills, tool_names_set)
        tool_lines = "\n".join(f"- {t.name}: {t.description}" for t in available_tools if t.name in allowed)
        user_prompt = f"Task:\n{task}\n\n"
        if prior_context:
            user_prompt += (
                "Prior execution log (revise the plan; avoid repeating steps that already failed the same way):\n"
                f"{prior_context}\n\n"
            )
        shell_allow = ", ".join(sorted(self._allowed_shell))
        user_prompt += (
            f"Allowed tool names: {sorted(allowed)}\n"
            f"Tool details:\n{tool_lines}\n"
            f"shell_exec pre-approved first argv tokens (no shell, no pipes; run without prompt): {shell_allow}\n"
            "Other single-program argv lists are allowed in the plan but may require user approval when executed.\n"
            "Return at least one step when possible."
        )
        result = self._agent.run_sync(user_prompt)
        normalized = self._normalize_plan(result.output, allowed, selected_skills)
        if not normalized:
            return self._fallback.create_plan(
                task, selected_skills, available_tools, prior_context=prior_context
            )
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
            if not isinstance(command, list) or not command:
                return False
            if not all(isinstance(part, str) for part in command):
                return False
            exe = command[0]
            if any(ch.isspace() for ch in exe):
                return False
            for part in command:
                if any(bad in part for bad in ("|", ";", "\n", "\r", "&&", "||", "`", "$(")):
                    return False
            return True
        if tool == "file_read":
            return isinstance(arguments.get("path"), str) and bool(arguments.get("path"))
        if tool == "file_write":
            return isinstance(arguments.get("path"), str) and isinstance(arguments.get("content"), str)
        if tool == "http_fetch":
            return isinstance(arguments.get("url"), str) and bool(arguments.get("url"))
        if tool == "search_workspace":
            return isinstance(arguments.get("query"), str)
        return False
