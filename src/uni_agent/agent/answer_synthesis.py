from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from uni_agent.agent.llm import LLMProvider, build_planner_model
from uni_agent.agent.run_conclusion import build_execution_digest
from uni_agent.agent.system_prompts import effective_answer_instructions
from uni_agent.context.budgeting import ContextBudgets, derive_context_budgets
from uni_agent.shared.models import PlanStep, TaskStatus

_DEFAULT_BUDGETS = derive_context_budgets(256_000)


class _AnswerSchema(BaseModel):
    answer: str = Field(description="Final answer to the user's task, grounded in the execution log.")


def fallback_run_answer(
    task: str,
    status: TaskStatus,
    steps: list[PlanStep],
    output: str,
    error: str | None,
) -> str:
    if status == TaskStatus.FAILED:
        return error or output or "Task failed without a detailed error."
    if not output.strip():
        return "Task completed, but no tool output was produced."
    return output.strip()


class RunAnswerSynthesizer:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        defer_model_check: bool = True,
        model_settings: dict[str, Any] | None = None,
        retries: int = 0,
        answer_system_prompt: str | None = None,
        global_system_prompt: str | None = None,
        context_budgets: ContextBudgets | None = None,
    ) -> None:
        self._provider = provider
        self._context_budgets = context_budgets or _DEFAULT_BUDGETS
        instructions = effective_answer_instructions(
            override=answer_system_prompt,
            global_prefix=global_system_prompt,
        )
        kwargs: dict[str, Any] = {
            "output_type": _AnswerSchema,
            "instructions": instructions,
            "defer_model_check": defer_model_check,
            "retries": retries,
        }
        if model_settings:
            kwargs["model_settings"] = model_settings
        resolved_model = build_planner_model(
            provider.model_id,
            openai_base_url=getattr(provider, "openai_base_url", None),
            openai_api_key=getattr(provider, "openai_api_key", None),
        )
        self._agent: Agent[None, _AnswerSchema] = Agent(resolved_model, **kwargs)

    def is_available(self) -> bool:
        return self._provider.is_available()

    def synthesize(
        self,
        task: str,
        status: TaskStatus,
        steps: list[PlanStep],
        output: str,
        error: str | None,
    ) -> str:
        digest = build_execution_digest(
            task,
            status,
            steps,
            output,
            error,
            max_tokens=self._context_budgets.conclusion_max_tokens,
            step_output_max_tokens=self._context_budgets.conclusion_step_output_max_tokens,
            aggregate_output_max_tokens=self._context_budgets.conclusion_aggregate_output_max_tokens,
        )
        result = self._agent.run_sync(f"Execution log:\n{digest}\n\nWrite the final answer for the user.")
        return result.output.answer.strip()
