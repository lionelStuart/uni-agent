from uni_agent.agent.verifier import StepVerifier
from uni_agent.agent.working_memory import RunWorkingMemory
from uni_agent.shared.models import PlanStep, TaskStatus


def test_step_verifier_flags_empty_file_read() -> None:
    result = StepVerifier().verify_step(
        PlanStep(
            id="step-1",
            description="read",
            tool="file_read",
            status=TaskStatus.COMPLETED,
            output="",
        ),
        RunWorkingMemory(),
    )

    assert result.passed is False
    assert result.code == "empty_output"


def test_step_verifier_records_file_write_artifact() -> None:
    memory = RunWorkingMemory()
    step = PlanStep(
        id="step-1",
        description="write",
        tool="file_write",
        arguments={"path": "out.txt"},
        status=TaskStatus.COMPLETED,
        output="ok",
    )
    memory.record_step(step)

    result = StepVerifier().verify_step(step, memory)

    assert result.passed is True
    assert result.code == "artifact_recorded"


def test_step_verifier_failed_step_uses_failure_code() -> None:
    result = StepVerifier().verify_step(
        PlanStep(
            id="step-1",
            description="bad",
            tool="shell_exec",
            status=TaskStatus.FAILED,
            failure_code="sandbox_error",
            error_detail="denied",
        ),
        RunWorkingMemory(),
    )

    assert result.passed is False
    assert result.code == "sandbox_error"
