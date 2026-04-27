from uni_agent.agent.run_stats import build_run_stats
from uni_agent.shared.models import PlanStep, TaskStatus


def test_build_run_stats_counts_tools_failures_and_verifications() -> None:
    stats = build_run_stats(
        [
            PlanStep(
                id="s1",
                description="read",
                tool="file_read",
                status=TaskStatus.COMPLETED,
                verifications=[{"passed": True, "code": "ok"}],
            ),
            PlanStep(
                id="s2",
                description="bad",
                tool="shell_exec",
                status=TaskStatus.FAILED,
                failure_code="sandbox_error",
                verifications=[{"passed": False, "code": "sandbox_error"}],
            ),
        ],
        goal_check_mismatch_rounds=1,
        loop_guard_events=[{"code": "repeated_action"}],
    )

    assert stats["steps_total"] == 2
    assert stats["tool_counts"]["file_read"] == 1
    assert stats["failure_counts"]["sandbox_error"] == 1
    assert stats["verification_failure_counts"]["sandbox_error"] == 1
    assert stats["goal_check_mismatch_rounds"] == 1
    assert stats["loop_guard_counts"]["repeated_action"] == 1
