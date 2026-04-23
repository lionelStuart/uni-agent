"""Guard: concurrency guidance doc stays present."""

from __future__ import annotations

from pathlib import Path


def test_sdk_concurrency_doc_mentions_key_guidance() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / "docs" / "sdk-concurrency.md").read_text(encoding="utf-8")
    for t in (
        "asyncio",
        "Semaphore",
        "同一",
        "Orchestrator",
    ):
        assert t in text, f"missing: {t}"
