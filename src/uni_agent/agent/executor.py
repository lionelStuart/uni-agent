from __future__ import annotations

from uni_agent.shared.models import PlanStep, TaskStatus
from uni_agent.tools.registry import ToolRegistry


class Executor:
    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry

    def execute(self, plan: list[PlanStep]) -> list[PlanStep]:
        executed_steps: list[PlanStep] = []
        for step in plan:
            running_step = step.model_copy(update={"status": TaskStatus.RUNNING})
            try:
                result = self.tool_registry.execute(running_step.tool, running_step.arguments)
            except Exception as exc:
                executed_steps.append(
                    running_step.model_copy(
                        update={
                            "status": TaskStatus.FAILED,
                            "output": str(exc),
                        }
                    )
                )
                break

            executed_steps.append(
                running_step.model_copy(
                    update={
                        "status": TaskStatus.COMPLETED,
                        "output": result,
                    }
                )
            )
        return executed_steps
