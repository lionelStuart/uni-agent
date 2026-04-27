from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from uni_agent.agent.llm import LLMProvider, build_planner_model
from uni_agent.context.token_budget import truncate_to_tokens
from uni_agent.evals.models import DimensionScore, EvalCase
from uni_agent.shared.models import TaskResult


class LLMJudgeOutput(BaseModel):
    score: float = Field(ge=0, le=100)
    passed: bool
    reason: str = Field(default="", max_length=1200)


class EvalLLMJudge:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        model_settings: dict[str, Any] | None = None,
        retries: int = 0,
    ) -> None:
        self._provider = provider
        resolved_model = build_planner_model(
            provider.model_id,
            openai_base_url=getattr(provider, "openai_base_url", None),
            openai_api_key=getattr(provider, "openai_api_key", None),
        )
        kwargs: dict[str, Any] = {
            "output_type": LLMJudgeOutput,
            "instructions": (
                "You are evaluating an autonomous agent run. Score whether the final result satisfies the user task. "
                "Use the provided assertions and execution trace. Penalize missing required evidence, unsafe or irrelevant tool use, "
                "and answers that appear successful but do not actually satisfy the task. Return structured fields only."
            ),
            "defer_model_check": True,
            "retries": retries,
        }
        if model_settings:
            kwargs["model_settings"] = model_settings
        self._agent: Agent[None, LLMJudgeOutput] = Agent(resolved_model, **kwargs)

    def is_available(self) -> bool:
        return self._provider.is_available()

    def judge(self, case: EvalCase, result: TaskResult) -> DimensionScore:
        if not self.is_available():
            return DimensionScore(
                score=0.0,
                passed=False,
                reasons=["LLM judge unavailable: no configured model credentials."],
            )
        prompt = _build_judge_prompt(case, result)
        try:
            judged = self._agent.run_sync(prompt).output
        except Exception as exc:  # noqa: BLE001 - eval should surface judge failures as score evidence.
            return DimensionScore(
                score=0.0,
                passed=False,
                reasons=[f"LLM judge failed: {exc}"],
            )
        reason = judged.reason.strip()
        return DimensionScore(
            score=round(float(judged.score), 2),
            passed=bool(judged.passed),
            reasons=[] if judged.passed else ([reason] if reason else ["LLM judge marked the run as failed."]),
        )


def _build_judge_prompt(case: EvalCase, result: TaskResult) -> str:
    steps = []
    for step in result.plan:
        out = truncate_to_tokens(step.output or "", 500)
        steps.append(
            {
                "id": step.id,
                "tool": step.tool,
                "status": step.status.value,
                "description": step.description,
                "arguments": step.arguments,
                "output": out,
                "error": step.error_detail,
            }
        )
    answer = truncate_to_tokens(result.answer or "", 1200)
    output = truncate_to_tokens(result.output or "", 1200)
    return (
        f"Eval case id: {case.id}\n"
        f"Task: {case.task}\n"
        f"Description: {case.description}\n"
        f"Deterministic assertions: {case.assertions.model_dump()}\n\n"
        f"Final status: {result.status.value}\n"
        f"Final answer:\n{answer or '(none)'}\n\n"
        f"Final output:\n{output}\n\n"
        f"Tool steps:\n{steps}\n\n"
        "Return score 0-100, passed boolean, and a concise reason."
    )
