from __future__ import annotations

from dataclasses import dataclass


def _clamp(value: int, *, low: int, high: int) -> int:
    return max(low, min(high, value))


@dataclass(frozen=True, slots=True)
class ContextBudgets:
    context_window_tokens: int
    session_context_max_tokens: int
    prior_context_max_tokens: int
    prior_step_output_max_tokens: int
    goal_check_max_tokens: int
    goal_check_step_output_max_tokens: int
    goal_check_session_context_max_tokens: int
    conclusion_max_tokens: int
    conclusion_step_output_max_tokens: int
    conclusion_aggregate_output_max_tokens: int


def derive_context_budgets(context_window_tokens: int) -> ContextBudgets:
    window = max(8_192, int(context_window_tokens))
    session = _clamp(window // 64, low=2_048, high=8_192)
    prior = _clamp(window // 64, low=2_048, high=8_192)
    goal = _clamp(window // 64, low=2_048, high=8_192)
    conclusion = _clamp(window // 48, low=3_072, high=12_288)
    return ContextBudgets(
        context_window_tokens=window,
        session_context_max_tokens=session,
        prior_context_max_tokens=prior,
        prior_step_output_max_tokens=_clamp(prior // 4, low=400, high=1_600),
        goal_check_max_tokens=goal,
        goal_check_step_output_max_tokens=_clamp(goal // 5, low=320, high=1_024),
        goal_check_session_context_max_tokens=_clamp(goal // 8, low=256, high=1_024),
        conclusion_max_tokens=conclusion,
        conclusion_step_output_max_tokens=_clamp(conclusion // 8, low=320, high=1_024),
        conclusion_aggregate_output_max_tokens=_clamp(conclusion // 7, low=384, high=1_536),
    )
