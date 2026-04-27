from __future__ import annotations

from collections.abc import Callable

from uni_agent.sandbox.runner import SandboxError
from uni_agent.shared.models import PlanStep, TaskStatus
from uni_agent.tools.registry import ToolRegistry


class Executor:
    def __init__(self, tool_registry: ToolRegistry, max_step_retries: int = 0):
        self.tool_registry = tool_registry
        self.max_step_retries = max(0, max_step_retries)

    def execute(
        self,
        plan: list[PlanStep],
        *,
        on_step_complete: Callable[[PlanStep], None] | None = None,
    ) -> list[PlanStep]:
        executed_steps: list[PlanStep] = []
        for step in plan:
            for attempt in range(self.max_step_retries + 1):
                running_step = step.model_copy(update={"status": TaskStatus.RUNNING})
                try:
                    result = self.tool_registry.execute_result(running_step.tool, running_step.arguments)
                except Exception as exc:
                    failure_code = _classify_failure(exc)
                    failed_step = running_step.model_copy(
                        update={
                            "status": TaskStatus.FAILED,
                            "output": str(exc),
                            "error_type": type(exc).__name__,
                            "error_detail": str(exc),
                            "failure_code": failure_code,
                        }
                    )
                    if attempt >= self.max_step_retries:
                        executed_steps.append(failed_step)
                        if on_step_complete is not None:
                            on_step_complete(failed_step)
                        return executed_steps
                    continue

                done = running_step.model_copy(
                    update={
                        "status": TaskStatus.COMPLETED,
                        "output": result.text,
                        "tool_result": result.model_dump(),
                    }
                )
                executed_steps.append(done)
                if on_step_complete is not None:
                    on_step_complete(done)
                break

        return executed_steps


def _classify_failure(exc: BaseException) -> str:
    if isinstance(exc, SandboxError):
        return "sandbox_error"
    if isinstance(exc, KeyError):
        return "unknown_tool"
    if isinstance(exc, ValueError):
        return "invalid_arguments"
    return "tool_execution_error"
