"""Orchestration loop. Optional ``stream_event`` emits NDJSON-friendly dicts:

- ``run_begin`` — run id, task, selected_skills
- ``round_plan`` — round, steps (id/tool/description); ``source=file_override`` for ``--plan``
- ``plan_empty`` — planner returned no steps
- ``step_finished`` — round, full step model (after each tool)
- ``round_completed`` / ``round_failed`` — batch outcome
- ``conclusion_begin`` / ``conclusion_done`` — final summary text
- ``run_end`` — status, run_id, orchestrator_failed_rounds
- ``goal_check`` (optional) — after a fully successful step batch, LLM may report ``satisfied`` / ``reason`` / ``planner_brief``; on error, may include ``error`` instead
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from uni_agent.agent import run_context
from uni_agent.agent.executor import Executor
from uni_agent.agent.loop_guard import LoopGuard
from uni_agent.agent.planner import Planner
from uni_agent.agent.goal_check import GoalCheckSynthesizer
from uni_agent.agent.run_conclusion import RunConclusionSynthesizer, fallback_run_conclusion
from uni_agent.agent.run_stats import build_run_stats
from uni_agent.agent.verifier import StepVerifier
from uni_agent.agent.working_memory import RunWorkingMemory
from uni_agent.context.budgeting import ContextBudgets, derive_context_budgets
from uni_agent.context.token_budget import ContextBlock, fit_blocks_to_budget, render_blocks
from uni_agent.observability.task_store import TaskStore
from uni_agent.shared.models import PlanStep, TaskResult, TaskStatus
from uni_agent.skills.matcher import SkillMatcher
from uni_agent.skills.loader import SkillLoader
from uni_agent.tools.registry import ToolRegistry

_DEFAULT_BUDGETS = derive_context_budgets(256_000)
_PRIOR_CONTEXT_MAX_TOKENS = _DEFAULT_BUDGETS.prior_context_max_tokens
_PRIOR_STEP_OUTPUT_MAX_TOKENS = _DEFAULT_BUDGETS.prior_step_output_max_tokens
_PRIOR_STEP_ERROR_MAX_TOKENS = 220
_PRIOR_CONTEXT_RECENT_STEPS = 6


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    kept: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        kept.append(normalized)
    return kept


def _summarize_step_output(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return ""
    kept = _dedupe_keep_order(lines[:8])
    return "\n".join(kept)


def _step_to_context_block(step: PlanStep, *, priority: int, step_output_max_tokens: int) -> ContextBlock:
    lines = [f"[{step.id}] {step.tool} {step.status.value}: {step.description}"]
    if step.output:
        snippet = _summarize_step_output(step.output)
        if snippet:
            if step_output_max_tokens > 0:
                from uni_agent.context.token_budget import truncate_to_tokens

                snippet = truncate_to_tokens(snippet, step_output_max_tokens)
            lines.append(f"  output:\n{snippet}")
    if step.error_detail:
        fc = f"{step.failure_code}: " if step.failure_code else ""
        lines.append(f"  error: {fc}{step.error_detail}")
    return ContextBlock(
        kind="prior_step",
        text="\n".join(lines),
        priority=priority,
        metadata={"labels": "recent_step"},
    )


def _format_prior_context(
    steps: list[PlanStep],
    *,
    model_name: str | None = None,
    max_tokens: int = _PRIOR_CONTEXT_MAX_TOKENS,
    step_output_max_tokens: int = _PRIOR_STEP_OUTPUT_MAX_TOKENS,
) -> str:
    hint = ContextBlock(
        kind="system",
        text="Note: do not paste this log into search_workspace `query`; use a short literal search phrase only.",
        priority=100,
        pinned=True,
        metadata={"labels": "system_hint"},
    )
    if not steps:
        return render_blocks([hint], separator="\n\n")

    older = steps[:-_PRIOR_CONTEXT_RECENT_STEPS]
    recent = steps[-_PRIOR_CONTEXT_RECENT_STEPS:]
    blocks: list[ContextBlock] = [hint]
    if older:
        failed_tools_raw = [
            f"{step.tool}: {(step.error_detail or step.output or '').strip()[:180]}"
            for step in older
            if step.status == TaskStatus.FAILED
        ]
        failed_tools = _dedupe_keep_order(failed_tools_raw)[:4]
        lines = [f"Older rounds summary ({len(older)} steps):"]
        if failed_tools:
            lines.append("  failures:")
            lines.extend(f"  - {item}" for item in failed_tools)
        older_outputs_raw = [
            next((line.strip() for line in step.output.splitlines() if line.strip()), "")
            for step in older
            if step.output
        ]
        older_outputs = _dedupe_keep_order(older_outputs_raw)[:4]
        if older_outputs:
            lines.append("  outputs:")
            lines.extend(f"  - {item[:180]}" for item in older_outputs if item)
        deduped = len(failed_tools_raw) != len(_dedupe_keep_order(failed_tools_raw)) or len(
            older_outputs_raw
        ) != len(_dedupe_keep_order(older_outputs_raw))
        block_labels = "rolling_summary,deduped" if deduped else "rolling_summary"
        blocks.append(
            ContextBlock(
                kind="memory_summary",
                text="\n".join(lines),
                priority=25,
                metadata={"labels": block_labels},
            )
        )
    for idx, step in enumerate(recent, start=1):
        blocks.append(
            _step_to_context_block(step, priority=80 - idx, step_output_max_tokens=step_output_max_tokens)
        )
    fitted = fit_blocks_to_budget(blocks, max_tokens=max_tokens, model_name=model_name)
    return render_blocks(fitted, separator="\n\n")


def _prefix_round(round_idx: int, steps: list[PlanStep]) -> list[PlanStep]:
    return [step.model_copy(update={"id": f"r{round_idx}-{step.id}"}) for step in steps]


StreamEventCallback = Callable[[dict[str, Any]], None]


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
        stream_event: StreamEventCallback | None = None,
        goal_check: GoalCheckSynthesizer | None = None,
        plan_goal_check_max_replan_rounds: int = 0,
        context_budgets: ContextBudgets | None = None,
    ):
        self.skill_loader = skill_loader
        self.tool_registry = tool_registry
        self.skill_matcher = SkillMatcher()
        self.planner = planner
        self.executor = Executor(tool_registry, max_step_retries=max_step_retries)
        self.task_store = task_store
        self.max_failed_rounds = max(1, max_failed_rounds)
        self._conclusion_synthesizer = conclusion_synthesizer
        self._stream_event = stream_event
        self._goal_check = goal_check
        self._plan_goal_check_max_replan_rounds = max(0, plan_goal_check_max_replan_rounds)
        self._context_budgets = context_budgets or _DEFAULT_BUDGETS
        self._step_verifier = StepVerifier()
        self._loop_guard = LoopGuard()

    def _stream(self, event: dict[str, Any]) -> None:
        if self._stream_event is not None:
            self._stream_event(event)

    def run(
        self,
        task: str,
        plan_override: list[PlanStep] | None = None,
        *,
        session_context: str | None = None,
        parent_run_id: str | None = None,
    ) -> TaskResult:
        run_id = self.task_store.next_run_id()
        rid_tok = run_context.set_run_id(run_id)
        sess_tok = run_context.set_session_context(session_context)
        try:
            return self._run_inner(
                task,
                plan_override,
                run_id=run_id,
                session_context=session_context,
                parent_run_id=parent_run_id,
            )
        finally:
            run_context.reset_session_context(sess_tok)
            run_context.reset_run_id(rid_tok)

    def _run_inner(
        self,
        task: str,
        plan_override: list[PlanStep] | None,
        *,
        run_id: str,
        session_context: str | None,
        parent_run_id: str | None,
    ) -> TaskResult:
        skills = self.skill_loader.load_all()
        matched_skills = self.skill_matcher.match(task, skills)
        selected_skills = matched_skills[:2]
        available_tools = self.tool_registry.list_tools()

        self._stream(
            {
                "type": "run_begin",
                "run_id": run_id,
                "task": task,
                "selected_skills": [s.name for s in selected_skills],
            }
        )

        goal_exhausted = False
        goal_mismatch_count = 0
        working_memory = RunWorkingMemory()
        loop_guard_error: str | None = None
        loop_guard_events: list[dict[str, Any]] = []
        if plan_override is not None:
            ov_summaries = [
                {"id": s.id, "tool": s.tool, "description": s.description} for s in plan_override
            ]
            self._stream({"type": "round_plan", "round": 1, "source": "file_override", "steps": ov_summaries})

            def _on_step(step: PlanStep) -> None:
                self._stream({"type": "step_finished", "round": 1, "step": step.model_dump()})

            executed_plan = _prefix_round(
                1,
                self.executor.execute(plan_override, on_step_complete=_on_step),
            )
            executed_plan = self._process_completed_steps(executed_plan, working_memory, round_idx=1)
            success = bool(executed_plan) and all(s.status == TaskStatus.COMPLETED for s in executed_plan)
            failed_rounds = 0 if success else 1
        else:
            accumulated: list[PlanStep] = []
            failed_rounds = 0
            round_idx = 0
            outcome_feedback: str | None = None
            latest_round_succeeded = False

            while True:
                prior = (
                    _format_prior_context(
                        accumulated,
                        max_tokens=self._context_budgets.prior_context_max_tokens,
                        step_output_max_tokens=self._context_budgets.prior_step_output_max_tokens,
                    )
                    if accumulated
                    else None
                )
                if working_memory.actions_attempted:
                    memory_digest = working_memory.render_digest()
                    prior = f"{prior}\n\n{memory_digest}" if prior else memory_digest
                plan = self.planner.create_plan(
                    task,
                    selected_skills,
                    available_tools,
                    prior_context=prior,
                    session_context=session_context,
                    outcome_feedback=outcome_feedback,
                )
                outcome_feedback = None

                if not plan:
                    failed_rounds += 1
                    self._stream(
                        {
                            "type": "plan_empty",
                            "failed_rounds_so_far": failed_rounds,
                            "max_failed_rounds": self.max_failed_rounds,
                        }
                    )
                    if failed_rounds >= self.max_failed_rounds:
                        break
                    continue

                round_idx += 1
                step_summaries = [
                    {"id": s.id, "tool": s.tool, "description": s.description} for s in plan
                ]
                self._stream({"type": "round_plan", "round": round_idx, "steps": step_summaries})

                def _on_step(step: PlanStep, *, r: int = round_idx) -> None:
                    self._stream({"type": "step_finished", "round": r, "step": step.model_dump()})

                batch = _prefix_round(round_idx, self.executor.execute(plan, on_step_complete=_on_step))
                batch = self._process_completed_steps(batch, working_memory, round_idx=round_idx)
                accumulated.extend(batch)

                loop_decision = self._loop_guard.check(working_memory, batch)
                if loop_decision.triggered:
                    loop_guard_events.append(loop_decision.model_dump())
                    self._stream(
                        {
                            "type": "loop_guard",
                            "round": round_idx,
                            "code": loop_decision.code,
                            "reason": loop_decision.reason,
                            "suggested_action": loop_decision.suggested_action,
                        }
                    )
                    if loop_decision.suggested_action == "fail":
                        latest_round_succeeded = False
                        loop_guard_error = f"Loop guard: {loop_decision.code}: {loop_decision.reason}"
                        break
                    if loop_decision.suggested_action == "replan":
                        outcome_feedback = f"Loop guard requested re-plan: {loop_decision.reason}"
                        latest_round_succeeded = False
                        continue

                if all(step.status == TaskStatus.COMPLETED for step in batch):
                    latest_round_succeeded = True
                    self._stream({"type": "round_completed", "round": round_idx})
                    goal_check_error = False
                    if self._goal_check is not None and self._goal_check.is_available():
                        try:
                            gc = self._goal_check.check(task, accumulated, session_context)
                        except Exception as exc:  # noqa: BLE001 — surface as stream + safe exit
                            goal_check_error = True
                            self._stream(
                                {
                                    "type": "goal_check",
                                    "round": round_idx,
                                    "satisfied": None,
                                    "error": str(exc)[:1_200],
                                }
                            )
                        else:
                            self._stream(
                                {
                                    "type": "goal_check",
                                    "round": round_idx,
                                    "satisfied": gc.goal_satisfied,
                                    "reason": (gc.reason or "")[:2_000],
                                }
                            )
                            if gc.goal_satisfied:
                                break
                            goal_mismatch_count += 1
                            if goal_mismatch_count > self._plan_goal_check_max_replan_rounds:
                                goal_exhausted = True
                                break
                            parts: list[str] = []
                            if (gc.reason or "").strip():
                                parts.append(f"Review: {gc.reason.strip()}")
                            if (gc.planner_brief or "").strip():
                                parts.append(f"Planner focus:\n{gc.planner_brief.strip()}")
                            outcome_feedback = (
                                "\n\n".join(parts)
                                if parts
                                else "Re-plan: the previous successful batch did not yet satisfy the user task; use different or additional tools."
                            )
                            continue
                    if goal_check_error and any(step.tool == "web_search" for step in batch):
                        latest_round_succeeded = False
                        continue
                    break

                failed_rounds += 1
                latest_round_succeeded = False
                self._stream(
                    {
                        "type": "round_failed",
                        "round": round_idx,
                        "failed_rounds_so_far": failed_rounds,
                        "max_failed_rounds": self.max_failed_rounds,
                    }
                )
                if failed_rounds >= self.max_failed_rounds:
                    break

            executed_plan = accumulated
            success = (
                bool(executed_plan)
                and latest_round_succeeded
                and not goal_exhausted
            )

        failed_step = None
        if not success:
            failed_step = next(
                (step for step in reversed(executed_plan) if step.status == TaskStatus.FAILED),
                None,
            )

        output = "\n\n".join(step.output for step in executed_plan if step.output)
        error: str | None = (failed_step.error_detail or failed_step.output) if failed_step else None
        if not success and error is None and goal_exhausted:
            error = (
                "Goal check: the task was not considered satisfied after "
                f"{self._plan_goal_check_max_replan_rounds} re-plan round(s) following completed tool steps. "
                f"Last review rounds (not satisfied): {goal_mismatch_count}."
            )
        if not success and error is None and loop_guard_error:
            error = loop_guard_error
        if not success and error is None:
            error = (
                f"Stopped after {failed_rounds} failed replan round(s) "
                f"(limit {self.max_failed_rounds}) without completing the task."
            )

        final_status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
        self._stream({"type": "conclusion_begin", "run_id": run_id})
        conclusion = fallback_run_conclusion(task, final_status, executed_plan, output, error)
        if self._conclusion_synthesizer is not None and self._conclusion_synthesizer.is_available():
            try:
                conclusion = self._conclusion_synthesizer.synthesize(
                    task, final_status, executed_plan, output, error
                )
            except Exception:
                pass
        self._stream({"type": "conclusion_done", "run_id": run_id, "conclusion": conclusion})

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
            goal_check_mismatch_rounds=goal_mismatch_count,
            conclusion=conclusion,
            parent_run_id=parent_run_id,
            working_memory=working_memory.model_dump(),
            run_stats=build_run_stats(
                executed_plan,
                goal_check_mismatch_rounds=goal_mismatch_count,
                loop_guard_events=loop_guard_events,
            ),
        )
        self.task_store.save(result)
        self._stream(
            {
                "type": "run_end",
                "run_id": run_id,
                "status": result.status.value,
                "orchestrator_failed_rounds": failed_rounds,
            }
        )
        return result

    def replay(self, run_id: str) -> TaskResult:
        return self.task_store.load(run_id).result

    def _process_completed_steps(
        self,
        steps: list[PlanStep],
        working_memory: RunWorkingMemory,
        *,
        round_idx: int,
    ) -> list[PlanStep]:
        processed: list[PlanStep] = []
        for step in steps:
            working_memory.record_step(step)
            verification = self._step_verifier.verify_step(step, working_memory)
            verified_step = step.model_copy(update={"verifications": [verification.model_dump()]})
            self._stream(
                {
                    "type": "step_verified",
                    "round": round_idx,
                    "step_id": verified_step.id,
                    "verification": verification.model_dump(),
                }
            )
            processed.append(verified_step)
        return processed
