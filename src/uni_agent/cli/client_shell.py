from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any

import typer

from uni_agent.agent.llm import EnvLLMProvider
from uni_agent.agent.memory_llm_search import run_memory_search_llm
from uni_agent.agent.orchestrator import StreamEventCallback
from uni_agent.config.settings import Settings, get_settings
from uni_agent.observability.client_session import (
    SessionStore,
    build_session_context_for_planner,
    task_result_to_entry,
)
from uni_agent.observability.local_memory import (
    MemoryPersistReport,
    count_memory_records,
    persist_incremental_for_client_session,
    search_memory_directory,
)

_memory_activity_gen = 0
_memory_idle_lock = threading.Lock()


def _stream_delegation(ev: dict[str, Any]) -> dict[str, Any] | None:
    d = ev.get("delegation")
    return d if isinstance(d, dict) else None


def _is_sub_agent_stream(ev: dict[str, Any]) -> bool:
    d = _stream_delegation(ev)
    return bool(d and d.get("phase") == "child")


def _indent_for_stream(ev: dict[str, Any]) -> str:
    return "    " if _is_sub_agent_stream(ev) else "  "


def _human_stream_event(ev: dict[str, Any]) -> None:
    """Pretty progress on stderr (stdout reserved for final JSON blocks in REPL)."""
    sub = _is_sub_agent_stream(ev)
    ind = _indent_for_stream(ev)
    de = _stream_delegation(ev)
    parent_rid = de.get("parent_run_id") if de else None

    t = ev.get("type")
    if t == "run_begin":
        if sub:
            typer.secho(f"{ind}───────── sub-agent ─────────", fg=typer.colors.BLUE, dim=True, err=True)
            typer.secho(
                f"{ind}· parent_run_id={parent_rid}  →  child_run_id={ev.get('run_id')}",
                fg=typer.colors.BLUE,
                err=True,
            )
            typer.secho(f"{ind}· task={ev.get('task')!r}", dim=True, err=True)
        else:
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
        label = "sub round" if sub else "round"
        typer.secho(f"{ind}· {label} {ev.get('round')}{extra}: " + ", ".join(parts), err=True)
    elif t == "plan_empty":
        typer.secho(
            f"{ind}· planner returned empty plan (failed_rounds={ev.get('failed_rounds_so_far')})",
            fg=typer.colors.YELLOW,
            err=True,
        )
    elif t == "step_finished":
        step = ev.get("step") or {}
        sid = step.get("id", "")
        tool = step.get("tool", "")
        st = step.get("status", "")
        typer.secho(f"{ind}· step {sid} [{tool}] → {st}", err=True)
        out = (step.get("output") or "").strip()
        if out:
            if not sub and tool == "delegate_task":
                typer.secho(
                    f"{ind}  (tool return text; nested sub-agent activity is shown above between "
                    "sub-agent banners)",
                    fg=typer.colors.BLUE,
                    dim=True,
                    err=True,
                )
                max_lines, max_chars = 8, 1200
            else:
                max_lines, max_chars = 12, 2000
            head = out.splitlines()[:max_lines]
            body = "\n".join(head)
            if len(out.splitlines()) > max_lines or len(body) > max_chars:
                body = body[:max_chars] + "\n... [truncated]"
            for line in body.splitlines():
                typer.secho(f"{ind}  {line}", dim=True, err=True)
        errd = step.get("error_detail")
        if errd:
            typer.secho(f"{ind}    error: {errd}", fg=typer.colors.RED, err=True)
    elif t == "round_completed":
        msg = f"{ind}· sub round {ev.get('round')} completed" if sub else f"{ind}· round {ev.get('round')} completed"
        typer.secho(msg, fg=typer.colors.GREEN, err=True)
    elif t == "round_failed":
        typer.secho(
            f"{ind}· round {ev.get('round')} failed (replan; "
            f"failed_rounds={ev.get('failed_rounds_so_far')}/{ev.get('max_failed_rounds')})",
            fg=typer.colors.YELLOW,
            err=True,
        )
    elif t == "conclusion_begin":
        typer.secho(f"{ind}· generating conclusion…", dim=True, err=True)
    elif t == "conclusion_done":
        concl = ev.get("conclusion") or ""
        if sub:
            typer.secho(f"\n{ind}── sub-agent conclusion ──", fg=typer.colors.BLUE, err=True)
        else:
            typer.secho("\n── conclusion ──", fg=typer.colors.MAGENTA, err=True)
        for line in (concl or "").splitlines() or [""]:
            typer.secho(f"{ind}{line}", err=True)
    elif t == "run_end":
        rid = ev.get("run_id")
        st = ev.get("status")
        if sub:
            typer.secho(
                f"\n{ind}■ sub-agent finished status={st} run_id={rid}\n",
                fg=typer.colors.BLUE,
                bold=True,
                err=True,
            )
            typer.secho(f"{ind}  (parent run continues)\n", dim=True, err=True)
        else:
            typer.secho(
                f"\n■ finished status={st} run_id={rid}\n",
                bold=True,
                err=True,
            )
    else:
        typer.secho(json.dumps(ev, ensure_ascii=False), err=True)


