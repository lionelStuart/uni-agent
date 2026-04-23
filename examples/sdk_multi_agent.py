#!/usr/bin/env python3
"""
Load multiple agents from ``examples/agents.example.yaml`` and run one task on ``agent-readonly``.

From repo root (after ``pip install -e '.[dev]'``):

    python examples/sdk_multi_agent.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from uni_agent.sdk import load_agent_registry_from_file

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "examples" / "agents.example.yaml"


def on_event(ev: dict) -> None:
    print(json.dumps(ev, ensure_ascii=False), file=sys.stderr, flush=True)


def main() -> int:
    reg = load_agent_registry_from_file(MANIFEST, on_event=on_event)
    client = reg.get("agent-readonly")
    result = client.run("read README.md")
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    return 0 if result.status.value == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
