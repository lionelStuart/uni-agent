from __future__ import annotations

from uni_agent.agent.executor import Executor
from uni_agent.agent.planner import Planner
from uni_agent.observability.task_store import TaskStore
from uni_agent.shared.models import TaskResult, TaskStatus
from uni_agent.skills.matcher import SkillMatcher
from uni_agent.skills.loader import SkillLoader
from uni_agent.tools.registry import ToolRegistry


class Orchestrator:
    def __init__(
        self,
        skill_loader: SkillLoader,
        tool_registry: ToolRegistry,
        planner: Planner,
        task_store: TaskStore,
    ):
        self.skill_loader = skill_loader
        self.tool_registry = tool_registry
        self.skill_matcher = SkillMatcher()
        self.planner = planner
        self.executor = Executor(tool_registry)
        self.task_store = task_store

    def run(self, task: str) -> TaskResult:
        run_id = self.task_store.next_run_id()
        skills = self.skill_loader.load_all()
        matched_skills = self.skill_matcher.match(task, skills)
        selected_skills = matched_skills[:2]
        available_tools = self.tool_registry.list_tools()
        plan = self.planner.create_plan(task, selected_skills, available_tools)
        executed_plan = self.executor.execute(plan)
        failed_step = next((step for step in executed_plan if step.status == TaskStatus.FAILED), None)
        output = "\n\n".join(step.output for step in executed_plan if step.output)
        result = TaskResult(
            run_id=run_id,
            task=task,
            status=TaskStatus.FAILED if failed_step else TaskStatus.COMPLETED,
            selected_skills=[skill.name for skill in selected_skills],
            available_tools=[tool.name for tool in available_tools],
            plan=executed_plan,
            output=output,
            error=failed_step.output if failed_step else None,
        )
        self.task_store.save(result)
        return result

    def replay(self, run_id: str) -> TaskResult:
        return self.task_store.load(run_id).result
