from __future__ import annotations

from pathlib import Path

from uni_agent.config.settings import Settings
from uni_agent.observability.client_session import ClientSessionRunEntry, SessionStore
from uni_agent.observability.sqlite_sink import SqliteStreamRecorder
from uni_agent.observability.sqlite_store import ObservabilitySqliteStore
from uni_agent.shared.models import TaskResult, TaskStatus


def test_settings_anchor_observability_sqlite_under_workspace(tmp_path: Path) -> None:
    settings = Settings(workspace=tmp_path, skills_dir=tmp_path / "skills")
    assert settings.observability_sqlite_path == (
        tmp_path / ".uni-agent" / "observability" / "observability.db"
    ).resolve()


def test_sqlite_stream_and_task_store_persist_run_data(tmp_path: Path) -> None:
    db = ObservabilitySqliteStore(tmp_path / "obs.db")
    sink = SqliteStreamRecorder(
        db,
        session_id="sess-1",
        source="sdk",
        workspace=str(tmp_path),
    )

    sink({"type": "run_begin", "run_id": "run-1", "task": "inspect repo"})
    sink({"type": "round_plan", "round": 1, "steps": [{"id": "s1", "tool": "search_workspace"}]})
    sink({"type": "run_end", "run_id": "run-1", "status": "completed", "orchestrator_failed_rounds": 0})

    result = TaskResult(
        run_id="run-1",
        task="inspect repo",
        status=TaskStatus.COMPLETED,
        answer="done",
        conclusion="all good",
        output="ok",
    )
    db.save_task_result(result, session_id="sess-1", source="sdk", workspace=str(tmp_path))

    sessions = db.list_sessions()
    assert [item.session_id for item in sessions] == ["sess-1"]
    assert sessions[0].run_count == 1

    runs = db.list_runs("sess-1")
    assert len(runs) == 1
    assert runs[0].run_id == "run-1"
    assert runs[0].conclusion == "all good"

    events = db.list_events("sess-1", "run-1")
    assert [item["event_type"] for item in events][-1] == "run_begin"


def test_session_store_syncs_client_session_to_sqlite(tmp_path: Path) -> None:
    db = ObservabilitySqliteStore(tmp_path / "obs.db")
    store = SessionStore(tmp_path / "sessions", sqlite_store=db)
    session = store.new_session(tmp_path)
    session.entries.append(
        ClientSessionRunEntry(run_id="run-2", task="hello", status="completed", conclusion="ok")
    )
    store.save(session)

    sessions = db.list_sessions()
    assert sessions[0].session_id == session.id
    payload = db.get_session_payload(session.id)
    assert payload is not None
    assert payload["entries"][0]["task"] == "hello"
