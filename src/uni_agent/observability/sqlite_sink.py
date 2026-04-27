from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from uni_agent.observability.logging import get_logger
from uni_agent.observability.sqlite_store import ObservabilitySqliteStore
from uni_agent.observability.streaming import enrich_stream_event

StreamEventCallback = Callable[[dict[str, Any]], None]


class SqliteStreamRecorder:
    def __init__(
        self,
        store: ObservabilitySqliteStore,
        *,
        session_id: str | None,
        source: str,
        workspace: str,
    ) -> None:
        self._store = store
        self._explicit_session_id = session_id.strip() if session_id else None
        self._source = source
        self._workspace = workspace
        self._event_index = 0
        self._run_stack: list[tuple[str, str]] = []
        self._log = get_logger(__name__)

    def __call__(self, event: dict[str, Any]) -> None:
        observed_at = datetime.now(timezone.utc).isoformat()
        event_type = str(event.get("type") or "unknown")
        current_run_id = self._resolve_run_id(event_type, event)
        current_session_id = self._resolve_session_id(event_type, event, current_run_id)
        enriched = enrich_stream_event(
            event,
            session_id=current_session_id,
            source=self._source,
            workspace=self._workspace,
            observed_at=observed_at,
        )
        self._event_index += 1
        try:
            self._store.record_event(
                session_id=current_session_id,
                run_id=current_run_id,
                event_index=self._event_index,
                event=enriched,
                source=self._source,
                workspace=self._workspace,
                observed_at=observed_at,
            )
        except Exception:
            self._log.exception(
                "observability_sqlite_record_failed",
                session_id=current_session_id,
                run_id=current_run_id,
                event_type=event_type,
            )
        self._update_stack(event_type, current_run_id, current_session_id)

    def default_session_id_for_run(self, run_id: str) -> str:
        return self._explicit_session_id or f"run-{run_id}"

    def _resolve_run_id(self, event_type: str, event: dict[str, Any]) -> str | None:
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
        if event_type == "run_begin" and run_id:
            return f"run-{run_id}"
        if run_id:
            return f"run-{run_id}"
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


def build_sqlite_stream_handler(
    store: ObservabilitySqliteStore | None,
    *,
    session_id: str | None,
    source: str,
    workspace: str,
) -> SqliteStreamRecorder | None:
    if store is None:
        return None
    return SqliteStreamRecorder(store, session_id=session_id, source=source, workspace=workspace)
