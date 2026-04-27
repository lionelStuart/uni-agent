from __future__ import annotations

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from uni_agent.observability.sqlite_store import ObservabilitySqliteStore


def _html_page(*, title: str, body: str) -> bytes:
    doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg: #f6f4ee;
      --panel: #fffdf7;
      --ink: #1f2937;
      --muted: #6b7280;
      --accent: #b45309;
      --border: #e5dccb;
      --ok: #166534;
      --bad: #b91c1c;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Iowan Old Style", "Palatino Linotype", serif; background: linear-gradient(180deg, #f9f6ef, var(--bg)); color: var(--ink); }}
    a {{ color: var(--accent); text-decoration: none; }}
    .layout {{ display: grid; grid-template-columns: 320px 1fr; min-height: 100vh; }}
    .sidebar {{ border-right: 1px solid var(--border); padding: 20px; background: rgba(255,255,255,0.55); backdrop-filter: blur(8px); }}
    .content {{ padding: 24px; }}
    .card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 16px; padding: 16px; margin-bottom: 16px; box-shadow: 0 10px 30px rgba(120, 93, 40, 0.08); }}
    .muted {{ color: var(--muted); }}
    .session-link {{ display: block; padding: 10px 12px; border-radius: 12px; margin-bottom: 8px; background: rgba(255,255,255,0.7); border: 1px solid var(--border); }}
    .status-completed {{ color: var(--ok); }}
    .status-failed {{ color: var(--bad); }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #faf6ed; border: 1px solid var(--border); border-radius: 12px; padding: 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
  </style>
</head>
<body>{body}</body>
</html>"""
    return doc.encode("utf-8")


def render_sessions_page(store: ObservabilitySqliteStore, selected_session_id: str | None) -> bytes:
    sessions = store.list_sessions(limit=100)
    if selected_session_id is None and sessions:
        selected_session_id = sessions[0].session_id
    sidebar = [
        "<div class='sidebar'><h2>Sessions</h2>",
        "<p class='muted'>SQLite-backed observability view.</p>",
    ]
    for sess in sessions:
        status_class = f"status-{html.escape((sess.latest_status or '').lower())}"
        sidebar.append(
            "<a class='session-link' href='/?session={sid}'>"
            "<strong>{sid}</strong><br><span class='muted'>{src} · runs={runs}</span><br>"
            "<span class='{status_class}'>{status}</span></a>".format(
                sid=html.escape(sess.session_id),
                src=html.escape(sess.source),
                runs=sess.run_count,
                status_class=status_class,
                status=html.escape(sess.latest_status or "unknown"),
            )
        )
    sidebar.append("</div>")

    content = ["<div class='content'>"]
    if not selected_session_id:
        content.append("<div class='card'><h2>No sessions</h2><p class='muted'>No observability rows yet.</p></div>")
    else:
        payload = store.get_session_payload(selected_session_id)
        runs = store.list_runs(selected_session_id)
        events = store.list_events(selected_session_id, limit=50)
        content.append(f"<div class='card'><h1>{html.escape(selected_session_id)}</h1>")
        if payload:
            content.append(
                "<div class='grid'>"
                f"<div><strong>Workspace</strong><div class='muted'>{html.escape(str(payload.get('workspace') or ''))}</div></div>"
                f"<div><strong>Entries</strong><div class='muted'>{len(payload.get('entries') or [])}</div></div>"
                f"<div><strong>Updated</strong><div class='muted'>{html.escape(str(payload.get('updated_at') or ''))}</div></div>"
                "</div>"
            )
        content.append("</div>")
        content.append("<div class='card'><h2>Runs</h2><table><thead><tr><th>Run</th><th>Status</th><th>Task</th><th>Finished</th></tr></thead><tbody>")
        for run in runs:
            status_class = f"status-{html.escape(run.status.lower())}"
            content.append(
                "<tr><td>{run_id}</td><td class='{status_class}'>{status}</td><td>{task}</td><td>{finished}</td></tr>".format(
                    run_id=html.escape(run.run_id),
                    status_class=status_class,
                    status=html.escape(run.status),
                    task=html.escape(run.task),
                    finished=html.escape(run.finished_at or run.started_at or ""),
                )
            )
            if run.conclusion or run.error or run.answer:
                detail = run.conclusion or run.error or run.answer or ""
                content.append(
                    f"<tr><td colspan='4'><pre>{html.escape(detail[:4000])}</pre></td></tr>"
                )
        content.append("</tbody></table></div>")
        content.append("<div class='card'><h2>Recent Events</h2>")
        for event in events:
            content.append(
                "<p><strong>#{idx} {etype}</strong> <span class='muted'>{at}</span></p><pre>{payload}</pre>".format(
                    idx=event["event_index"],
                    etype=html.escape(str(event["event_type"])),
                    at=html.escape(str(event["created_at"])),
                    payload=html.escape(json.dumps(event["payload"], ensure_ascii=False, indent=2)[:4000]),
                )
            )
        content.append("</div>")
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
            if parsed.path == "/api/sessions":
                self._json([item.__dict__ for item in store.list_sessions(limit=200)])
                return
            if parsed.path == "/api/runs":
                params = parse_qs(parsed.query)
                session_id = (params.get("session") or [None])[0]
                if not session_id:
                    self._json({"error": "missing session query parameter"}, status=400)
                    return
                self._json([item.__dict__ for item in store.list_runs(session_id)])
                return
            if parsed.path == "/api/events":
                params = parse_qs(parsed.query)
                session_id = (params.get("session") or [None])[0]
                if not session_id:
                    self._json({"error": "missing session query parameter"}, status=400)
                    return
                run_id = (params.get("run") or [None])[0]
                self._json(store.list_events(session_id, run_id, limit=200))
                return
            params = parse_qs(parsed.query)
            selected = (params.get("session") or [None])[0]
            payload = render_sessions_page(store, selected)
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
