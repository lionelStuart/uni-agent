from __future__ import annotations

import json
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel

from uni_agent.agent.working_memory import RunWorkingMemory
from uni_agent.shared.models import PlanStep, TaskStatus


class LoopGuardDecision(BaseModel):
    triggered: bool = False
    code: str = "ok"
    reason: str = ""
    suggested_action: Literal["continue", "replan", "fail"] = "continue"


class LoopGuard:
    def __init__(self, *, repeated_action_threshold: int = 4, repeated_failure_threshold: int = 4):
        self.repeated_action_threshold = max(2, repeated_action_threshold)
        self.repeated_failure_threshold = max(2, repeated_failure_threshold)

    def check(self, memory: RunWorkingMemory, latest_batch: list[PlanStep]) -> LoopGuardDecision:
        if not latest_batch:
            return LoopGuardDecision()

        recent_actions = memory.actions_attempted[-8:]
        fingerprints = [_action_fingerprint(a.tool, a.arguments) for a in recent_actions]
        counts = Counter(fingerprints)
        repeated = [(fp, count) for fp, count in counts.items() if count >= self.repeated_action_threshold]
        if repeated:
            _, count = max(repeated, key=lambda item: item[1])
            return LoopGuardDecision(
                triggered=True,
                code="repeated_action",
                reason=f"The same tool call was attempted {count} time(s) in the recent window.",
                suggested_action="fail",
            )

        recent_failures = memory.recent_failures[-self.repeated_failure_threshold :]
        if len(recent_failures) >= self.repeated_failure_threshold:
            keys = {(f.tool, f.failure_code, f.error_detail[:160]) for f in recent_failures}
            if len(keys) == 1:
                failure = recent_failures[-1]
                return LoopGuardDecision(
                    triggered=True,
                    code="repeated_failure",
                    reason=(
                        "The latest failures have the same tool, failure code, and error detail: "
                        f"{failure.tool} {failure.failure_code or ''} {failure.error_detail[:180]}"
                    ),
                    suggested_action="fail",
                )

        if all(step.status == TaskStatus.COMPLETED and not (step.output or "").strip() for step in latest_batch):
            acceptable_empty = {"no_matches", "no_memory_hits"}
            if any(
                str(raw.get("code") or "") in acceptable_empty
                for step in latest_batch
                for raw in step.verifications
            ):
                return LoopGuardDecision()
            return LoopGuardDecision(
                triggered=True,
                code="no_progress_empty_outputs",
                reason="The latest batch completed but produced no observable output.",
                suggested_action="replan",
            )

        return LoopGuardDecision()


def _action_fingerprint(tool: str | None, arguments: dict[str, Any]) -> str:
    try:
        args = json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        args = str(arguments)
    return f"{tool or ''}:{args}"
