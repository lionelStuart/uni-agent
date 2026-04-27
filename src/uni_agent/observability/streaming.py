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
