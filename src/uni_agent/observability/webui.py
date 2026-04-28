from __future__ import annotations

import html
import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from uni_agent.observability.sqlite_store import ObservabilitySqliteStore

_TEXT_PREVIEW_LIMIT = 4_000


def _escape(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _truncate(text: str | None, limit: int = _TEXT_PREVIEW_LIMIT) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... [truncated]"


def _params_with(params: dict[str, str], **updates: str | None) -> str:
    merged = {k: v for k, v in params.items() if v not in {"", None}}
    for key, value in updates.items():
        if value in {"", None}:
            merged.pop(key, None)
        else:
            merged[key] = value
    return urlencode(merged)


def _status_badge(status: str | None) -> str:
    normalized = (status or "unknown").lower()
    return f"<span class='badge badge-{_escape(normalized)}'>{_escape(status or 'unknown')}</span>"


def _render_block(title: str, text: str | None, *, empty_label: str = "Empty") -> str:
    body = _escape(_truncate(text)) if text else f"<span class='muted'>{_escape(empty_label)}</span>"
    return f"<div class='card'><h3>{_escape(title)}</h3><pre>{body}</pre></div>"


def _render_runs_table(
    runs: list[Any],
    params: dict[str, str],
    *,
    selected_run_id: str | None,
) -> str:
    rows = [
        "<div class='card'><h2>Runs</h2>",
        "<table><thead><tr><th>Run</th><th>Status</th><th>Task</th><th>Finished</th></tr></thead><tbody>",
    ]
    for run in runs:
        query = _params_with(params, run=run.run_id)
        selected = "row-selected" if run.run_id == selected_run_id else ""
        rows.append(
            "<tr class='{selected}'><td><a href='/?{query}'>{run_id}</a></td><td>{status}</td>"
            "<td>{task}</td><td>{finished}</td></tr>".format(
                selected=selected,
                query=query,
                run_id=_escape(run.run_id),
                status=_status_badge(run.status),
                task=_escape(run.task),
                finished=_escape(run.finished_at or run.started_at or ""),
            )
        )
    rows.append("</tbody></table></div>")
    return "".join(rows)


def _render_run_detail(run_detail: dict[str, Any] | None) -> str:
    if run_detail is None:
        return "<div class='card'><h2>Run Detail</h2><p class='muted'>Select a run to inspect input, output, and steps.</p></div>"

    payload = run_detail.get("result_payload") or {}
    plan = payload.get("plan") if isinstance(payload, dict) else None
    plan_rows = [
        "<div class='card'><h2>Plan Steps</h2><table><thead><tr><th>Step</th><th>Tool</th><th>Status</th><th>Description</th></tr></thead><tbody>"
    ]
    for step in plan or []:
        step_id = step.get("id") if isinstance(step, dict) else ""
        tool = step.get("tool") if isinstance(step, dict) else ""
        status = step.get("status") if isinstance(step, dict) else ""
        desc = step.get("description") if isinstance(step, dict) else ""
        plan_rows.append(
            "<tr><td>{step_id}</td><td>{tool}</td><td>{status}</td><td>{desc}</td></tr>".format(
                step_id=_escape(step_id),
                tool=_escape(tool),
                status=_status_badge(status if isinstance(status, str) else None),
                desc=_escape(desc),
            )
        )
        output = step.get("output") if isinstance(step, dict) else ""
        err = step.get("error_detail") if isinstance(step, dict) else ""
        if output or err:
            detail = output or err
            plan_rows.append(f"<tr><td colspan='4'><pre>{_escape(_truncate(detail))}</pre></td></tr>")
    plan_rows.append("</tbody></table></div>")

    cards = [
        "<div class='card'><h2>Run Detail</h2>"
        f"<div class='grid tight'><div><strong>Run</strong><div class='muted'>{_escape(run_detail.get('run_id'))}</div></div>"
        f"<div><strong>Status</strong><div>{_status_badge(run_detail.get('status'))}</div></div>"
        f"<div><strong>Started</strong><div class='muted'>{_escape(run_detail.get('started_at') or '')}</div></div>"
        f"<div><strong>Finished</strong><div class='muted'>{_escape(run_detail.get('finished_at') or '')}</div></div>"
        "</div></div>",
        _render_block("Input / Task", run_detail.get("task"), empty_label="No task text"),
        _render_block("Final Answer", payload.get("answer") if isinstance(payload, dict) else run_detail.get("answer")),
        _render_block(
            "Conclusion",
            payload.get("conclusion") if isinstance(payload, dict) else run_detail.get("conclusion"),
        ),
        _render_block("Output", payload.get("output") if isinstance(payload, dict) else run_detail.get("output")),
        _render_block("Error", payload.get("error") if isinstance(payload, dict) else run_detail.get("error")),
        "".join(plan_rows),
    ]
    return "".join(cards)


def _render_events(events: list[dict[str, Any]]) -> str:
    body = ["<div class='card'><h2>Events</h2>"]
    if not events:
        body.append("<p class='muted'>No events matched the current filters.</p>")
    for event in events:
        payload = event["payload"]
        task = payload.get("task")
        status = payload.get("status")
        body.append(
            "<div class='event'><p><strong>#{idx} {etype}</strong> {status} <span class='muted'>{at}</span></p>"
            "{task}"
            "<pre>{payload}</pre></div>".format(
                idx=_escape(event["event_index"]),
                etype=_escape(event["event_type"]),
                status=_status_badge(status if isinstance(status, str) else None),
                at=_escape(event["created_at"]),
                task=f"<p class='muted'>{_escape(task)}</p>" if task else "",
                payload=_escape(json.dumps(payload, ensure_ascii=False, indent=2)[:_TEXT_PREVIEW_LIMIT]),
            )
        )
    body.append("</div>")
    return "".join(body)


def _render_timeline(payload: dict[str, Any] | None) -> str:
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if not entries:
        return "<div class='card'><h2>Session Timeline</h2><p class='muted'>No persisted client entries for this session yet.</p></div>"
    body = ["<div class='card'><h2>Session Timeline</h2>"]
    for idx, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            continue
        body.append(
            "<div class='timeline-item'><p><strong>{idx}. {task}</strong> {status}</p>"
            "<p class='muted'>run_id={run_id} finished={finished}</p>"
            "<pre>{preview}</pre></div>".format(
                idx=idx,
                task=_escape(entry.get("task")),
                status=_status_badge(entry.get("status") if isinstance(entry.get("status"), str) else None),
                run_id=_escape(entry.get("run_id")),
                finished=_escape(entry.get("finished_at")),
                preview=_escape(
                    _truncate(
                        entry.get("conclusion")
                        or entry.get("output_preview")
                        or entry.get("summary")
                        or ""
                    )
                ),
            )
        )
    body.append("</div>")
    return "".join(body)


def _html_page(*, title: str, body: str) -> bytes:
    doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(title)}</title>
  <style>
    :root {{
      --bg: #f5f1e8;
      --panel: rgba(255, 252, 245, 0.9);
      --ink: #1c2430;
      --muted: #6d7380;
      --accent: #915d12;
      --accent-soft: #eedfc3;
      --border: #dfd2bc;
      --ok: #166534;
      --bad: #b91c1c;
      --pending: #9a6700;
      --shadow: rgba(110, 80, 30, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Iowan Old Style", "Palatino Linotype", serif; background:
      radial-gradient(circle at top left, #fff8ed, transparent 28%),
      linear-gradient(180deg, #fbf7ef, var(--bg)); color: var(--ink); }}
    a {{ color: var(--accent); text-decoration: none; }}
    .layout {{ display: grid; grid-template-columns: 320px 1fr; min-height: 100vh; }}
    .sidebar {{ border-right: 1px solid var(--border); padding: 24px 18px; background: rgba(255,255,255,0.55); backdrop-filter: blur(10px); }}
    .content {{ padding: 24px; }}
    .card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 18px; padding: 18px; margin-bottom: 18px; box-shadow: 0 12px 30px var(--shadow); }}
    .muted {{ color: var(--muted); }}
    .session-link {{ display: block; padding: 12px; border-radius: 14px; margin-bottom: 10px; background: rgba(255,255,255,0.7); border: 1px solid var(--border); }}
    .session-link.is-active {{ background: linear-gradient(180deg, #fff7e8, #fffdf7); border-color: #c89d59; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; border: 1px solid var(--border); }}
    .badge-completed {{ color: var(--ok); border-color: #b9d5c0; background: #eef8f0; }}
    .badge-failed {{ color: var(--bad); border-color: #efc1c1; background: #fdf1f1; }}
    .badge-running, .badge-pending, .badge-partial, .badge-needs_review {{ color: var(--pending); border-color: #ead2a0; background: #fff8e8; }}
    .badge-unknown {{ color: var(--muted); background: #f8f4ec; }}
    form.filters {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; margin-bottom: 14px; }}
    label {{ font-size: 13px; color: var(--muted); display: block; margin-bottom: 4px; }}
    input, select {{ width: 100%; border: 1px solid var(--border); border-radius: 12px; padding: 10px 12px; font: inherit; background: #fffdf8; }}
    button {{ border: 1px solid #c08a3b; border-radius: 12px; padding: 10px 14px; background: linear-gradient(180deg, #fff1d7, #f7deaf); font: inherit; cursor: pointer; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }}
    tr.row-selected {{ background: rgba(240, 222, 187, 0.25); }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #fbf7ef; border: 1px solid var(--border); border-radius: 12px; padding: 12px; margin: 0; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    .grid.tight {{ grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }}
    .event, .timeline-item {{ border-top: 1px solid var(--border); padding-top: 12px; margin-top: 12px; }}
  </style>
</head>
<body>{body}</body>
</html>"""
    return doc.encode("utf-8")


def render_sessions_page(
    store: ObservabilitySqliteStore,
    *,
    selected_session_id: str | None,
    selected_run_id: str | None,
    session_query: str,
    run_query: str,
    source: str | None,
    status: str | None,
    event_type: str | None,
) -> bytes:
    base_params = {
        "q": session_query,
        "run_q": run_query,
        "source": source or "",
        "status": status or "",
        "event_type": event_type or "",
        "session": selected_session_id or "",
        "run": selected_run_id or "",
    }
    sessions = store.search_sessions(limit=100, source=source, status=status, query=session_query or None)
    if selected_session_id is None and sessions:
        selected_session_id = sessions[0].session_id
        base_params["session"] = selected_session_id
    payload = store.get_session_payload(selected_session_id) if selected_session_id else None
    runs = (
        store.list_runs(selected_session_id, status=status, query=run_query or session_query or None)
        if selected_session_id
        else []
    )
    if selected_run_id is None and runs:
        selected_run_id = runs[0].run_id
        base_params["run"] = selected_run_id
    run_detail = store.get_run_detail(selected_run_id) if selected_run_id else None
    events = (
        store.list_events(
            selected_session_id,
            selected_run_id,
            event_type=event_type or None,
            query=run_query or session_query or None,
            limit=80,
        )
        if selected_session_id
        else []
    )

    sidebar = [
        "<div class='sidebar'><h1>Sessions</h1><p class='muted'>SQLite-backed observability explorer.</p>",
        "<form class='filters' method='get'>",
        "<div><label for='q'>Search sessions</label><input id='q' name='q' value='{q}'></div>".format(
            q=_escape(session_query)
        ),
        "<div><label for='source'>Source</label><select id='source' name='source'>"
        "<option value=''>All</option>"
        f"<option value='cli' {'selected' if source == 'cli' else ''}>cli</option>"
        f"<option value='client' {'selected' if source == 'client' else ''}>client</option>"
        f"<option value='sdk' {'selected' if source == 'sdk' else ''}>sdk</option>"
        "</select></div>",
        "<div><label for='status'>Status</label><select id='status' name='status'>"
        "<option value=''>All</option>"
        f"<option value='completed' {'selected' if status == 'completed' else ''}>completed</option>"
        f"<option value='failed' {'selected' if status == 'failed' else ''}>failed</option>"
        f"<option value='running' {'selected' if status == 'running' else ''}>running</option>"
        "</select></div>",
        "<div style='align-self:end'><button type='submit'>Apply</button></div>",
        "</form>",
    ]
    for sess in sessions:
        query = _params_with(base_params, session=sess.session_id, run=None)
        active = "is-active" if sess.session_id == selected_session_id else ""
        sidebar.append(
            "<a class='session-link {active}' href='/?{query}'>"
            "<strong>{sid}</strong><br><span class='muted'>{src} · runs={runs}</span><br>"
            "{status}</a>".format(
                active=active,
                query=query,
                sid=_escape(sess.session_id),
                src=_escape(sess.source),
                runs=sess.run_count,
                status=_status_badge(sess.latest_status),
            )
        )
    sidebar.append("</div>")

    content = ["<div class='content'>"]
    if not selected_session_id:
        content.append("<div class='card'><h2>No sessions</h2><p class='muted'>No observability rows matched the current filters.</p></div>")
    else:
        content.append(
            "<div class='card'><h2>{sid}</h2><div class='grid tight'>"
            "<div><strong>Workspace</strong><div class='muted'>{workspace}</div></div>"
            "<div><strong>Source</strong><div class='muted'>{source}</div></div>"
            "<div><strong>Runs</strong><div class='muted'>{runs}</div></div>"
            "<div><strong>Updated</strong><div class='muted'>{updated}</div></div>"
            "</div></div>".format(
                sid=_escape(selected_session_id),
                workspace=_escape(payload.get("workspace") if isinstance(payload, dict) else ""),
                source=_escape(source or (sessions[0].source if sessions else "")),
                runs=len(runs),
                updated=_escape(payload.get("updated_at") if isinstance(payload, dict) else ""),
            )
        )
        content.append(
            "<div class='card'><h2>Run & Event Filters</h2><form class='filters' method='get'>"
            f"<input type='hidden' name='session' value='{_escape(selected_session_id)}'>"
            "<div><label for='run_q'>Search runs/events</label><input id='run_q' name='run_q' value='{run_q}'></div>"
            "<div><label for='event_type'>Event type</label><select id='event_type' name='event_type'>"
            "<option value=''>All</option>"
            f"<option value='run_begin' {'selected' if event_type == 'run_begin' else ''}>run_begin</option>"
            f"<option value='step_finished' {'selected' if event_type == 'step_finished' else ''}>step_finished</option>"
            f"<option value='answer_done' {'selected' if event_type == 'answer_done' else ''}>answer_done</option>"
            f"<option value='conclusion_done' {'selected' if event_type == 'conclusion_done' else ''}>conclusion_done</option>"
            f"<option value='run_end' {'selected' if event_type == 'run_end' else ''}>run_end</option>"
            "</select></div>"
            f"<input type='hidden' name='q' value='{_escape(session_query)}'>"
            f"<input type='hidden' name='source' value='{_escape(source or '')}'>"
            f"<input type='hidden' name='status' value='{_escape(status or '')}'>"
            "<div style='align-self:end'><button type='submit'>Apply</button></div>"
            "</form></div>".format(run_q=_escape(run_query))
        )
        content.append(_render_runs_table(runs, base_params, selected_run_id=selected_run_id))
        content.append(_render_run_detail(run_detail))
        content.append(_render_timeline(payload))
        content.append(_render_events(events))
    content.append("</div>")
    body = "<div class='layout'>{sidebar}{content}</div>".format(
        sidebar="".join(sidebar),
        content="".join(content),
    )
    return _html_page(title="uni-agent observability", body=body)


def build_webui_handler(store: ObservabilitySqliteStore):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            session_id = (params.get("session") or [None])[0]
            run_id = (params.get("run") or [None])[0]
            session_query = (params.get("q") or [""])[0]
            run_query = (params.get("run_q") or [""])[0]
            source = (params.get("source") or [None])[0] or None
            status = (params.get("status") or [None])[0] or None
            event_type = (params.get("event_type") or [None])[0] or None

            if parsed.path == "/api/sessions":
                self._json(
                    [
                        asdict(item)
                        for item in store.search_sessions(
                            limit=200,
                            source=source,
                            status=status,
                            query=session_query or None,
                        )
                    ]
                )
                return
            if parsed.path == "/api/runs":
                if not session_id:
                    self._json({"error": "missing session query parameter"}, status=400)
                    return
                self._json(
                    [
                        asdict(item)
                        for item in store.list_runs(
                            session_id,
                            status=status,
                            query=run_query or session_query or None,
                        )
                    ]
                )
                return
            if parsed.path == "/api/run":
                if not run_id:
                    self._json({"error": "missing run query parameter"}, status=400)
                    return
                detail = store.get_run_detail(run_id)
                if detail is None:
                    self._json({"error": "run not found"}, status=404)
                    return
                self._json(detail)
                return
            if parsed.path == "/api/events":
                if not session_id:
                    self._json({"error": "missing session query parameter"}, status=400)
                    return
                self._json(
                    store.list_events(
                        session_id,
                        run_id,
                        event_type=event_type,
                        query=run_query or session_query or None,
                        limit=200,
                    )
                )
                return
            payload = render_sessions_page(
                store,
                selected_session_id=session_id,
                selected_run_id=run_id,
                session_query=session_query,
                run_query=run_query,
                source=source,
                status=status,
                event_type=event_type,
            )
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _json(self, payload: Any, *, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve_webui(store: ObservabilitySqliteStore, *, host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), build_webui_handler(store))
    try:
        server.serve_forever()
    finally:
        server.server_close()
