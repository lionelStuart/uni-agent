from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import typer

from uni_agent.agent.orchestrator import StreamEventCallback
from uni_agent.config.settings import get_settings
from uni_agent.observability.client_session import (
    SessionStore,
    build_session_context_for_planner,
    task_result_to_entry,
)


def _human_stream_event(ev: dict[str, Any]) -> None:
    """Pretty progress on stderr (stdout reserved for final JSON blocks in REPL)."""
    t = ev.get("type")
    if t == "run_begin":
        typer.secho(
            f">> run_id={ev.get('run_id')}  task={ev.get('task')!r}",
            fg=typer.colors.CYAN,
            err=True,
        )
    elif t == "round_plan":
        steps = ev.get("steps") or []
        parts = [f"{s.get('id')}:{s.get('tool')}" for s in steps]
        src = ev.get("source")
        extra = f" ({src})" if src else ""
        typer.secho(f"  · round {ev.get('round')}{extra}: " + ", ".join(parts), err=True)
    elif t == "plan_empty":
        typer.secho(
            f"  · planner returned empty plan (failed_rounds={ev.get('failed_rounds_so_far')})",
            fg=typer.colors.YELLOW,
            err=True,
        )
    elif t == "step_finished":
        step = ev.get("step") or {}
        sid = step.get("id", "")
        tool = step.get("tool", "")
        st = step.get("status", "")
        typer.secho(f"  · step {sid} [{tool}] → {st}", err=True)
        out = (step.get("output") or "").strip()
        if out:
            head = out.splitlines()[:12]
            body = "\n".join(head)
            if len(out.splitlines()) > 12 or len(body) > 2000:
                body = body[:2000] + "\n... [truncated]"
            typer.secho(body, dim=True, err=True)
        errd = step.get("error_detail")
        if errd:
            typer.secho(f"    error: {errd}", fg=typer.colors.RED, err=True)
    elif t == "round_completed":
        typer.secho(f"  · round {ev.get('round')} completed", fg=typer.colors.GREEN, err=True)
    elif t == "round_failed":
        typer.secho(
            f"  · round {ev.get('round')} failed (replan; "
            f"failed_rounds={ev.get('failed_rounds_so_far')}/{ev.get('max_failed_rounds')})",
            fg=typer.colors.YELLOW,
            err=True,
        )
    elif t == "conclusion_begin":
        typer.secho("  · generating conclusion…", dim=True, err=True)
    elif t == "conclusion_done":
        concl = ev.get("conclusion") or ""
        typer.secho("\n── conclusion ──", fg=typer.colors.MAGENTA, err=True)
        typer.secho(concl, err=True)
    elif t == "run_end":
        typer.secho(
            f"\n■ finished status={ev.get('status')} run_id={ev.get('run_id')}\n",
            bold=True,
            err=True,
        )
    else:
        typer.secho(json.dumps(ev, ensure_ascii=False), err=True)


def _print_help() -> None:
    typer.echo(
        """
Commands:
  <text>          Run as a task (same as agent run).
  load <id>       Load session by id or id prefix (from session store).
  new             Start a new session (current one saved first if it has entries).
  sessions        List recent session files.
  status          Show current session id and run count.
  help            This help.
  exit / quit     Leave the client.

Environment matches ``agent run`` (see UNI_AGENT_* in settings).
""".strip()
    )


def run_interactive_client(
    *,
    stream: bool = True,
    session_id: str | None = None,
) -> None:
    settings = get_settings()
    store = SessionStore(settings.session_dir)
    workspace = settings.workspace.resolve()

    if session_id:
        session = store.load(session_id)
        typer.secho(f"Loaded session {session.id} ({len(session.entries)} runs).", fg=typer.colors.GREEN)
        if session.workspace and session.workspace != str(workspace):
            typer.secho(
                f"Note: session workspace was {session.workspace!r}; current UNI_AGENT_WORKSPACE is {str(workspace)!r}.",
                fg=typer.colors.YELLOW,
            )
    else:
        session = store.new_session(workspace)
        store.save(session)
        typer.secho(f"New session {session.id} (workspace={session.workspace})", fg=typer.colors.GREEN)

    stream_fn: StreamEventCallback | None = _human_stream_event if stream else None

    typer.echo("uni-agent interactive client — type `help` for commands.\n")

    while True:
        try:
            line = input("uni-agent> ").strip()
        except (EOFError, KeyboardInterrupt):
            typer.echo("\nBye.")
            store.save(session)
            raise SystemExit(0) from None

        if not line:
            continue

        lower = line.lower()
        if lower in {"exit", "quit", ":q"}:
            store.save(session)
            typer.echo("Session saved. Bye.")
            return

        if lower == "help" or lower == "?":
            _print_help()
            continue

        if lower == "status":
            typer.echo(f"session={session.id}  runs={len(session.entries)}  workspace={session.workspace}")
            continue

        if lower == "sessions":
            rows = store.list_sessions(limit=25)
            if not rows:
                typer.echo("(no sessions yet)")
                continue
            for sid, mtime in rows:
                typer.echo(f"  {sid}  mtime={mtime}")
            continue

        if lower == "new":
            store.save(session)
            session = store.new_session(workspace)
            store.save(session)
            typer.secho(f"New session {session.id}", fg=typer.colors.GREEN)
            continue

        if lower.startswith("load "):
            arg = line[5:].strip()
            if not arg:
                typer.secho("Usage: load <session_id_or_prefix>", fg=typer.colors.RED)
                continue
            try:
                store.save(session)
                session = store.load(arg)
                typer.secho(f"Loaded session {session.id} ({len(session.entries)} runs).", fg=typer.colors.GREEN)
            except FileNotFoundError as exc:
                typer.secho(str(exc), fg=typer.colors.RED)
            continue

        # Task line
        task = line
        started = datetime.now(timezone.utc).isoformat()
        from uni_agent.cli.main import build_orchestrator

        orchestrator = build_orchestrator(stream_event=stream_fn)
        ctx = build_session_context_for_planner(session.entries)
        try:
            result = orchestrator.run(task, session_context=ctx if ctx.strip() else None)
        except Exception as exc:
            typer.secho(f"Run failed: {exc}", fg=typer.colors.RED)
            continue

        entry = task_result_to_entry(result)
        entry.started_at = started
        session.entries.append(entry)
        store.save(session)

        typer.echo(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
