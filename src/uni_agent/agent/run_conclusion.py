from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from uni_agent.agent.llm import LLMProvider, build_planner_model
from uni_agent.agent.system_prompts import effective_conclusion_instructions
from uni_agent.context.budgeting import ContextBudgets, derive_context_budgets
from uni_agent.context.token_budget import ContextBlock, fit_blocks_to_budget, render_blocks, truncate_to_tokens
from uni_agent.shared.models import PlanStep, TaskStatus

_DEFAULT_BUDGETS = derive_context_budgets(256_000)
_CONCLUSION_MAX_TOKENS = _DEFAULT_BUDGETS.conclusion_max_tokens
_STEP_OUTPUT_MAX_TOKENS = _DEFAULT_BUDGETS.conclusion_step_output_max_tokens
_AGG_OUTPUT_MAX_TOKENS = _DEFAULT_BUDGETS.conclusion_aggregate_output_max_tokens


class _ConclusionSchema(BaseModel):
    conclusion: str = Field(
        description="2–8 short sentences: whether the task goal was met, what was done, key outputs, and what failed."
    )


def build_execution_digest(
    task: str,
    status: TaskStatus,
    steps: list[PlanStep],
    output: str,
    error: str | None,
    *,
    max_tokens: int = _CONCLUSION_MAX_TOKENS,
    step_output_max_tokens: int = _STEP_OUTPUT_MAX_TOKENS,
    aggregate_output_max_tokens: int = _AGG_OUTPUT_MAX_TOKENS,
) -> str:
    blocks: list[ContextBlock] = [
        ContextBlock(kind="task", text=f"Task:\n{task}", priority=100, pinned=True),
        ContextBlock(kind="status", text=f"Final status: {status.value}", priority=100, pinned=True),
    ]
    if error:
        blocks.append(ContextBlock(kind="error", text=f"Top-level error (if any):\n{error}", priority=95))
    step_lines = ["Steps (chronological):"]
    for step in steps:
        step_lines.append(
            f"- [{step.id}] {step.tool} {step.status.value}: {step.description}"
        )
        if step.output:
            snip = truncate_to_tokens(step.output, step_output_max_tokens)
            step_lines.append(f"  output:\n{snip}")
        if step.error_detail:
            fc = f"{step.failure_code}: " if step.failure_code else ""
            step_lines.append(f"  error: {fc}{step.error_detail}")
    blocks.append(ContextBlock(kind="prior_step", text="\n".join(step_lines), priority=75))
    if output.strip():
        agg = truncate_to_tokens(output.strip(), aggregate_output_max_tokens)
        blocks.append(ContextBlock(kind="aggregate", text=f"Aggregated tool output:\n{agg}", priority=60))
    return render_blocks(fit_blocks_to_budget(blocks, max_tokens), separator="\n\n")


def fallback_run_conclusion(
    task: str,
    status: TaskStatus,
    plan: list[PlanStep],
    output: str,
    error: str | None,
) -> str:
    """Deterministic summary when LLM synthesis is off or fails."""
    ok = status == TaskStatus.COMPLETED
    n = len(plan)
    failed = [s for s in plan if s.status == TaskStatus.FAILED]
    parts: list[str] = []
    if ok and not failed:
        parts.append("执行已完成：所有步骤均成功。")
    elif ok and failed:
        parts.append("最终状态为已完成，但执行记录中仍包含失败的步骤，请结合输出判断是否达到目标。")
    else:
        parts.append("执行未完全成功。")
    parts.append(f"共 {n} 个步骤，其中 {len(failed)} 个失败。")
    if failed:
        last = failed[-1]
        parts.append(f"最后一处失败：{last.id} ({last.tool}) — {last.error_detail or last.output or 'unknown'}")
    if output.strip():
        head = output.strip().splitlines()[0][:200]
        parts.append(f"合并输出摘要（首行）：{head}")
    elif not failed:
        parts.append("工具合并输出为空。")
    if error and (not failed or error not in (failed[-1].error_detail or "")):
        parts.append(f"错误信息：{error[:500]}")
    return "\n".join(parts)


class RunConclusionSynthesizer:
    """Final LLM round: turn execution digest into a user-facing conclusion."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        defer_model_check: bool = True,
        model_settings: dict[str, Any] | None = None,
        retries: int = 0,
        conclusion_system_prompt: str | None = None,
        global_system_prompt: str | None = None,
        context_budgets: ContextBudgets | None = None,
    ) -> None:
        self._provider = provider
        self._context_budgets = context_budgets or _DEFAULT_BUDGETS
        instructions = effective_conclusion_instructions(
            override=conclusion_system_prompt,
            global_prefix=global_system_prompt,
        )
        agent_kwargs: dict = {
            "output_type": _ConclusionSchema,
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
        self._agent: Agent[None, _ConclusionSchema] = Agent(resolved_model, **agent_kwargs)

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
        prompt = f"Execution log:\n{digest}\n\nWrite the conclusion for the user."
        result = self._agent.run_sync(prompt)
        return result.output.conclusion.strip()
