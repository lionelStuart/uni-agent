import json
from pathlib import Path

import pytest

from uni_agent.agent.plan_loader import load_plan_file
from uni_agent.bootstrap import build_orchestrator


def test_delegate_task_creates_two_runs_and_child_has_parent_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = tmp_path / "runs"
    skills = tmp_path / "skills"
    ws = tmp_path / "ws"
    runs.mkdir()
    skills.mkdir()
    ws.mkdir()
    (ws / "hello.txt").write_text("HELLO_DELEGATE", encoding="utf-8")

    monkeypatch.setenv("UNI_AGENT_TASK_LOG_DIR", str(runs))
    monkeypatch.setenv("UNI_AGENT_SKILLS_DIR", str(skills))
    monkeypatch.setenv("UNI_AGENT_WORKSPACE", str(ws))
    monkeypatch.setenv("UNI_AGENT_PLANNER_BACKEND", "heuristic")

    plan_path = tmp_path / "plan.yaml"
    plan_path.write_text(
        """
steps:
  - id: step-1
    description: delegate read
    tool: delegate_task
    arguments:
      task: read hello.txt
""".strip(),
        encoding="utf-8",
    )

    orch = build_orchestrator(stream_event=None)
    result = orch.run("parent wrapper", plan_override=load_plan_file(plan_path))

    assert result.status.value == "completed"
    assert result.run_id
    step_out = result.plan[0].output
    assert "CHILD_RUN_ID=" in step_out
    assert f"PARENT_RUN_ID={result.run_id}" in step_out
    assert "HELLO_DELEGATE" in step_out

    json_files = list(runs.glob("*.json"))
    assert len(json_files) == 2

    parent_record = json.loads((runs / f"{result.run_id}.json").read_text(encoding="utf-8"))
    assert parent_record["result"]["parent_run_id"] is None

    child_line = next(line for line in step_out.splitlines() if line.startswith("CHILD_RUN_ID="))
    child_id = child_line.split("=", 1)[1].strip()
    assert child_id
    child_record = json.loads((runs / f"{child_id}.json").read_text(encoding="utf-8"))
    assert child_record["result"]["parent_run_id"] == result.run_id


def test_delegate_stream_events_include_delegation_meta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = tmp_path / "runs"
    skills = tmp_path / "skills"
    ws = tmp_path / "ws"
    runs.mkdir()
    skills.mkdir()
    ws.mkdir()
    (ws / "hello.txt").write_text("x", encoding="utf-8")

    monkeypatch.setenv("UNI_AGENT_TASK_LOG_DIR", str(runs))
    monkeypatch.setenv("UNI_AGENT_SKILLS_DIR", str(skills))
    monkeypatch.setenv("UNI_AGENT_WORKSPACE", str(ws))
    monkeypatch.setenv("UNI_AGENT_PLANNER_BACKEND", "heuristic")

    plan_path = tmp_path / "plan.yaml"
    plan_path.write_text(
        """
steps:
  - id: step-1
    tool: delegate_task
    description: d
    arguments:
      task: read hello.txt
""".strip(),
        encoding="utf-8",
    )

    events: list[dict] = []

    def capture(ev: dict) -> None:
        events.append(ev)

    orch = build_orchestrator(stream_event=capture)
    orch.run("p", plan_override=load_plan_file(plan_path))

    child_phases = [e for e in events if e.get("delegation", {}).get("phase") == "child"]
    assert child_phases, "expected wrapped child stream events"
    parent_rid = next(
        e["run_id"] for e in events if e.get("type") == "run_begin" and "delegation" not in e
    )
    for e in child_phases:
        assert e["delegation"].get("parent_run_id") == parent_rid


def test_delegate_child_respects_max_failed_rounds_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = tmp_path / "runs"
    skills = tmp_path / "skills"
    ws = tmp_path / "ws"
    runs.mkdir()
    skills.mkdir()
    ws.mkdir()

    monkeypatch.setenv("UNI_AGENT_TASK_LOG_DIR", str(runs))
    monkeypatch.setenv("UNI_AGENT_SKILLS_DIR", str(skills))
    monkeypatch.setenv("UNI_AGENT_WORKSPACE", str(ws))
    monkeypatch.setenv("UNI_AGENT_PLANNER_BACKEND", "heuristic")
    monkeypatch.setenv("UNI_AGENT_DELEGATE_MAX_FAILED_ROUNDS", "1")

    plan_path = tmp_path / "plan.yaml"
    plan_path.write_text(
        """
steps:
  - id: step-1
    tool: delegate_task
    description: d
    arguments:
      task: read missing999.txt
""".strip(),
        encoding="utf-8",
    )

    orch = build_orchestrator(stream_event=None)
    result = orch.run("p", plan_override=load_plan_file(plan_path))
    assert result.status.value == "completed"
    step_out = result.plan[0].output
    child_line = next(line for line in step_out.splitlines() if line.startswith("CHILD_RUN_ID="))
    child_id = child_line.split("=", 1)[1].strip()
    child_record = json.loads((runs / f"{child_id}.json").read_text(encoding="utf-8"))
    assert child_record["result"]["orchestrator_failed_rounds"] >= 1


def test_delegate_readonly_child_exposes_subset_tools_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = tmp_path / "runs"
    skills = tmp_path / "skills"
    ws = tmp_path / "ws"
    runs.mkdir()
    skills.mkdir()
    ws.mkdir()
    (ws / "hello.txt").write_text("ro", encoding="utf-8")

    monkeypatch.setenv("UNI_AGENT_TASK_LOG_DIR", str(runs))
    monkeypatch.setenv("UNI_AGENT_SKILLS_DIR", str(skills))
    monkeypatch.setenv("UNI_AGENT_WORKSPACE", str(ws))
    monkeypatch.setenv("UNI_AGENT_PLANNER_BACKEND", "heuristic")
    monkeypatch.setenv("UNI_AGENT_DELEGATE_TOOL_PROFILE", "readonly")

    plan_path = tmp_path / "plan.yaml"
    plan_path.write_text(
        """
steps:
  - id: step-1
    tool: delegate_task
    description: d
    arguments:
      task: read hello.txt
""".strip(),
        encoding="utf-8",
    )

    orch = build_orchestrator(stream_event=None)
    result = orch.run("p", plan_override=load_plan_file(plan_path))
    assert result.status.value == "completed"
    step_out = result.plan[0].output
    child_line = next(line for line in step_out.splitlines() if line.startswith("CHILD_RUN_ID="))
    child_id = child_line.split("=", 1)[1].strip()
    child_record = json.loads((runs / f"{child_id}.json").read_text(encoding="utf-8"))
    names = set(child_record["result"]["available_tools"])
    assert names == {"file_read", "search_workspace", "memory_search", "command_lookup"}
    assert "shell_exec" not in names
    assert "delegate_task" not in names
