"""Stream utilities for orchestrator event callbacks."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, Callable

from uni_agent.observability.logging import get_logger

StreamEventCallback = Callable[[dict[str, Any]], None]


def compose_stream_callbacks(
    callbacks: Iterable[StreamEventCallback | None],
) -> StreamEventCallback | None:
    """Compose 0/1/N callbacks into a single callback.

    - `None` callbacks are ignored.
    - Callback exceptions are caught and logged, never propagated.
    """
    active: list[StreamEventCallback] = [cb for cb in callbacks if cb is not None]
    if not active:
        return None
    if len(active) == 1:
        return active[0]

    log = get_logger(__name__)

    def _merged(event: dict[str, Any]) -> None:
        for cb in active:
            try:
                cb(event)
            except Exception:
                log.exception("stream_callback_failed", callback=str(cb))

    return _merged


def enrich_stream_event(
    event: dict[str, Any],
    *,
    session_id: str,
    source: str,
    workspace: str,
    observed_at: str | None = None,
) -> dict[str, Any]:
    enriched = dict(event)
    enriched.setdefault("session_id", session_id)
    enriched.setdefault("source", source)
    enriched.setdefault("workspace", workspace)
    enriched.setdefault("observed_at", observed_at or datetime.now(timezone.utc).isoformat())
    return enriched


class ObservabilityEventProjector:
    """Stateful projection from internal stream events to a stable observability event shape."""

    def __init__(self, *, session_id: str | None, source: str, workspace: str) -> None:
        self._explicit_session_id = session_id.strip() if session_id else None
        self._source = source
        self._workspace = workspace
        self._event_index = 0
        self._run_stack: list[tuple[str, str]] = []

    def project(self, event: dict[str, Any], *, observed_at: str | None = None) -> dict[str, Any]:
        observed = observed_at or datetime.now(timezone.utc).isoformat()
        event_type = str(event.get("type") or "unknown")
        run_id = self._resolve_run_id(event)
        session_id = self._resolve_session_id(event_type, event, run_id)
        self._event_index += 1
        raw = enrich_stream_event(
            event,
            session_id=session_id,
            source=self._source,
            workspace=self._workspace,
            observed_at=observed,
        )
        projected = {
            "schema_version": 1,
            "event_index": self._event_index,
            "event_id": f"{session_id}:{self._event_index}",
            "type": event_type,
            "session_id": session_id,
            "run_id": run_id,
            "parent_run_id": self._resolve_parent_run_id(raw),
            "source": self._source,
            "workspace": self._workspace,
            "observed_at": observed,
            "task": self._resolve_task(raw),
            "status": self._resolve_status(raw),
            "round": raw.get("round"),
            "selected_skills": raw.get("selected_skills") if isinstance(raw.get("selected_skills"), list) else [],
            "delegation": raw.get("delegation") if isinstance(raw.get("delegation"), dict) else None,
            "step": self._project_step(raw.get("step")),
            "answer": raw.get("answer") if isinstance(raw.get("answer"), str) else None,
            "conclusion": raw.get("conclusion") if isinstance(raw.get("conclusion"), str) else None,
            "raw": raw,
        }
        self._update_stack(event_type, run_id, session_id)
        return projected

    def _resolve_run_id(self, event: dict[str, Any]) -> str | None:
        run_id = event.get("run_id")
        if isinstance(run_id, str) and run_id.strip():
            return run_id
        if self._run_stack:
            return self._run_stack[-1][0]
        return None

    def _resolve_session_id(self, event_type: str, event: dict[str, Any], run_id: str | None) -> str:
        event_sid = event.get("session_id")
        if isinstance(event_sid, str) and event_sid.strip():
            return event_sid
        if self._run_stack:
            return self._run_stack[0][1]
        if self._explicit_session_id:
            return self._explicit_session_id
        if run_id:
            return f"run-{run_id}"
        if event_type == "run_begin":
            return "session-pending"
        return "session-unknown"

    def _update_stack(self, event_type: str, run_id: str | None, session_id: str) -> None:
        if not run_id:
            return
        if event_type == "run_begin":
            self._run_stack.append((run_id, session_id))
            return
        if event_type == "run_end":
            for idx in range(len(self._run_stack) - 1, -1, -1):
                if self._run_stack[idx][0] == run_id:
                    self._run_stack.pop(idx)
                    break

    def _resolve_parent_run_id(self, event: dict[str, Any]) -> str | None:
        parent_run_id = event.get("parent_run_id")
        if isinstance(parent_run_id, str) and parent_run_id.strip():
            return parent_run_id
        delegation = event.get("delegation")
        if isinstance(delegation, dict):
            val = delegation.get("parent_run_id")
            if isinstance(val, str) and val.strip():
                return val
        return None

    def _resolve_task(self, event: dict[str, Any]) -> str | None:
        task = event.get("task")
        if isinstance(task, str) and task.strip():
            return task
        step = event.get("step")
        if isinstance(step, dict):
            desc = step.get("description")
            if isinstance(desc, str) and desc.strip():
                return desc
        return None

    def _resolve_status(self, event: dict[str, Any]) -> str | None:
        status = event.get("status")
        if isinstance(status, str) and status.strip():
            return status
        step = event.get("step")
        if isinstance(step, dict):
            val = step.get("status")
            if isinstance(val, str) and val.strip():
                return val
        return None

    def _project_step(self, step: Any) -> dict[str, Any] | None:
        if not isinstance(step, dict):
            return None
        return {
            "id": step.get("id"),
            "tool": step.get("tool"),
            "description": step.get("description"),
            "status": step.get("status"),
            "output": step.get("output"),
            "error_detail": step.get("error_detail"),
            "failure_code": step.get("failure_code"),
        }
