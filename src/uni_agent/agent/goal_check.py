"""LLM step: after a fully **completed** plan batch, decide if the user task is satisfied; if not, feed `planner_brief` into the next `create_plan` as `outcome_feedback`."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent

from uni_agent.agent.llm import LLMProvider, build_planner_model
from uni_agent.agent.system_prompts import effective_goal_check_instructions
from uni_agent.context.budgeting import ContextBudgets, derive_context_budgets
from uni_agent.context.token_budget import ContextBlock, fit_blocks_to_budget, render_blocks, truncate_to_tokens
from uni_agent.shared.models import PlanStep

_DEFAULT_BUDGETS = derive_context_budgets(256_000)
_GOAL_CHECK_MAX_TOKENS = _DEFAULT_BUDGETS.goal_check_max_tokens
_STEP_OUT_MAX_TOKENS = _DEFAULT_BUDGETS.goal_check_step_output_max_tokens
_SESSION_CONTEXT_MAX_TOKENS = _DEFAULT_BUDGETS.goal_check_session_context_max_tokens


def build_goal_check_digest(
    task: str,
    steps: list[PlanStep],
    session_context: str | None,
    *,
    max_tokens: int = _GOAL_CHECK_MAX_TOKENS,
    step_output_max_tokens: int = _STEP_OUT_MAX_TOKENS,
    session_context_max_tokens: int = _SESSION_CONTEXT_MAX_TOKENS,
) -> str:
    """Compact execution log for goal review (only completed steps are expected in typical use)."""
    blocks: list[ContextBlock] = [ContextBlock(kind="task", text=f"User task:\n{task}", priority=100, pinned=True)]
    step_lines: list[str] = ["Tool steps (this run, chronological):"]
    for step in steps:
        step_lines.append(f"- [{step.id}] {step.tool} {step.status.value}: {step.description}")
        if step.output:
            o = truncate_to_tokens(step.output, step_output_max_tokens)
            step_lines.append(f"  output:\n{o}")
        if step.error_detail:
            fc = f"{step.failure_code}: " if step.failure_code else ""
            step_lines.append(f"  error: {fc}{step.error_detail}")
    blocks.append(ContextBlock(kind="prior_step", text="\n".join(step_lines), priority=80))
    if session_context and session_context.strip():
        s = truncate_to_tokens(session_context.strip(), session_context_max_tokens)
        blocks.append(ContextBlock(kind="memory_summary", text=f"Client session context (compressed):\n{s}", priority=50))
    return render_blocks(fit_blocks_to_budget(blocks, max_tokens), separator="\n\n")


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
        context_budgets: ContextBudgets | None = None,
    ) -> None:
        self._provider = provider
        self._context_budgets = context_budgets or _DEFAULT_BUDGETS
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
        digest = build_goal_check_digest(
            task,
            steps,
            session_context,
            max_tokens=self._context_budgets.goal_check_max_tokens,
            step_output_max_tokens=self._context_budgets.goal_check_step_output_max_tokens,
            session_context_max_tokens=self._context_budgets.goal_check_session_context_max_tokens,
        )
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
