"""Guard: multi-agent manifest doc and API names stay present."""

from __future__ import annotations

from pathlib import Path


def test_sdk_agents_doc_mentions_loader_api() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / "docs" / "sdk-agents.md").read_text(encoding="utf-8")
    for t in (
        "load_agent_configs_from_file",
        "load_agent_registry_from_file",
        "agents",
    ):
        assert t in text, f"missing: {t}"
