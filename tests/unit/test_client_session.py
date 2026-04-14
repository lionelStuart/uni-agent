import json
from pathlib import Path

import pytest

from uni_agent.observability.client_session import (
    ClientSession,
    ClientSessionRunEntry,
    SessionStore,
    build_session_context_for_planner,
    compress_task_result_for_session,
    new_session_id,
    task_result_to_entry,
)
from uni_agent.shared.models import TaskResult, TaskStatus


def test_new_session_id_has_timestamp_and_suffix() -> None:
    sid = new_session_id()
    assert len(sid) > 10
    assert "-" in sid


def test_session_store_round_trip(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    session = store.new_session(tmp_path)
    session.entries.append(
        ClientSessionRunEntry(
            run_id="r1",
            task="hello",
            status="completed",
        )
    )
    store.save(session)
    loaded = store.load(session.id)
    assert loaded.id == session.id
    assert len(loaded.entries) == 1
    assert loaded.entries[0].task == "hello"


def test_session_store_load_by_prefix(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    s = store.new_session(tmp_path)
    store.save(s)
    prefix = s.id.split("-")[0]
    loaded = store.load(prefix)
    assert loaded.id == s.id


def test_session_store_ambiguous_prefix_raises(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    store.base_dir.mkdir(parents=True)
    for name in ("20260101-abc-aaaa", "20260101-abc-bbbb"):
        (store.base_dir / f"{name}.json").write_text(
            json.dumps(
                ClientSession(
                    id=name,
                    created_at="x",
                    updated_at="x",
                    entries=[],
                ).model_dump()
            ),
            encoding="utf-8",
        )
    with pytest.raises(FileNotFoundError):
        store.load("20260101-abc")


def test_compress_and_session_context_includes_prior_runs() -> None:
    r1 = TaskResult(task="first", status=TaskStatus.COMPLETED, conclusion="done A", plan=[])
    r2 = TaskResult(task="second", status=TaskStatus.FAILED, error="boom", plan=[])
    e1 = task_result_to_entry(r1)
    e2 = task_result_to_entry(r2)
    assert e1.summary
    assert "done A" in e1.summary
    ctx = build_session_context_for_planner([e1])
    assert "done A" in ctx
    ctx2 = build_session_context_for_planner([e1, e2])
    assert "boom" in ctx2 or "failed" in ctx2.lower()


def test_task_result_to_entry_preview_truncates() -> None:
    result = TaskResult(
        task="t",
        status=TaskStatus.COMPLETED,
        output=("x\n" * 3000),
    )
    entry = task_result_to_entry(result)
    assert len(entry.output_preview) < len(result.output or "")