def _print_help() -> None:
    typer.echo(
        """
Commands:
  <text>          Run as a task (same as uni-agent run).
  load <id>       Load session by id or id prefix (from session store).
  new             Start a new session (current one saved first if it has entries).
  sessions        List recent session files.
  status          Show current session id and run count.
  memory search <q>   Search memory (LLM keywords→L0→L1 answer when configured; else substring).
  memory status       Show memory dir, record count, extraction checkpoint.
  memory extract      Flush new session entries to memory immediately.
  help            This help.
  exit / quit     Leave the client.

Environment matches ``uni-agent run`` (see UNI_AGENT_* in settings).
""".strip()
    )


def _echo_memory_flush_summary(settings: Settings, report: MemoryPersistReport) -> None:
    """Human-readable memory persist summary on stderr (does not clutter task JSON on stdout)."""
    if report.written == 0:
        return
    typer.secho("", err=True)
    typer.secho("── memory updated ──", fg=typer.colors.MAGENTA, err=True)
    typer.secho(f"  directory: {settings.memory_dir}", dim=True, err=True)
    typer.secho(f"  checkpoint → {report.new_checkpoint} (flushed {report.written} record(s))", err=True)
    for it in report.items:
        label = "new" if it.action == "created" else "update"
        typer.secho(
            f"  · [{label}] run_id={it.run_id}  file={it.file_name}",
            err=True,
        )
        typer.secho(f"    L0: {it.l0_preview}", dim=True, err=True)


def _schedule_idle_memory_flush(session, store, settings) -> None:
    """After a quiet period at the prompt, persist turns not yet written to ``memory_dir``."""
    if not settings.memory_extract_enabled or settings.memory_idle_extract_seconds <= 0:
        return
    expected = _memory_activity_gen

    def worker() -> None:
        time.sleep(settings.memory_idle_extract_seconds)
        if _memory_activity_gen != expected:
            return
        with _memory_idle_lock:
            if _memory_activity_gen != expected:
                return
            report = persist_incremental_for_client_session(memory_dir=settings.memory_dir, session=session)
            if report.written:
                store.save(session)
                _echo_memory_flush_summary(settings, report)

    threading.Thread(target=worker, daemon=True).start()


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

        if lower.startswith("memory "):
            rest = line[7:].strip()
            rlow = rest.lower()
            if rlow.startswith("search "):
                q = rest[7:].strip()
                if not q:
                    typer.secho("Usage: memory search <query>", fg=typer.colors.RED)
                    continue
                model_settings = None
                if settings.llm_temperature is not None:
                    model_settings = {"temperature": settings.llm_temperature}
                prov = EnvLLMProvider(
                    settings.model_name,
                    openai_base_url=settings.openai_base_url,
                    openai_api_key=settings.openai_api_key,
                )
                if settings.memory_search_use_llm and prov.is_available():
                    try:
                        typer.echo(
                            run_memory_search_llm(
                                q,
                                settings.memory_dir,
                                prov,
                                model_settings=model_settings,
                                keyword_retries=settings.llm_retries,
                                max_hits=settings.memory_search_max_hits,
                            )
                        )
                    except Exception as exc:
                        typer.secho(
                            f"[memory search LLM error, substring fallback] {exc}",
                            fg=typer.colors.YELLOW,
                            err=True,
                        )
                        typer.echo(search_memory_directory(settings.memory_dir, q))
                else:
                    typer.echo(search_memory_directory(settings.memory_dir, q))
                continue
            if rlow == "status":
                nrec = count_memory_records(settings.memory_dir)
                typer.echo(
                    f"memory_dir={settings.memory_dir}  records={nrec}  "
                    f"checkpoint={session.memory_last_extracted_index}/{len(session.entries)}"
                )
                continue
            if rlow == "extract":
                with _memory_idle_lock:
                    report = persist_incremental_for_client_session(
                        memory_dir=settings.memory_dir, session=session
                    )
                    store.save(session)
                if report.written:
                    _echo_memory_flush_summary(settings, report)
                else:
                    typer.secho("(memory extract: nothing new to flush)", dim=True, err=True)
                continue
            typer.secho(
                "Usage: memory search <query> | memory status | memory extract",
                fg=typer.colors.RED,
            )
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
        global _memory_activity_gen
        _memory_activity_gen += 1

        task = line
        started = datetime.now(timezone.utc).isoformat()
        from uni_agent.bootstrap import build_orchestrator

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

        _schedule_idle_memory_flush(session, store, settings)
