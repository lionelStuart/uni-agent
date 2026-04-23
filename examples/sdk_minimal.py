#!/usr/bin/env python3
"""
Minimal end-to-end SDK example: AgentConfig + create_client + run.

Run from the repository root after installing the package:

    pip install -e '.[dev]'
    python examples/sdk_minimal.py

Uses ``planner_backend=heuristic`` and a read-only task so a network LLM
is not required. Execution events (NDJSON-style dicts) go to stderr; the
final TaskResult JSON goes to stdout. Event schema: ``docs/sdk-streaming.md``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from uni_agent.sdk import AgentConfig, create_client

# Repository root: parent of examples/
REPO_ROOT = Path(__file__).resolve().parent.parent


def on_event(event: dict) -> None:
    print(json.dumps(event, ensure_ascii=False), file=sys.stderr, flush=True)


def main() -> int:
    config = AgentConfig(
        name="ExampleAgent",
        description="SDK smoke run from examples/sdk_minimal.py (read-only).",
        workspace=REPO_ROOT,
        skills_dir=REPO_ROOT / "skills",
        storage_namespace="example-sdk",
        planner_backend="heuristic",
    )
    client = create_client(config, on_event=on_event)
    # Heuristic planner recognizes file paths in the task and plans file_read.
    result = client.run("read README.md")
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    return 0 if result.status.value == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
