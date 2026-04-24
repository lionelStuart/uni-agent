from uni_agent.agent.goal_check import build_goal_check_digest
from uni_agent.agent.run_conclusion import build_execution_digest
from uni_agent.shared.models import PlanStep, TaskStatus


def test_goal_check_digest_uses_budgeted_context() -> None:
    steps = [
        PlanStep(
            id="step-1",
            description="fetch",
            tool="http_fetch",
            status=TaskStatus.COMPLETED,
            output=("headline\n" * 500),
        )
    ]

    digest = build_goal_check_digest("今天的新闻热点", steps, "old session\n" * 200)

    assert "User task" in digest
    assert "Client session context" in digest
    assert "truncated" in digest


def test_execution_digest_keeps_status_and_steps() -> None:
    steps = [
        PlanStep(
            id="step-1",
            description="fetch docs",
            tool="http_fetch",
            status=TaskStatus.COMPLETED,
            output=("docs line\n" * 400),
        )
    ]

    digest = build_execution_digest("搜一下 Python 官方文档", TaskStatus.COMPLETED, steps, "done\n" * 200, None)

    assert "Final status: completed" in digest
    assert "Steps (chronological)" in digest
    assert "Aggregated tool output" in digest
