from __future__ import annotations

from pathlib import Path

from uni_agent.agent.orchestrator import Orchestrator
from uni_agent.agent.plan_loader import load_plan_file
from uni_agent.evals.loader import load_eval_cases
from uni_agent.evals.llm_judge import EvalLLMJudge
from uni_agent.evals.models import EvalCase, EvalSuiteResult
from uni_agent.evals.scorer import score_case


def run_eval_suite(
    path: Path,
    orchestrator: Orchestrator,
    *,
    llm_judge: EvalLLMJudge | None = None,
    workspace: Path | None = None,
) -> EvalSuiteResult:
    cases = load_eval_cases(path)
    results = []
    for case in cases:
        task_result = _run_case(case, orchestrator)
        judged = llm_judge.judge(case, task_result) if llm_judge is not None else None
        results.append(
            score_case(
                case,
                task_result,
                llm_score=judged,
                workspace=workspace,
            )
        )
    passed = sum(1 for result in results if result.passed)
    average = sum(result.overall_score for result in results) / max(1, len(results))
    return EvalSuiteResult(
        cases_total=len(results),
        cases_passed=passed,
        pass_rate=round(passed / max(1, len(results)), 4),
        average_score=round(average, 2),
        results=results,
    )


def _run_case(case: EvalCase, orchestrator: Orchestrator):
    plan_override = None
    if case.plan:
        if case.source_path is None:
            plan_path = Path(case.plan)
        else:
            plan_path = (case.source_path.parent / case.plan).resolve()
        plan_override = load_plan_file(plan_path)
    return orchestrator.run(case.task, plan_override=plan_override)
