from __future__ import annotations

from uni_agent.shared.models import PlanStep, TaskResult, TaskStatus
from uni_agent.skills.matcher import SkillMatcher
from uni_agent.skills.loader import SkillLoader
from uni_agent.tools.registry import ToolRegistry


class Orchestrator:
    def __init__(self, skill_loader: SkillLoader, tool_registry: ToolRegistry):
        self.skill_loader = skill_loader
        self.tool_registry = tool_registry
        self.skill_matcher = SkillMatcher()

    def run(self, task: str) -> TaskResult:
        skills = self.skill_loader.load_all()
        matched_skills = self.skill_matcher.match(task, skills)
        selected_skills = matched_skills[:2]
        plan = [
            PlanStep(
                id="step-1",
                description="Load matching skills and available tools for the task.",
                status=TaskStatus.COMPLETED,
            ),
            PlanStep(
                id="step-2",
                description="Prepare planner and executor context for the requested task.",
                skill=selected_skills[0].name if selected_skills else None,
                status=TaskStatus.COMPLETED,
            ),
        ]
        summary = "Skeleton runtime only. Model planning and tool execution are not implemented yet."
        return TaskResult(
            task=task,
            status=TaskStatus.COMPLETED,
            selected_skills=[skill.name for skill in selected_skills],
            available_tools=self.tool_registry.names(),
            plan=plan,
            output=summary,
        )

