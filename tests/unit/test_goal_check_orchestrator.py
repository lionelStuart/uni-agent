"""Post-batch goal check: re-plan when LLM reports task not yet satisfied."""

from __future__ import annotations

from pathlib import Path

from uni_agent.agent.goal_check import GoalCheckResult
from uni_agent.agent.orchestrator import Orchestrator
from uni_agent.agent.planner import Planner
from uni_agent.observability.task_store import TaskStore
from uni_agent.sandbox.runner import LocalSandbox
from uni_agent.shared.models import PlanStep, SkillSpec, ToolSpec
from uni_agent.skills.loader import SkillLoader
from uni_agent.tools.builtins import register_builtin_handlers
from uni_agent.tools.registry import ToolRegistry


def _echo_step(sid: str, text: str) -> PlanStep:
    return PlanStep(
        id=sid,
        description="echo",
        tool="shell_exec",
        arguments={"command": ["echo", text]},
    )


class ReplanTwicePlanner(Planner):
    """First plan: one echo. After outcome_feedback, second plan: another echo."""

    def __init__(self) -> None:
        self.calls = 0

    def create_plan(
        self,
        task: str,
        selected_skills: list[SkillSpec],
        available_tools: list[ToolSpec],
        *,
        prior_context: str | None = None,
        session_context: str | None = None,
        outcome_feedback: str | None = None,
    ) -> list[PlanStep]:
        self.calls += 1
        if self.calls == 1:
            return [_echo_step("step-1", "a")]
        return [_echo_step("step-1", "b")]


class FakeGoalCheck:
    def __init__(self) -> None:
        self.check_calls = 0

    def is_available(self) -> bool:
        return True

    def check(self, task: str, steps, session_context: str | None) -> GoalCheckResult:
        self.check_calls += 1
        if self.check_calls == 1:
            return GoalCheckResult(
                goal_satisfied=False,
                reason="Need a second step.",
                planner_brief="Run another echo with different content.",
            )
        return GoalCheckResult(goal_satisfied=True, reason="Done.", planner_brief="")


def _runtime(
    tmp_path: Path,
    planner: Planner,
    *,
    max_replan: int = 3,
) -> Orchestrator:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    register_builtin_handlers(registry, Path(".").resolve(), LocalSandbox(Path(".").resolve()))
    return Orchestrator(
        skill_loader=SkillLoader(Path("skills")),
        tool_registry=registry,
        planner=planner,
        task_store=TaskStore(tmp_path / "runs"),
        max_failed_rounds=5,
        goal_check=FakeGoalCheck(),
        plan_goal_check_max_replan_rounds=max_replan,
    )


def test_goal_check_triggers_replan_then_succeeds(tmp_path: Path) -> None:
    p = ReplanTwicePlanner()
    orchestrator = _runtime(tmp_path, p, max_replan=3)

    result = orchestrator.run("say hi")

    assert result.status.value == "completed"
    assert p.calls == 2
    assert result.goal_check_mismatch_rounds == 1
    assert len(result.plan) == 2
    assert all(s.status.value == "completed" for s in result.plan)


class AlwaysUnsatisfiedGoalCheck:
    def is_available(self) -> bool:
        return True

    def check(self, task: str, steps, session_context: str | None) -> GoalCheckResult:
        return GoalCheckResult(
            goal_satisfied=False,
            reason="never",
            planner_brief="try again",
        )


class SingleEchoPlanner(Planner):
    def create_plan(
        self,
        task: str,
        selected_skills: list[SkillSpec],
        available_tools: list[ToolSpec],
        *,
        prior_context: str | None = None,
        session_context: str | None = None,
        outcome_feedback: str | None = None,
    ) -> list[PlanStep]:
        return [_echo_step("step-1", "x")]


def test_goal_check_exhausted_marks_failed(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    register_builtin_handlers(registry, Path(".").resolve(), LocalSandbox(Path(".").resolve()))
    orchestrator = Orchestrator(
        skill_loader=SkillLoader(Path("skills")),
        tool_registry=registry,
        planner=SingleEchoPlanner(),
        task_store=TaskStore(tmp_path / "runs"),
        max_failed_rounds=5,
        goal_check=AlwaysUnsatisfiedGoalCheck(),
        plan_goal_check_max_replan_rounds=1,
    )

    result = orchestrator.run("task")

    assert result.status.value == "failed"
    assert result.error and "Goal check" in result.error
    assert result.goal_check_mismatch_rounds == 2
