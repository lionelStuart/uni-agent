from __future__ import annotations

from typing import Any

import pytest

from uni_agent.observability.streaming import compose_stream_callbacks


def test_compose_stream_callbacks_none_only() -> None:
    assert compose_stream_callbacks([]) is None
    assert compose_stream_callbacks([None, None]) is None


def test_compose_stream_callbacks_keeps_single() -> None:
    calls: list[dict[str, Any]] = []

    def cb(ev: dict[str, Any]) -> None:
        calls.append(ev)

    merged = compose_stream_callbacks([None, cb, None])
    assert merged is cb
    merged({"type": "test"})
    assert calls == [{"type": "test"}]


def test_compose_stream_callbacks_multiple() -> None:
    c1_calls: list[dict[str, Any]] = []
    c2_calls: list[dict[str, Any]] = []

    def c1(ev: dict[str, Any]) -> None:
        c1_calls.append(ev)

    def c2(ev: dict[str, Any]) -> None:
        c2_calls.append(ev)

    merged = compose_stream_callbacks([c1, c2])
    assert merged is not None
    merged({"type": "ok"})
    assert c1_calls == [{"type": "ok"}]
    assert c2_calls == [{"type": "ok"}]


def test_compose_stream_callbacks_swallow_callback_exception() -> None:
    c1_calls: list[dict[str, Any]] = []

    def c1(_: dict[str, Any]) -> None:
        raise RuntimeError("boom")

    def c2(ev: dict[str, Any]) -> None:
        c1_calls.append(ev)

    merged = compose_stream_callbacks([c1, c2])
    assert merged is not None
    merged({"type": "still-runs"})
    assert c1_calls == [{"type": "still-runs"}]
