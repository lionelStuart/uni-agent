from uni_agent.agent.answer_synthesis import fallback_run_answer
from uni_agent.agent.run_conclusion import build_execution_digest, fallback_run_conclusion
from uni_agent.shared.models import PlanStep, TaskStatus


def test_fallback_conclusion_reports_failures() -> None:
    steps = [
        PlanStep(
            id="s1",
            description="a",
            tool="shell_exec",
            status=TaskStatus.FAILED,
            output="boom",
            error_detail="boom",
            failure_code="sandbox_error",
        )
    ]
    text = fallback_run_conclusion("task", TaskStatus.FAILED, steps, "", "boom")
    assert "失败" in text
    assert "s1" in text


def test_build_execution_digest_includes_task_and_steps() -> None:
    steps = [
        PlanStep(id="s1", description="read", tool="file_read", status=TaskStatus.COMPLETED, output="ok")
    ]
    digest = build_execution_digest("hello", TaskStatus.COMPLETED, steps, "ok", None)
    assert "hello" in digest
    assert "s1" in digest
    assert "file_read" in digest


def test_fallback_answer_returns_output_for_success() -> None:
    assert fallback_run_answer("read", TaskStatus.COMPLETED, [], "hello", None) == "hello"


def test_fallback_answer_returns_error_for_failure() -> None:
    assert fallback_run_answer("read", TaskStatus.FAILED, [], "", "missing") == "missing"
