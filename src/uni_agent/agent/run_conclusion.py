from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from uni_agent.agent.llm import LLMProvider, build_planner_model
from uni_agent.shared.models import PlanStep, TaskStatus

_DIGEST_MAX_CHARS = 14_000
_OUTPUT_SNIPPET = 2_500


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
) -> str:
    lines: list[str] = [
        f"Task:\n{task}\n",
        f"Final status: {status.value}\n",
    ]
    if error:
        lines.append(f"Top-level error (if any):\n{error}\n")
    lines.append("Steps (chronological):")
    for step in steps:
        lines.append(
            f"- [{step.id}] {step.tool} {step.status.value}: {step.description}"
        )
        if step.output:
            snip = step.output[:_OUTPUT_SNIPPET]
            if len(step.output) > _OUTPUT_SNIPPET:
                snip += "\n  ... [truncated]"
            lines.append(f"  output:\n{snip}")
        if step.error_detail:
            fc = f"{step.failure_code}: " if step.failure_code else ""
            lines.append(f"  error: {fc}{step.error_detail}")
    if output.strip():
        agg = output.strip()
        if len(agg) > _OUTPUT_SNIPPET:
            agg = agg[:_OUTPUT_SNIPPET] + "\n... [truncated]"
        lines.append(f"\nAggregated tool output:\n{agg}")
    text = "\n".join(lines)
    if len(text) > _DIGEST_MAX_CHARS:
        text = "... [truncated digest]\n" + text[-_DIGEST_MAX_CHARS:]
    return text


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
    ) -> None:
        self._provider = provider
        instructions = (
            "You write a clear execution conclusion for the user who ran a local agent. "
            "Use the same language as the task when it is clearly Chinese or English; otherwise match the task. "
            "Base every claim on the provided log only — do not invent files, numbers, or outcomes. "
            "Say whether the original task goal appears achieved, summarize evidence from outputs, "
            "and briefly explain failures or missing pieces."
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
        digest = build_execution_digest(task, status, steps, output, error)
        prompt = f"Execution log:\n{digest}\n\nWrite the conclusion for the user."
        result = self._agent.run_sync(prompt)
        return result.output.conclusion.strip()
