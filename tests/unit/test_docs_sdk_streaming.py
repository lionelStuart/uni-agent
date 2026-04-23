"""Guard: streaming event doc stays in sync with documented event types (light check)."""

from __future__ import annotations

from pathlib import Path


def test_sdk_streaming_doc_lists_core_event_types() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / "docs" / "sdk-streaming.md").read_text(encoding="utf-8")
    for t in (
        "run_begin",
        "round_plan",
        "step_finished",
        "run_end",
        "goal_check",
        "delegation",
    ):
        assert t in text, f"missing type mention: {t}"
