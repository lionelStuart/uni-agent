from __future__ import annotations

from pydantic import BaseModel, Field

from uni_agent.agent.working_memory import RunWorkingMemory
from uni_agent.shared.models import PlanStep, TaskStatus


class StepVerification(BaseModel):
    passed: bool
    code: str
    reason: str = ""
    hints: list[str] = Field(default_factory=list)


class StepVerifier:
    def verify_step(self, step: PlanStep, memory: RunWorkingMemory) -> StepVerification:
        if step.status == TaskStatus.FAILED:
            return StepVerification(
                passed=False,
                code=step.failure_code or "step_failed",
                reason=step.error_detail or step.output or "Step failed.",
            )
        if step.status != TaskStatus.COMPLETED:
            return StepVerification(passed=False, code="not_completed", reason="Step did not complete.")

        output = (step.output or "").strip()
        if step.tool == "file_read" and not output:
            return StepVerification(
                passed=False,
                code="empty_output",
                reason="file_read completed but returned no content.",
            )
        if step.tool == "search_workspace" and not output:
            return StepVerification(
                passed=True,
                code="no_matches",
                reason="search_workspace completed with no matches.",
                hints=["Use a shorter literal query or inspect likely files directly."],
            )
        if step.tool == "memory_search" and not output:
            return StepVerification(
                passed=True,
                code="no_memory_hits",
                reason="memory_search completed with no visible hits.",
            )
        if step.tool == "file_write":
            path = step.arguments.get("path")
            if isinstance(path, str) and path in memory.artifacts_created:
                return StepVerification(passed=True, code="artifact_recorded", reason=f"Recorded artifact: {path}")
            return StepVerification(
                passed=True,
                code="write_completed",
                reason="file_write completed; artifact path was not recorded.",
            )
        return StepVerification(passed=True, code="ok")
