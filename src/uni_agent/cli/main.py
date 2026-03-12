from __future__ import annotations

import json

import typer

from uni_agent.agent.planner import HeuristicPlanner
from uni_agent.agent.orchestrator import Orchestrator
from uni_agent.config.settings import get_settings
from uni_agent.observability.logging import configure_logging
from uni_agent.observability.task_store import TaskStore
from uni_agent.sandbox.runner import LocalSandbox
from uni_agent.skills.loader import SkillLoader
from uni_agent.tools.builtins import register_builtin_handlers
from uni_agent.tools.registry import ToolRegistry

app = typer.Typer(help="uni-agent CLI")


def build_orchestrator() -> Orchestrator:
    settings = get_settings()
    configure_logging(settings.log_level)
    tool_registry = ToolRegistry()
    tool_registry.register_builtin_tools()
    sandbox = LocalSandbox(settings.workspace)
    register_builtin_handlers(tool_registry, settings.workspace, sandbox)
    skill_loader = SkillLoader(settings.skills_dir)
    planner = HeuristicPlanner()
    task_store = TaskStore(settings.task_log_dir)
    return Orchestrator(
        skill_loader=skill_loader,
        tool_registry=tool_registry,
        planner=planner,
        task_store=task_store,
    )


@app.command("skills")
def list_skills() -> None:
    settings = get_settings()
    loader = SkillLoader(settings.skills_dir)
    skills = loader.load_all()
    for skill in skills:
        typer.echo(f"{skill.name}\t{skill.version}\t{skill.description}")


@app.command("run")
def run_task(task: str) -> None:
    orchestrator = build_orchestrator()
    result = orchestrator.run(task)
    typer.echo(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


@app.command("replay")
def replay_task(run_id: str) -> None:
    orchestrator = build_orchestrator()
    result = orchestrator.replay(run_id)
    typer.echo(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
