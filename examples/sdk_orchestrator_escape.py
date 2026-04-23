#!/usr/bin/env python3
"""
Use ``AgentClient.orchestrator`` to read the live ``Orchestrator`` (e.g. tool list).

From repo root, after ``pip install -e '.[dev]'``:

    python examples/sdk_orchestrator_escape.py

See ``docs/sdk-runtime.md`` (escape hatch, same object as ``run``/``replay``).
"""

from __future__ import annotations

from pathlib import Path

from uni_agent.sdk import AgentConfig, create_client

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    config = AgentConfig(
        name="EscapeExample",
        description="read-only: inspect tool_registry via .orchestrator",
        workspace=REPO_ROOT,
        skills_dir=REPO_ROOT / "skills",
        storage_namespace="example-orchestrator-escape",
        planner_backend="heuristic",
    )
    client = create_client(config)
    tools = client.orchestrator.tool_registry.list_tools()
    print(f"registered_tools={len(tools)}")
    for spec in tools[:5]:
        print(f"  - {spec.name}")
    if len(tools) > 5:
        print("  - …")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
