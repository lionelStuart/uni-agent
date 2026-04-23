"""Guard: SDK runtime / orchestrator relationship doc stays present."""

from __future__ import annotations

from pathlib import Path


def test_sdk_runtime_doc_mentions_assembly() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / "docs" / "sdk-runtime.md").read_text(encoding="utf-8")
    for t in (
        "build_orchestrator",
        "AgentClient",
        "orchestrator",
        "MagicMock",
    ):
        assert t in text, f"missing: {t}"
