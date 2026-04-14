from pathlib import Path
from typing import Any

from uni_agent.agent.orchestrator import Orchestrator
from uni_agent.agent.planner import HeuristicPlanner
from uni_agent.observability.task_store import TaskStore
from uni_agent.sandbox.runner import LocalSandbox
from uni_agent.skills.loader import SkillLoader
from uni_agent.tools.builtins import register_builtin_handlers
from uni_agent.tools.registry import ToolRegistry


def build_runtime(tmp_path: Path, **orch_kwargs) -> Orchestrator:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    register_builtin_handlers(registry, Path(".").resolve(), LocalSandbox(Path(".").resolve()))
    return Orchestrator(
        skill_loader=SkillLoader(Path("skills")),
        tool_registry=registry,
        planner=HeuristicPlanner(),
        task_store=TaskStore(tmp_path / "runs"),
        **orch_kwargs,
    )


def test_orchestrator_reads_a_file_and_persists_run(tmp_path: Path) -> None:
    orchestrator = build_runtime(tmp_path)

    result = orchestrator.run("read README.md")

    assert result.status.value == "completed"
    assert result.run_id
    assert any(step.tool == "file_read" for step in result.plan)
    assert "# uni-agent" in result.output
    assert result.conclusion
    assert "执行" in result.conclusion or "步骤" in result.conclusion
    assert (tmp_path / "runs" / f"{result.run_id}.json").exists()


def test_orchestrator_stream_events_order(tmp_path: Path) -> None:
    events: list[dict[str, Any]] = []

    def capture(ev: dict[str, Any]) -> None:
        events.append(ev)

    orchestrator = build_runtime(tmp_path, stream_event=capture)
    orchestrator.run("read README.md")

    types = [e["type"] for e in events]
    assert types[0] == "run_begin"
    assert "round_plan" in types
    assert "step_finished" in types
    assert "conclusion_begin" in types
    assert "conclusion_done" in types
    assert types[-1] == "run_end"
    assert events[-1]["status"] == "completed"


def test_orchestrator_can_replay_previous_run(tmp_path: Path) -> None:
    orchestrator = build_runtime(tmp_path)

    result = orchestrator.run("read README.md")
    replayed = orchestrator.replay(result.run_id or "")

    assert replayed.run_id == result.run_id
    assert replayed.output == result.output
    assert replayed.conclusion == result.conclusion
