from pathlib import Path

from uni_agent.agent.orchestrator import Orchestrator
from uni_agent.agent.planner import HeuristicPlanner
from uni_agent.observability.task_store import TaskStore
from uni_agent.sandbox.runner import LocalSandbox
from uni_agent.skills.loader import SkillLoader
from uni_agent.tools.builtins import register_builtin_handlers
from uni_agent.tools.registry import ToolRegistry


def _orchestrator(tmp_path: Path, workspace: Path) -> Orchestrator:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    register_builtin_handlers(registry, workspace, LocalSandbox(workspace))
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    return Orchestrator(
        skill_loader=SkillLoader(skills_dir),
        tool_registry=registry,
        planner=HeuristicPlanner(),
        task_store=TaskStore(tmp_path / "runs"),
    )


def test_run_executes_file_write_end_to_end(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    note = workspace / "draft.txt"
    note.write_text("before", encoding="utf-8")

    orchestrator = _orchestrator(tmp_path, workspace)
    result = orchestrator.run('write the file draft.txt with content "after"')

    assert result.status.value == "completed"
    assert note.read_text(encoding="utf-8") == "after"
    assert (tmp_path / "runs" / f"{result.run_id}.json").exists()
