from __future__ import annotations

from uni_agent.agent.executor import Executor
from uni_agent.agent.planner import Planner
from uni_agent.agent.run_conclusion import RunConclusionSynthesizer, fallback_run_conclusion
from uni_agent.observability.task_store import TaskStore
from uni_agent.shared.models import PlanStep, TaskResult, TaskStatus
from uni_agent.skills.matcher import SkillMatcher
from uni_agent.skills.loader import SkillLoader
from uni_agent.tools.registry import ToolRegistry

_PRIOR_CONTEXT_MAX_CHARS = 12_000


def _format_prior_context(steps: list[PlanStep]) -> str:
    parts: list[str] = []
    for step in steps:
        parts.append(f"[{step.id}] {step.tool} {step.status.value}: {step.description}")
        if step.output:
            snippet = step.output[:4_000]
            if len(step.output) > 4_000:
                snippet += "\n  ... [truncated]"
            parts.append(f"  output:\n{snippet}")
        if step.error_detail:
            fc = f"{step.failure_code}: " if step.failure_code else ""
            parts.append(f"  error: {fc}{step.error_detail}")
    text = "\n".join(parts)
    if len(text) > _PRIOR_CONTEXT_MAX_CHARS:
        text = "... [truncated prior log]\n" + text[-_PRIOR_CONTEXT_MAX_CHARS:]
    hint = (
        "Note: do not paste this log into search_workspace `query`; use a short literal search phrase only.\n\n"
    )
    return hint + text


def _prefix_round(round_idx: int, steps: list[PlanStep]) -> list[PlanStep]:
    return [step.model_copy(update={"id": f"r{round_idx}-{step.id}"}) for step in steps]


class Orchestrator:
    def __init__(
        self,
        skill_loader: SkillLoader,
        tool_registry: ToolRegistry,
        planner: Planner,
        task_store: TaskStore,
        max_step_retries: int = 0,
        max_failed_rounds: int = 5,
        conclusion_synthesizer: RunConclusionSynthesizer | None = None,
    ):
        self.skill_loader = skill_loader
        self.tool_registry = tool_registry
        self.skill_matcher = SkillMatcher()
        self.planner = planner
        self.executor = Executor(tool_registry, max_step_retries=max_step_retries)
        self.task_store = task_store
        self.max_failed_rounds = max(1, max_failed_rounds)
        self._conclusion_synthesizer = conclusion_synthesizer

    def run(self, task: str, plan_override: list[PlanStep] | None = None) -> TaskResult:
        run_id = self.task_store.next_run_id()
        skills = self.skill_loader.load_all()
        matched_skills = self.skill_matcher.match(task, skills)
        selected_skills = matched_skills[:2]
        available_tools = self.tool_registry.list_tools()

        if plan_override is not None:
            executed_plan = _prefix_round(1, self.executor.execute(plan_override))
            success = bool(executed_plan) and all(s.status == TaskStatus.COMPLETED for s in executed_plan)
            failed_rounds = 0 if success else 1
        else:
            accumulated: list[PlanStep] = []
            failed_rounds = 0
            round_idx = 0

            while True:
                prior = _format_prior_context(accumulated) if accumulated else None
                plan = self.planner.create_plan(
                    task,
                    selected_skills,
                    available_tools,
                    prior_context=prior,
                )

                if not plan:
                    failed_rounds += 1
                    if failed_rounds >= self.max_failed_rounds:
                        break
                    continue

                round_idx += 1
                batch = _prefix_round(round_idx, self.executor.execute(plan))
                accumulated.extend(batch)

                if all(step.status == TaskStatus.COMPLETED for step in batch):
                    break

                failed_rounds += 1
                if failed_rounds >= self.max_failed_rounds:
                    break

            executed_plan = accumulated
            success = bool(executed_plan) and all(s.status == TaskStatus.COMPLETED for s in executed_plan)

        failed_step = None
        if not success:
            failed_step = next(
                (step for step in reversed(executed_plan) if step.status == TaskStatus.FAILED),
                None,
            )

        output = "\n\n".join(step.output for step in executed_plan if step.output)
        error: str | None = (failed_step.error_detail or failed_step.output) if failed_step else None
        if not success and error is None:
            error = (
                f"Stopped after {failed_rounds} failed replan round(s) "
                f"(limit {self.max_failed_rounds}) without completing the task."
            )

        final_status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
        conclusion = fallback_run_conclusion(task, final_status, executed_plan, output, error)
        if self._conclusion_synthesizer is not None and self._conclusion_synthesizer.is_available():
            try:
                conclusion = self._conclusion_synthesizer.synthesize(
                    task, final_status, executed_plan, output, error
                )
            except Exception:
                pass

        result = TaskResult(
            run_id=run_id,
            task=task,
            status=final_status,
            selected_skills=[skill.name for skill in selected_skills],
            available_tools=[tool.name for tool in available_tools],
            plan=executed_plan,
            output=output,
            error=error,
            orchestrator_failed_rounds=failed_rounds,
            conclusion=conclusion,
        )
        self.task_store.save(result)
        return result

    def replay(self, run_id: str) -> TaskResult:
        return self.task_store.load(run_id).result
