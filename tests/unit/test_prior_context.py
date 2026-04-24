from uni_agent.agent.orchestrator import _format_prior_context
from uni_agent.shared.models import PlanStep, TaskStatus


def test_prior_context_rolls_older_steps_and_keeps_recent_details() -> None:
    steps = [
        PlanStep(
            id=f"r{i}-step-1",
            description=f"step {i}",
            tool="http_fetch",
            status=TaskStatus.COMPLETED if i % 2 else TaskStatus.FAILED,
            output=f"headline {i}\nbody {i}",
            error_detail=f"error {i}" if i % 2 == 0 else None,
        )
        for i in range(1, 10)
    ]

    text = _format_prior_context(steps)

    assert "Older rounds summary" in text
    assert "[r9-step-1]" in text
    assert "search_workspace `query`" in text


def test_prior_context_dedupes_repeated_older_outputs() -> None:
    steps = [
        PlanStep(
            id=f"r{i}-step-1",
            description="step",
            tool="web_search",
            status=TaskStatus.COMPLETED,
            output="same output line\nsame output line",
        )
        for i in range(1, 9)
    ]

    text = _format_prior_context(steps)

    assert text.count("same output line") < len(steps)
