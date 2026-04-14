import json
import os
from pathlib import Path

from typer.testing import CliRunner

from uni_agent.cli import main


def test_replay_jsonl_format(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("UNI_AGENT_TASK_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("UNI_AGENT_PLANNER_BACKEND", "heuristic")
    cwd = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(cwd)

    runner = CliRunner()
    invoke = runner.invoke(main.app, ["run", "read README.md"], env={**os.environ})
    assert invoke.exit_code == 0, invoke.stdout + invoke.stderr

    payload = json.loads(invoke.stdout)
    run_id = payload["run_id"]
    assert run_id

    replay = runner.invoke(main.app, ["replay", run_id, "--format", "jsonl"], env={**os.environ})
    assert replay.exit_code == 0, replay.stdout + replay.stderr

    lines = [line for line in replay.stdout.splitlines() if line.strip()]
    assert lines
    last = json.loads(lines[-1])
    assert last["type"] == "task_result"
    assert last["run_id"] == run_id
