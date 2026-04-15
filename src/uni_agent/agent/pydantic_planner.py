from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from uni_agent.agent.llm import LLMProvider, build_planner_model
from uni_agent.agent.planner import HeuristicPlanner, Planner
from uni_agent.agent.system_prompts import effective_planner_instructions
from uni_agent.config.settings import DEFAULT_SANDBOX_ALLOWED_COMMANDS, parse_sandbox_allowed_commands
from uni_agent.shared.models import PlanStep, SkillSpec, ToolSpec
from uni_agent.skills.bundle import planner_skill_context

_DEFAULT_ALLOWED_SHELL = frozenset(parse_sandbox_allowed_commands(DEFAULT_SANDBOX_ALLOWED_COMMANDS))

_CMD_LOOKUP_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.+-]{0,255}$")
_CMD_LOOKUP_PREFIX = re.compile(r"^[a-zA-Z0-9_.+-]{1,32}$")


class LLMPlanStep(BaseModel):
    id: str = Field(description="Stable step id, e.g. step-1.")
    description: str = Field(description="What this step accomplishes.")
    tool: str = Field(description="Tool name from the allowed list.")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Arguments for the tool call.")


class LLMStructuredPlan(BaseModel):
    steps: list[LLMPlanStep] = Field(description="Ordered executable steps.")


class PydanticAIPlanner(Planner):
    """Uses PydanticAI structured output to build a plan; falls back when unavailable."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        fallback: HeuristicPlanner | None = None,
        defer_model_check: bool = True,
        planner_instructions: str | None = None,
        global_system_prompt: str | None = None,
        model_settings: ModelSettings | None = None,
        retries: int = 1,
        allowed_shell_commands: frozenset[str] | None = None,
    ) -> None:
        self._provider = provider
        self._fallback = fallback or HeuristicPlanner()
        self._allowed_shell = allowed_shell_commands or _DEFAULT_ALLOWED_SHELL
        instructions = effective_planner_instructions(
            override=planner_instructions,
            global_prefix=global_system_prompt,
        )
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
        session_context: str | None = None,
    ) -> list[PlanStep]:
        if not self._provider.is_available():
            return self._fallback.create_plan(
                task,
                selected_skills,
                available_tools,
                prior_context=prior_context,
                session_context=session_context,
            )

        tool_names_set = {tool.name for tool in available_tools}
        allowed = self._resolve_allowed_tools(selected_skills, tool_names_set)
        mem_q = self._fallback._memory_search_query(task.strip())
        if mem_q is not None and "memory_search" in allowed:
            selected_skill = selected_skills[0].name if selected_skills else None
            return [
                PlanStep(
                    id="step-1",
                    description=f"Search saved session memory for: {mem_q[:120]!r}.",
                    tool="memory_search",
                    skill=selected_skill,
                    arguments={"query": mem_q},
                )
            ]
        tool_lines = "\n".join(f"- {t.name}: {t.description}" for t in available_tools if t.name in allowed)
        user_prompt = f"Task:\n{task}\n\n"
        if session_context:
            user_prompt += (
                "Compressed memory from earlier turns in this client session (same workspace):\n"
                f"{session_context}\n\n"
            )
        if prior_context:
            user_prompt += (
                "Prior execution log (revise the plan; avoid repeating steps that already failed the same way):\n"
                f"{prior_context}\n\n"
            )
        skill_ctx = planner_skill_context(selected_skills)
        if skill_ctx:
            user_prompt += f"Selected skill instructions (follow when relevant):\n{skill_ctx}\n\n"
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
                task,
                selected_skills,
                available_tools,
                prior_context=prior_context,
                session_context=session_context,
            )
        return normalized

    def _resolve_allowed_tools(self, selected_skills: list[SkillSpec], tool_names: set[str]) -> set[str]:
        """All registered tools are always available; skills supply extra instructions, not a subset of tools."""
        return set(tool_names)

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
        if tool == "memory_search":
            if not isinstance(arguments.get("query"), str) or not arguments.get("query", "").strip():
                return False
            if "limit" not in arguments:
                return True
            lim = arguments["limit"]
            if isinstance(lim, bool):
                return False
            if isinstance(lim, int):
                return True
            if isinstance(lim, str) and lim.strip().isdigit():
                return True
            return False
        if tool == "command_lookup":
            name = arguments.get("name")
            prefix = arguments.get("prefix")
            n_ok = isinstance(name, str) and bool(name.strip()) and bool(_CMD_LOOKUP_NAME.match(name.strip()))
            p_ok = isinstance(prefix, str) and bool(prefix.strip()) and bool(
                _CMD_LOOKUP_PREFIX.match(prefix.strip())
            )
            if not n_ok and not p_ok:
                return False
            ih = arguments.get("include_help", True)
            if ih is not None and not isinstance(ih, bool):
                return False
            if "max_list" in arguments:
                ml = arguments["max_list"]
                if isinstance(ml, bool):
                    return False
                if isinstance(ml, int):
                    if not 1 <= ml <= 200:
                        return False
                elif isinstance(ml, str) and ml.strip().isdigit():
                    if not 1 <= int(ml.strip()) <= 200:
                        return False
                else:
                    return False
            return True
        if tool == "run_python":
            if not isinstance(arguments.get("source"), str) or not arguments.get("source", "").strip():
                return False
            if len(arguments["source"]) > 200_000:
                return False
            if "timeout_seconds" not in arguments:
                return True
            ts = arguments["timeout_seconds"]
            if isinstance(ts, bool):
                return False
            if isinstance(ts, int):
                return 1 <= ts <= 120
            if isinstance(ts, str) and ts.strip().isdigit():
                return 1 <= int(ts.strip()) <= 120
            return False
        return False
