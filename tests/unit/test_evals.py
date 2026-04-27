from pathlib import Path

from typer.testing import CliRunner

from uni_agent.agent.orchestrator import Orchestrator
from uni_agent.agent.planner import Planner
from uni_agent.evals.loader import load_eval_cases
from uni_agent.evals.models import DimensionScore, EvalAssertions
from uni_agent.evals.runner import run_eval_suite
from uni_agent.evals.scorer import score_case
from uni_agent.observability.task_store import TaskStore
from uni_agent.shared.models import PlanStep, SkillSpec, TaskResult, TaskStatus, ToolSpec
from uni_agent.skills.loader import SkillLoader
from uni_agent.tools.registry import ToolRegistry
from uni_agent.cli import main


class StaticPlanner(Planner):
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
        return [
            PlanStep(
                id="step-1",
                description="read",
                tool="file_read",
                arguments={"path": "README.md"},
            )
        ]


def test_score_case_uses_deterministic_assertions() -> None:
    case = load_eval_cases(Path("docs/evals/cases/read-readme.yaml"))[0]
    result = TaskResult(
        run_id="r1",
        task=case.task,
        status=TaskStatus.COMPLETED,
        plan=[
            PlanStep(
                id="s1",
                description="read",
                tool="file_read",
                status=TaskStatus.COMPLETED,
                output="# uni-agent",
            )
        ],
        output="raw output without marker",
        answer="# uni-agent",
        run_stats={"loop_guard_counts": {}, "verification_failure_counts": {}},
    )

    scored = score_case(case, result)

    assert scored.passed is True
    assert scored.overall_score == 100.0


def test_score_case_checks_raw_output_when_answer_is_paraphrased() -> None:
    case = load_eval_cases(Path("docs/evals/cases/python-analysis.yaml"))[0]
    result = TaskResult(
        run_id="r1",
        task=case.task,
        status=TaskStatus.COMPLETED,
        plan=[
            PlanStep(
                id="s1",
                description="run python",
                tool="run_python",
                status=TaskStatus.COMPLETED,
            )
        ],
        output="rows=3\ntotal=10",
        answer="There are three rows and the total is ten.",
        run_stats={"loop_guard_counts": {}, "verification_failure_counts": {}},
    )

    scored = score_case(case, result)

    assert scored.passed is True


def test_score_case_checks_file_and_payload_assertions(tmp_path: Path) -> None:
    (tmp_path / "out.txt").write_text("artifact-ok", encoding="utf-8")
    case = load_eval_cases(Path("docs/evals/cases/write-artifact.yaml"))[0].model_copy(
        update={
            "assertions": EvalAssertions(
                status="completed",
                file_contains={"out.txt": "artifact-ok"},
                tool_payload_contains={"child_run_id": "completed"},
            )
        }
    )
    result = TaskResult(
        run_id="r1",
        task=case.task,
        status=TaskStatus.COMPLETED,
        plan=[
            PlanStep(
                id="s1",
                description="delegate",
                tool="delegate_task",
                status=TaskStatus.COMPLETED,
                tool_result={"payload": {"child_run_id": "c1", "status": "completed"}},
            )
        ],
        output="ok",
        run_stats={"loop_guard_counts": {}, "verification_failure_counts": {}},
    )

    scored = score_case(case, result, workspace=tmp_path)

    assert scored.scores["goal"].passed is True


def test_loader_skips_plan_yaml_files() -> None:
    cases = load_eval_cases(Path("docs/evals/cases"))

    ids = {case.id for case in cases}
    assert "read-readme" in ids
    assert all(case.task for case in cases)


def test_eval_suite_runs_with_static_tool_handler(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools(include_delegate_task=False, tool_profile="readonly")
    registry.attach_handler("file_read", lambda _: "# uni-agent\n")
    orchestrator = Orchestrator(
        skill_loader=SkillLoader(tmp_path / "skills"),
        tool_registry=registry,
        planner=StaticPlanner(),
        task_store=TaskStore(tmp_path / "runs"),
    )

    result = run_eval_suite(Path("docs/evals/cases/read-readme.yaml"), orchestrator)

    assert result.cases_total == 1
    assert result.cases_passed == 1
    assert result.average_score == 100.0


def test_eval_suite_includes_llm_judge_score(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools(include_delegate_task=False, tool_profile="readonly")
    registry.attach_handler("file_read", lambda _: "# uni-agent\n")
    orchestrator = Orchestrator(
        skill_loader=SkillLoader(tmp_path / "skills"),
        tool_registry=registry,
        planner=StaticPlanner(),
        task_store=TaskStore(tmp_path / "runs"),
    )

    class FakeJudge:
        def judge(self, _case, _result):
            return DimensionScore(score=50.0, passed=True, reasons=["ok"])

    result = run_eval_suite(Path("docs/evals/cases/read-readme.yaml"), orchestrator, llm_judge=FakeJudge())

    assert result.results[0].scores["llm_judge"].score == 50.0
    assert result.average_score == 90.0


def test_eval_cli_rejects_bad_format() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["eval", "docs/evals/cases/read-readme.yaml", "--format", "bad"])

    assert result.exit_code != 0
    assert "format must be one of" in result.output


def test_eval_cli_default_enables_llm_judge_and_disables_agent_llm_review(monkeypatch) -> None:
    captured = {}

    class DummyOrchestrator:
        pass

    def fake_build_orchestrator(*, stream_event=None, settings=None, **_kwargs):
        captured["goal_check"] = settings.plan_goal_check_enabled
        captured["conclusion"] = settings.run_conclusion_llm
        return DummyOrchestrator()

    def fake_run_eval_suite(_path, _orchestrator, *, llm_judge=None, workspace=None):
        from uni_agent.evals.models import EvalSuiteResult

        captured["judge_enabled"] = llm_judge is not None
        return EvalSuiteResult(cases_total=0, cases_passed=0, pass_rate=0, average_score=0, results=[])

    monkeypatch.setattr(main, "build_orchestrator", fake_build_orchestrator)
    monkeypatch.setattr(main, "run_eval_suite", fake_run_eval_suite)

    runner = CliRunner()
    result = runner.invoke(main.app, ["eval", "docs/evals/cases/read-readme.yaml"])

    assert result.exit_code == 0
    assert captured == {"goal_check": False, "conclusion": False, "judge_enabled": True}


def test_eval_cli_can_disable_llm_judge(monkeypatch) -> None:
    captured = {}

    class DummyOrchestrator:
        pass

    def fake_build_orchestrator(*, stream_event=None, settings=None, **_kwargs):
        return DummyOrchestrator()

    def fake_run_eval_suite(_path, _orchestrator, *, llm_judge=None, workspace=None):
        from uni_agent.evals.models import EvalSuiteResult

        captured["judge_enabled"] = llm_judge is not None
        return EvalSuiteResult(cases_total=0, cases_passed=0, pass_rate=0, average_score=0, results=[])

    monkeypatch.setattr(main, "build_orchestrator", fake_build_orchestrator)
    monkeypatch.setattr(main, "run_eval_suite", fake_run_eval_suite)

    runner = CliRunner()
    result = runner.invoke(main.app, ["eval", "docs/evals/cases/read-readme.yaml", "--no-llm-judge"])

    assert result.exit_code == 0
    assert captured == {"judge_enabled": False}
