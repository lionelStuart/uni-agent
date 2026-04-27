from uni_agent.agent.loop_guard import LoopGuard
from uni_agent.agent.working_memory import RunWorkingMemory
from uni_agent.shared.models import PlanStep, TaskStatus


def test_loop_guard_detects_repeated_actions() -> None:
    memory = RunWorkingMemory()
    for idx in range(3):
        memory.record_step(
            PlanStep(
                id=f"r{idx}-step-1",
                description="read",
                tool="file_read",
                arguments={"path": "missing.txt"},
                status=TaskStatus.COMPLETED,
                output="same",
            )
        )

    decision = LoopGuard(repeated_action_threshold=3).check(memory, [])

    assert decision.triggered is False

    decision = LoopGuard(repeated_action_threshold=3).check(
        memory,
        [
            PlanStep(
                id="r3-step-1",
                description="read",
                tool="file_read",
                arguments={"path": "missing.txt"},
                status=TaskStatus.COMPLETED,
                output="same",
            )
        ],
    )

    assert decision.triggered is True
    assert decision.code == "repeated_action"
    assert decision.suggested_action == "fail"


def test_loop_guard_detects_empty_completed_batch() -> None:
    memory = RunWorkingMemory()
    batch = [
        PlanStep(
            id="r1-step-1",
            description="search",
            tool="search_workspace",
            arguments={"query": "not-there"},
            status=TaskStatus.COMPLETED,
            output="",
        )
    ]
    for step in batch:
        memory.record_step(step)

    decision = LoopGuard(repeated_action_threshold=3).check(memory, batch)

    assert decision.triggered is True
    assert decision.code == "no_progress_empty_outputs"
    assert decision.suggested_action == "replan"


def test_loop_guard_allows_search_no_matches_verification() -> None:
    memory = RunWorkingMemory()
    batch = [
        PlanStep(
            id="r1-step-1",
            description="search",
            tool="search_workspace",
            arguments={"query": "not-there"},
            status=TaskStatus.COMPLETED,
            output="",
            verifications=[{"passed": True, "code": "no_matches"}],
        )
    ]
    for step in batch:
        memory.record_step(step)

    decision = LoopGuard(repeated_action_threshold=3).check(memory, batch)

    assert decision.triggered is False
