from uni_agent.shared.models import PlanStep, TaskStatus


def test_extended_task_status_values_round_trip() -> None:
    step = PlanStep(
        id="step-1",
        description="blocked",
        status=TaskStatus.BLOCKED,
    )

    dumped = step.model_dump()
    loaded = PlanStep.model_validate(dumped)

    assert loaded.status == TaskStatus.BLOCKED
    assert {TaskStatus.PARTIAL.value, TaskStatus.NEEDS_REVIEW.value, TaskStatus.SKIPPED.value}
