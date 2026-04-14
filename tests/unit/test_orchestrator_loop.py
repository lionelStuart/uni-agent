from pathlib import Path

from uni_agent.agent.orchestrator import Orchestrator
from uni_agent.agent.planner import Planner
from uni_agent.observability.task_store import TaskStore
from uni_agent.sandbox.runner import LocalSandbox
from uni_agent.shared.models import PlanStep, SkillSpec, ToolSpec
from uni_agent.skills.loader import SkillLoader
from uni_agent.tools.builtins import register_builtin_handlers
from uni_agent.tools.registry import ToolRegistry


def _runtime(tmp_path: Path, planner: Planner, *, max_failed_rounds: int = 5) -> Orchestrator:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    register_builtin_handlers(registry, Path(".").resolve(), LocalSandbox(Path(".").resolve()))
    return Orchestrator(
        skill_loader=SkillLoader(Path("skills")),
        tool_registry=registry,
        planner=planner,
        task_store=TaskStore(tmp_path / "runs"),
        max_failed_rounds=max_failed_rounds,
    )


class FailThenSucceedPlanner(Planner):
    def __init__(self) -> None:
        self.calls = 0

    def create_plan(
        self,
        task: str,
        selected_skills: list[SkillSpec],
        available_tools: list[ToolSpec],
        *,
        prior_context: str | None = None,
    ) -> list[PlanStep]:
        self.calls += 1
        if self.calls < 3:
            return [
                PlanStep(
                    id="step-1",
                    description="disallowed",
                    tool="shell_exec",
                    arguments={"command": ["rm", "-rf", "/"]},
                )
            ]
        return [
            PlanStep(
                id="step-1",
                description="ok",
                tool="shell_exec",
                arguments={"command": ["pwd"]},
            )
        ]


def test_orchestrator_replans_last_round_ok_but_overall_failed_if_earlier_steps_failed(
    tmp_path: Path,
) -> None:
    """A later successful batch does not mask FAILED steps left in the accumulated plan."""
    orchestrator = _runtime(tmp_path, FailThenSucceedPlanner(), max_failed_rounds=5)

    result = orchestrator.run("loop test")

    assert result.status.value == "failed"
    assert result.orchestrator_failed_rounds == 2
    assert any(step.tool == "shell_exec" and step.status.value == "failed" for step in result.plan)
    assert any(step.tool == "shell_exec" and step.status.value == "completed" for step in result.plan)


class AlwaysFailPlanner(Planner):
    def create_plan(
        self,
        task: str,
        selected_skills: list[SkillSpec],
        available_tools: list[ToolSpec],
        *,
        prior_context: str | None = None,
    ) -> list[PlanStep]:
        return [
            PlanStep(
                id="step-1",
                description="always bad",
                tool="shell_exec",
                arguments={"command": ["rm"]},
            )
        ]


def test_orchestrator_stops_after_max_failed_rounds(tmp_path: Path) -> None:
    orchestrator = _runtime(tmp_path, AlwaysFailPlanner(), max_failed_rounds=3)

    result = orchestrator.run("never works")

    assert result.status.value == "failed"
    assert result.orchestrator_failed_rounds == 3
    assert len(result.plan) == 3
