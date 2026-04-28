from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from uni_agent.observability.logging import get_logger
from uni_agent.observability.sqlite_store import ObservabilitySqliteStore
from uni_agent.observability.streaming import ObservabilityEventProjector

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
        self._projector = ObservabilityEventProjector(
            session_id=session_id,
            source=source,
            workspace=workspace,
        )
        self._log = get_logger(__name__)

    def __call__(self, event: dict[str, Any]) -> None:
        observed_at = datetime.now(timezone.utc).isoformat()
        projected = self._projector.project(event, observed_at=observed_at)
        event_type = str(projected.get("type") or "unknown")
        current_run_id = projected.get("run_id")
        current_session_id = str(projected.get("session_id"))
        try:
            self._store.record_event(
                session_id=current_session_id,
                run_id=current_run_id if isinstance(current_run_id, str) else None,
                event_index=int(projected["event_index"]),
                event=projected,
                source=str(projected["source"]),
                workspace=str(projected["workspace"]),
                observed_at=observed_at,
            )
        except Exception:
            self._log.exception(
                "observability_sqlite_record_failed",
                session_id=current_session_id,
                run_id=current_run_id,
                event_type=event_type,
            )


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
