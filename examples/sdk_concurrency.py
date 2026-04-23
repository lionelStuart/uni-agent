#!/usr/bin/env python3
"""
Sketches asyncio + in-app limiting around synchronous ``AgentClient.run``.

Run from the repository root after installing the package:

    pip install -e '.[dev]'
    python examples/sdk_concurrency.py

This uses two **separate** ``create_client`` instances so two ``run``\ s may
run in parallel without sharing one ``Orchestrator``. Concurrency is capped
with ``asyncio.Semaphore(2)``. Full rationale: ``docs/sdk-concurrency.md``;
event schema: ``docs/sdk-streaming.md``.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from uni_agent.sdk import AgentConfig, AgentClient, create_client
from uni_agent.shared.models import TaskResult

REPO_ROOT = Path(__file__).resolve().parent.parent


def on_event(_event: dict) -> None:
    # Omit streaming in this sample; use sdk_minimal.py to see events on stderr.
    return


def _config(ns: str) -> AgentConfig:
    return AgentConfig(
        name="ConcurrencySample",
        description="docs/sdk-concurrency example",
        workspace=REPO_ROOT,
        skills_dir=REPO_ROOT / "skills",
        storage_namespace=ns,
        planner_backend="heuristic",
    )


async def main() -> int:
    # Two clients => two Orchestrators; safe for parallel to_thread (see doc).
    c1 = create_client(_config("conc-a"), on_event=on_event)
    c2 = create_client(_config("conc-b"), on_event=on_event)
    sem = asyncio.Semaphore(2)

    async def one(client: AgentClient, task: str) -> TaskResult:
        async with sem:
            return await asyncio.to_thread(client.run, task)

    results = await asyncio.gather(
        one(c1, "read README.md"),
        one(c2, "read pyproject.toml"),
    )
    for tr in results:
        print(tr.status.value, file=sys.stderr, flush=True)
    print(json.dumps([r.model_dump() for r in results], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
