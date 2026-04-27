from uni_agent.agent.working_memory import RunWorkingMemory
from uni_agent.shared.models import PlanStep, TaskStatus


def test_working_memory_records_actions_failures_and_artifacts() -> None:
    memory = RunWorkingMemory()

    memory.record_step(
        PlanStep(
            id="r1-step-1",
            description="write",
            tool="file_write",
            arguments={"path": "notes.txt", "content": "hello"},
            status=TaskStatus.COMPLETED,
            output="Wrote notes.txt",
        )
    )
    memory.record_step(
        PlanStep(
            id="r1-step-2",
            description="bad",
            tool="shell_exec",
            arguments={"command": ["rm"]},
            status=TaskStatus.FAILED,
            error_type="SandboxError",
            error_detail="not allowed",
            failure_code="sandbox_error",
        )
    )

    assert [a.step_id for a in memory.actions_attempted] == ["r1-step-1", "r1-step-2"]
    assert memory.artifacts_created == ["notes.txt"]
    assert memory.recent_failures[0].failure_code == "sandbox_error"


def test_working_memory_digest_is_compact_and_actionable() -> None:
    memory = RunWorkingMemory()
    memory.record_step(
        PlanStep(
            id="r1-step-1",
            description="read",
            tool="file_read",
            arguments={"path": "README.md"},
            status=TaskStatus.COMPLETED,
            output="line 1\nline 2",
        )
    )

    digest = memory.render_digest()

    assert "Working memory" in digest
    assert "r1-step-1 file_read completed" in digest
    assert "README.md" in digest
