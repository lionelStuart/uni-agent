from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer

from uni_agent.agent.plan_loader import load_plan_file
from uni_agent.bootstrap import build_orchestrator
from uni_agent.observability.logging import configure_logging
from uni_agent.skills.loader import SkillLoader
from uni_agent.config.settings import get_settings

app = typer.Typer(help="uni-agent CLI")


def _stderr_ndjson_stream(event: dict[str, Any]) -> None:
    print(json.dumps(event, ensure_ascii=False), file=sys.stderr, flush=True)


@app.command("skills")
def list_skills() -> None:
    settings = get_settings()
    loader = SkillLoader(settings.skills_dir, settings.workspace)
    skills = loader.load_all()
    for skill in skills:
        typer.echo(f"{skill.name}\t{skill.version}\t{skill.description}")


@app.command("run")
def run_task(
    task: str,
    plan: Path | None = typer.Option(
        None,
        "--plan",
        help="Execute a static YAML/JSON plan (skips automatic planning).",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    stream: bool = typer.Option(
        True,
        "--stream/--no-stream",
        help="Stream execution events to stderr as NDJSON (one JSON object per line).",
    ),
) -> None:
    orchestrator = build_orchestrator(
        stream_event=_stderr_ndjson_stream if stream else None,
    )
    plan_override = load_plan_file(plan) if plan is not None else None
    result = orchestrator.run(task, plan_override=plan_override)
    typer.echo(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


@app.command("client")
def client_cmd(
    stream: bool = typer.Option(
        True,
        "--stream/--no-stream",
        help="Show human-readable execution progress on stderr during each task.",
    ),
    session: str | None = typer.Option(
        None,
        "--session",
        "-s",
        help="Load an existing session id or id prefix instead of creating a new one.",
    ),
) -> None:
    """Interactive REPL: new time-based session by default; persist after each task; ``load <id>`` inside."""
    from uni_agent.cli.client_shell import run_interactive_client

    run_interactive_client(stream=stream, session_id=session)


@app.command("replay")
def replay_task(
    run_id: str,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Print each stored plan step."),
    output_format: str = typer.Option(
        "full",
        "--format",
        "-f",
        help="Output shape: full (JSON), steps (human steps only), jsonl (NDJSON lines).",
    ),
) -> None:
    if output_format not in {"full", "steps", "jsonl"}:
        raise typer.BadParameter("format must be one of: full, steps, jsonl")

    orchestrator = build_orchestrator()
    result = orchestrator.replay(run_id)

    if output_format == "steps":
        for step in result.plan:
            typer.echo(
                f"{step.id}\t{step.tool}\t{step.status.value}\t"
                f"{step.error_type or ''}\t{step.error_detail or ''}"
            )
            if step.output:
                typer.echo(step.output)
        return

    if output_format == "jsonl":
        for step in result.plan:
            typer.echo(json.dumps(step.model_dump(), ensure_ascii=False))
        summary = {
            "type": "task_result",
            "run_id": result.run_id,
            "task": result.task,
            "status": result.status.value,
            "error": result.error,
            "output": result.output,
        }
        typer.echo(json.dumps(summary, ensure_ascii=False))
        return

    if verbose:
        for step in result.plan:
            typer.echo(
                f"{step.id}\t{step.tool}\t{step.status.value}\t"
                f"{step.error_type or ''}\t{step.error_detail or ''}"
            )
            if step.output:
                typer.echo(step.output)
    typer.echo(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
