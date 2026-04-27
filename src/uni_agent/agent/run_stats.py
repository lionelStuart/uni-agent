from __future__ import annotations

from collections import Counter
from typing import Any

from uni_agent.shared.models import PlanStep, TaskStatus


def build_run_stats(
    steps: list[PlanStep],
    *,
    goal_check_mismatch_rounds: int = 0,
    loop_guard_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    status_counts = Counter(step.status.value for step in steps)
    tool_counts = Counter((step.tool or "<none>") for step in steps)
    failure_counts = Counter(
        (step.failure_code or step.error_type or "unknown_failure")
        for step in steps
        if step.status == TaskStatus.FAILED
    )
    verification_counts: Counter[str] = Counter()
    verification_failures: Counter[str] = Counter()
    for step in steps:
        for raw in step.verifications:
            code = str(raw.get("code") or "unknown")
            verification_counts[code] += 1
            if raw.get("passed") is False:
                verification_failures[code] += 1

    loop_guard_codes = Counter(str(ev.get("code") or "unknown") for ev in (loop_guard_events or []))
    return {
        "steps_total": len(steps),
        "status_counts": dict(status_counts),
        "tool_counts": dict(tool_counts),
        "failure_counts": dict(failure_counts),
        "verification_counts": dict(verification_counts),
        "verification_failure_counts": dict(verification_failures),
        "goal_check_mismatch_rounds": goal_check_mismatch_rounds,
        "loop_guard_counts": dict(loop_guard_codes),
    }
