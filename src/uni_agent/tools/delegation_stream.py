"""Stream callback helpers for child (delegated) runs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


StreamEventCallback = Callable[[dict[str, Any]], None]


def wrap_child_stream(
    parent_run_id: str | None,
    inner: StreamEventCallback | None,
) -> StreamEventCallback | None:
    """Attach ``delegation`` metadata so parent/child NDJSON lines are distinguishable."""
    if inner is None:
        return None

    def _wrapped(event: dict[str, Any]) -> None:
        ev = dict(event)
        extra = {"phase": "child", "parent_run_id": parent_run_id}
        if "delegation" in ev and isinstance(ev["delegation"], dict):
            ev["delegation"] = {**ev["delegation"], **extra}
        else:
            ev["delegation"] = extra
        inner(ev)

    return _wrapped
