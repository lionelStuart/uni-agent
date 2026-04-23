"""LLM step: after a fully **completed** plan batch, decide if the user task is satisfied; if not, feed `planner_brief` into the next `create_plan` as `outcome_feedback`."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent

from uni_agent.agent.llm import LLMProvider, build_planner_model
from uni_agent.agent.system_prompts import effective_goal_check_instructions
from uni_agent.shared.models import PlanStep

_DIGEST_MAX = 12_000
_STEP_OUT_MAX = 3_200


def build_goal_check_digest(
    task: str,
    steps: list[PlanStep],
    session_context: str | None,
) -> str:
    """Compact execution log for goal review (only completed steps are expected in typical use)."""
    lines: list[str] = [f"User task:\n{task}\n", "Tool steps (this run, chronological):\n"]
    for step in steps:
        lines.append(f"- [{step.id}] {step.tool} {step.status.value}: {step.description}")
        if step.output:
            o = step.output[:_STEP_OUT_MAX]
            if len(step.output) > _STEP_OUT_MAX:
                o += "\n  ... [truncated]"
            lines.append(f"  output:\n{o}")
        if step.error_detail:
            fc = f"{step.failure_code}: " if step.failure_code else ""
            lines.append(f"  error: {fc}{step.error_detail}")
    if session_context and session_context.strip():
        s = session_context.strip()
        if len(s) > 2_000:
            s = s[:2_000] + "\n... [truncated session]"
        lines.append(f"\nClient session context (compressed):\n{s}\n")
    text = "\n".join(lines)
    if len(text) > _DIGEST_MAX:
        text = "... [truncated digest]\n" + text[-_DIGEST_MAX:]
    return text


class GoalCheckResult(BaseModel):
    goal_satisfied: bool
    reason: str = Field(default="", max_length=2_000)
    planner_brief: str = Field(
        default="",
        max_length=4_000,
        description="If goal_satisfied is false, concrete hints for the next plan.",
    )

    @field_validator("planner_brief", mode="after")
    @classmethod
    def _trim_brief(cls, v: str) -> str:
        s = (v or "").strip()
        if len(s) > 4_000:
            return s[:3_999] + "…"
        return s


class GoalCheckSynthesizer:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        defer_model_check: bool = True,
        model_settings: dict[str, Any] | None = None,
        retries: int = 0,
        goal_check_system_prompt: str | None = None,
        global_system_prompt: str | None = None,
    ) -> None:
        self._provider = provider
        instructions = effective_goal_check_instructions(
            override=goal_check_system_prompt,
            global_prefix=global_system_prompt,
        )
        agent_kwargs: dict = {
            "output_type": GoalCheckResult,
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
        self._agent: Agent[None, GoalCheckResult] = Agent(resolved_model, **agent_kwargs)

    def is_available(self) -> bool:
        return self._provider.is_available()

    def check(
        self,
        task: str,
        steps: list[PlanStep],
        session_context: str | None,
    ) -> GoalCheckResult:
        digest = build_goal_check_digest(task, steps, session_context)
        prompt = f"{digest}\n\nRespond with the structured goal check fields only."
        result = self._agent.run_sync(prompt)
        r = result.output
        if not r.goal_satisfied and not (r.planner_brief or "").strip():
            # Ensure the planner has something to act on.
            return r.model_copy(
                update={"planner_brief": (r.reason or "Re-plan with tools that better match the user task.").strip()[
                    :4_000
                ]}
            )
        return r
