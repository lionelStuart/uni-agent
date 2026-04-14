from uni_agent.agent.executor import Executor
from uni_agent.shared.models import PlanStep, TaskStatus
from uni_agent.tools.registry import ToolRegistry


def test_executor_records_error_attribution() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()

    def boom(_: dict) -> str:
        raise ValueError("nope")

    registry.attach_handler("shell_exec", boom)
    executor = Executor(registry)
    plan = [
        PlanStep(
            id="step-1",
            description="run",
            tool="shell_exec",
            arguments={"command": ["ls"]},
        )
    ]

    executed = executor.execute(plan)

    assert executed[0].status == TaskStatus.FAILED
    assert executed[0].error_type == "ValueError"
    assert executed[0].error_detail == "nope"
    assert executed[0].failure_code == "invalid_arguments"


def test_executor_retries_until_success() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()

    attempts = {"count": 0}

    def flaky(_: dict) -> str:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise ValueError("retry")
        return "ok"

    registry.attach_handler("shell_exec", flaky)
    executor = Executor(registry, max_step_retries=2)
    plan = [
        PlanStep(
            id="step-1",
            description="run",
            tool="shell_exec",
            arguments={"command": ["ls"]},
        )
    ]

    executed = executor.execute(plan)

    assert executed[0].status == TaskStatus.COMPLETED
    assert executed[0].output == "ok"
    assert attempts["count"] == 2
