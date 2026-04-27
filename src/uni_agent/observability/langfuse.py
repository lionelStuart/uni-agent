"""Optional Langfuse bridge for orchestrator stream events."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

from uni_agent.agent import run_context
from uni_agent.observability.logging import get_logger

from .streaming import StreamEventCallback


class _LangfuseUnavailable:
    pass


def _import_langfuse() -> Any | None:
    try:
        from langfuse import Langfuse  # type: ignore
    except ModuleNotFoundError:
        return None
    return Langfuse


def _safe_repr(value: Any, max_chars: int) -> str:
    text = str(value)
    if len(text) <= max_chars:
        return text
    if max_chars <= 0:
        return ""
    return text[: max_chars - 3] + "..."


def _safe_payload(event: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in ("type", "round", "status", "failed_rounds_so_far", "max_failed_rounds", "orchestrator_failed_rounds", "satisfied", "reason"):
        if key in event:
            payload[key] = event[key]
    if "step" in event and isinstance(event["step"], dict):
        step = event["step"]
        payload["step"] = {
            "id": step.get("id"),
            "tool": step.get("tool"),
            "status": step.get("status"),
            "description": _safe_repr(step.get("description"), 320),
            "failure_code": step.get("failure_code"),
        }
        output = step.get("output") or ""
        if isinstance(output, str):
            payload["step"]["output"] = _safe_repr(output, 300)
        error = step.get("error_detail") or ""
        if isinstance(error, str):
            payload["step"]["error_detail"] = _safe_repr(error, 300)
    if "delegation" in event and isinstance(event["delegation"], dict):
        payload["delegation"] = dict(event["delegation"])
    return payload


def _normalize_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _deterministic_span_key(run_id: str, name: str) -> str:
    return f"{run_id}:{name}:{hashlib.sha1(name.encode('utf-8')).hexdigest()[:8]}"


class _SimpleLangfuseObserver:
    def __init__(
        self,
        *,
        host: str | None,
        public_key: str | None,
        secret_key: str | None,
        debug: bool,
        trace_name: str,
        trace_input_max_chars: int,
    ) -> None:
        self._log = get_logger(__name__)
        Langfuse = _import_langfuse()
        if Langfuse is None:
            self._client = _LangfuseUnavailable()
            return
        try:
            self._client = Langfuse(
                host=host,
                public_key=public_key,
                secret_key=secret_key,
                debug=debug,
            )
        except Exception:
            self._log.exception("langfuse_init_failed")
            self._client = _LangfuseUnavailable()
            return
        self._trace_maker = getattr(self._client, "trace", None)
        self._flush = getattr(self._client, "flush", None)
        self._trace_by_run: dict[str, Any] = {}
        self._span_by_run: dict[str, dict[str, Any]] = {}
        self._trace_input_max_chars = max(0, trace_input_max_chars)
        self._trace_name = trace_name or "uni-agent-run"

    def _enabled(self) -> bool:
        return not isinstance(self._client, _LangfuseUnavailable)

    @staticmethod
    def _as_bool(value: Any) -> bool:
        return bool(value)

    def _trace_name_for(self, run_id: str, task: str) -> str:
        clean_task = _safe_repr(_normalize_text(task), 80)
        return f"{self._trace_name}:{run_id}:{clean_task}"

    def _start_trace(self, event: dict[str, Any], run_id: str) -> None:
        if self._trace_maker is None or run_id in self._trace_by_run:
            return
        task = _safe_repr(event.get("task"), 280)
        input_payload = _safe_payload(event, max_chars=self._trace_input_max_chars)
        try:
            trace = self._trace_maker(
                name=self._trace_name_for(run_id, task),
                input=input_payload,
                metadata={
                    "selected_skills": event.get("selected_skills"),
                    "run_id": run_id,
                },
            )
        except Exception:
            self._log.exception("langfuse_trace_create_failed")
            return
        self._trace_by_run[run_id] = trace
        self._span_by_run[run_id] = {}

    def _create_span(self, trace: Any, *, run_id: str, span_name: str) -> Any | None:
        key = _deterministic_span_key(run_id, span_name)
        span_cache = self._span_by_run.setdefault(run_id, {})
        if key in span_cache:
            return span_cache[key]
        span_factory = getattr(trace, "span", None) or getattr(trace, "start_span", None)
        if span_factory is None:
            return None
        try:
            span = span_factory(name=span_name)
        except Exception:
            self._log.exception("langfuse_span_create_failed", span_name=span_name)
            return None
        span_cache[key] = span
        return span

    def _finalize_span(self, span: Any) -> None:
        end_fn = getattr(span, "end", None)
        if callable(end_fn):
            end_fn()
            return
        complete = getattr(span, "end_span", None)
        if callable(complete):
            complete()

    def _finalize_trace(self, trace: Any) -> None:
        flush_fn = self._flush
        if callable(flush_fn):
            try:
                flush_fn()
            except Exception:
                self._log.exception("langfuse_flush_failed")

    def _scorecard(self, event: dict[str, Any]) -> dict[str, Any]:
        payload = event.copy()
        payload["run_context"] = _normalize_text(run_context.get_run_id())
        return _safe_payload(payload, max_chars=self._trace_input_max_chars)

    def __call__(self, event: dict[str, Any]) -> None:
        if not self._enabled():
            return
        event_type = event.get("type")
        run_id = event.get("run_id") or run_context.get_run_id()
        if not isinstance(run_id, str) or not run_id:
            return

        if event_type == "run_begin":
            self._start_trace(event, run_id)
            return
        trace = self._trace_by_run.get(run_id)
        if trace is None:
            return

        if event_type == "step_finished":
            span = self._create_span(trace, run_id=run_id, span_name="step")
            if span is not None:
                try:
                    span.update(input=_safe_payload(event, max_chars=800))
                    span.update(output=_safe_repr((event.get("step") or {}).get("output"), 1200))
                    span.end()
                except Exception:
                    try:
                        self._finalize_span(span)
                    except Exception:
                        pass
            return

        if event_type in {"round_plan", "round_completed", "round_failed", "goal_check", "plan_empty", "conclusion_begin", "conclusion_done", "run_end"}:
            span_name = event_type
            span = self._create_span(trace, run_id=run_id, span_name=span_name)
            if span is None:
                return
            try:
                span.update(input=_safe_payload(event, max_chars=800))
            except Exception:
                pass
            if event_type in {"round_completed", "round_failed", "conclusion_done", "run_end", "goal_check", "plan_empty"}:
                try:
                    output = event.get("conclusion") or _normalize_text(event.get("error"), "")
                    if output:
                        span.update(output=_safe_repr(output, 1200))
                except Exception:
                    pass
                self._finalize_span(span)

        if event_type == "run_end":
            self._trace_by_run.pop(run_id, None)
            self._span_by_run.pop(run_id, None)
            self._finalize_trace(trace)


def build_langfuse_stream_handler(settings: Any) -> StreamEventCallback | None:
    if not getattr(settings, "observability_langfuse_enabled", False):
        return None
    if _import_langfuse() is None:
        get_logger(__name__).warning("langfuse_dependency_missing")
        return None
    if not settings.observability_langfuse_secret_key and not settings.observability_langfuse_public_key:
        get_logger(__name__).warning(
            "langfuse_credentials_missing",
            public_key_present=bool(settings.observability_langfuse_public_key),
            secret_key_present=bool(settings.observability_langfuse_secret_key),
        )
        return None

    observer = _SimpleLangfuseObserver(
        host=settings.observability_langfuse_host,
        public_key=settings.observability_langfuse_public_key,
        secret_key=settings.observability_langfuse_secret_key,
        debug=getattr(settings, "observability_langfuse_debug", False),
        trace_name=getattr(settings, "observability_langfuse_trace_name", "uni-agent-run"),
        trace_input_max_chars=max(128, int(getattr(settings, "observability_langfuse_trace_input_max_chars", 4000))),
    )
    if not observer._enabled():  # type: ignore[attr-defined]
        return None
    return observer
