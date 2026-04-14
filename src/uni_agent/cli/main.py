from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer

from uni_agent.agent.llm import EnvLLMProvider
from uni_agent.agent.plan_loader import load_plan_file
from uni_agent.agent.orchestrator import Orchestrator, StreamEventCallback
from uni_agent.agent.run_conclusion import RunConclusionSynthesizer
from uni_agent.agent.planner import HeuristicPlanner
from uni_agent.agent.pydantic_planner import PydanticAIPlanner
from uni_agent.config.settings import (
    Settings,
    get_settings,
    parse_http_fetch_allowed_hosts,
    parse_sandbox_allowed_commands,
)
from uni_agent.observability.logging import configure_logging
from uni_agent.observability.task_store import TaskStore
from uni_agent.sandbox.runner import LocalSandbox, prompt_tty_approve_disallowed_command
from uni_agent.skills.loader import SkillLoader
from uni_agent.tools.builtins import register_builtin_handlers
from uni_agent.tools.registry import ToolRegistry

app = typer.Typer(help="uni-agent CLI")


def _sandbox_approval_callback(settings: Settings):
    if not settings.sandbox_prompt_for_disallowed:
        return None
    return prompt_tty_approve_disallowed_command


def _stderr_ndjson_stream(event: dict[str, Any]) -> None:
    print(json.dumps(event, ensure_ascii=False), file=sys.stderr, flush=True)


def build_orchestrator(stream_event: StreamEventCallback | None = None) -> Orchestrator:
    settings = get_settings()
    configure_logging(settings.log_level)
    tool_registry = ToolRegistry()
    tool_registry.register_builtin_tools()
    allowed_commands = parse_sandbox_allowed_commands(settings.sandbox_allowed_commands)
    sandbox = LocalSandbox(
        settings.workspace,
        allowed_commands=allowed_commands,
        command_timeout=settings.sandbox_command_timeout_seconds,
        approve_non_allowlisted=_sandbox_approval_callback(settings),
    )
    register_builtin_handlers(
        tool_registry,
        settings.workspace,
        sandbox,
        http_fetch_max_bytes=settings.http_fetch_max_bytes,
        http_fetch_allow_private_networks=settings.http_fetch_allow_private_networks,
        http_fetch_allowed_hosts=parse_http_fetch_allowed_hosts(settings.http_fetch_allowed_hosts),
        http_fetch_timeout_seconds=settings.sandbox_command_timeout_seconds,
    )
    skill_loader = SkillLoader(settings.skills_dir)
    heuristic = HeuristicPlanner()
    provider = EnvLLMProvider(
        settings.model_name,
        openai_base_url=settings.openai_base_url,
        openai_api_key=settings.openai_api_key,
    )
    model_settings = None
    if settings.llm_temperature is not None:
        model_settings = {"temperature": settings.llm_temperature}

    allowed_shell = frozenset(allowed_commands)
    if settings.planner_backend == "heuristic":
        planner = heuristic
    elif settings.planner_backend == "pydantic_ai":
        planner = PydanticAIPlanner(
            provider=provider,
            fallback=heuristic,
            planner_instructions=settings.planner_instructions,
            global_system_prompt=settings.global_system_prompt,
            model_settings=model_settings,
            retries=settings.llm_retries,
            allowed_shell_commands=allowed_shell,
        )
    else:
        planner = (
            PydanticAIPlanner(
                provider=provider,
                fallback=heuristic,
                planner_instructions=settings.planner_instructions,
                global_system_prompt=settings.global_system_prompt,
                model_settings=model_settings,
                retries=settings.llm_retries,
                allowed_shell_commands=allowed_shell,
            )
            if provider.is_available()
            else heuristic
        )
    task_store = TaskStore(settings.task_log_dir)
    conclusion_syn: RunConclusionSynthesizer | None = None
    if settings.run_conclusion_llm and provider.is_available():
        conclusion_syn = RunConclusionSynthesizer(
            provider=provider,
            model_settings=model_settings,
            retries=0,
            conclusion_system_prompt=settings.conclusion_system_prompt,
            global_system_prompt=settings.global_system_prompt,
        )
    return Orchestrator(
        skill_loader=skill_loader,
        tool_registry=tool_registry,
        planner=planner,
        task_store=task_store,
        max_step_retries=settings.tool_step_retries,
        max_failed_rounds=settings.orchestrator_max_failed_rounds,
        conclusion_synthesizer=conclusion_syn,
        stream_event=stream_event,
    )


@app.command("skills")
def list_skills() -> None:
    settings = get_settings()
    loader = SkillLoader(settings.skills_dir)
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
