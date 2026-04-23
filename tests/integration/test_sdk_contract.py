"""SDK integration contract: real `build_orchestrator` via `create_client` + heuristic `run` (Round 6)."""

from __future__ import annotations

from pathlib import Path

from uni_agent.sdk import AgentConfig, create_client


def test_create_client_run_heuristic_reads_workspace_file(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "note.txt").write_text("ok-sdk", encoding="utf-8")
    skills = tmp_path / "skills"
    skills.mkdir()

    cfg = AgentConfig(
        name="Contract",
        description="round6",
        workspace=workspace,
        skills_dir=skills,
        planner_backend="heuristic",
        storage_namespace="sdk-round6",
    )
    client = create_client(cfg)
    result = client.run("read the file note.txt")
    assert result.status.value == "completed"
    text = " ".join(
        [f"{s.tool} {s.description} {s.output}" for s in result.plan]
    )
    assert "ok-sdk" in text or "file_read" in text
