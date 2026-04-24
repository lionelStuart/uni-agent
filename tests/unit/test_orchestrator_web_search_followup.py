from pathlib import Path

from uni_agent.agent.orchestrator import Orchestrator
from uni_agent.agent.planner import Planner
from uni_agent.observability.task_store import TaskStore
from uni_agent.shared.models import PlanStep, SkillSpec, ToolSpec
from uni_agent.skills.loader import SkillLoader
from uni_agent.tools.registry import ToolRegistry


class WebSearchThenFetchPlanner(Planner):
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
        if not prior_context:
            return [
                PlanStep(
                    id="step-1",
                    description="Search the public web.",
                    tool="web_search",
                    arguments={"query": task},
                )
            ]
        if "web_search completed" in prior_context and "http_fetch completed" not in prior_context:
            return [
                PlanStep(
                    id="step-1",
                    description="Fetch top result.",
                    tool="http_fetch",
                    arguments={"url": "https://example.com/news"},
                )
            ]
        return []


class BrokenGoalCheck:
    def is_available(self) -> bool:
        return True

    def check(self, task: str, steps, session_context: str | None):
        raise RuntimeError("Connection error.")


def test_orchestrator_continues_web_followup_when_goal_check_errors(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools(include_delegate_task=False)
    registry.attach_handler(
        "web_search",
        lambda arguments: '{"results":[{"title":"Example","url":"https://example.com/news","snippet":"Top story"}]}',
    )
    registry.attach_handler("http_fetch", lambda arguments: "Title: Example News\nText: Headline details")

    orchestrator = Orchestrator(
        skill_loader=SkillLoader(Path("skills")),
        tool_registry=registry,
        planner=WebSearchThenFetchPlanner(),
        task_store=TaskStore(tmp_path / "runs"),
        max_failed_rounds=3,
        goal_check=BrokenGoalCheck(),
    )

    result = orchestrator.run("查看今天的热点新闻")

    assert result.status.value == "completed"
    assert [step.tool for step in result.plan] == ["web_search", "http_fetch"]
    assert "Headline details" in (result.output or "")

