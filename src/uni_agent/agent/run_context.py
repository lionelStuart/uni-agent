"""Process-wide context for the active orchestrator run (run id, session text).

Used by ``delegate_task`` to read the parent ``run_id`` and optional session snapshot.
"""

from __future__ import annotations

import contextvars

_run_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "uni_agent_current_run_id", default=None
)
_session_context_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "uni_agent_session_context", default=None
)


def set_run_id(run_id: str) -> contextvars.Token[str | None]:
    return _run_id_var.set(run_id)


def reset_run_id(token: contextvars.Token[str | None]) -> None:
    _run_id_var.reset(token)


def get_run_id() -> str | None:
    return _run_id_var.get()


def set_session_context(session_context: str | None) -> contextvars.Token[str | None]:
    return _session_context_var.set(session_context)


def reset_session_context(token: contextvars.Token[str | None]) -> None:
    _session_context_var.reset(token)


def get_session_context() -> str | None:
    return _session_context_var.get()
