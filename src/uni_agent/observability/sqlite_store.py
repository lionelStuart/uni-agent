from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from uni_agent.observability.logging import get_logger
from uni_agent.shared.models import TaskResult


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


@dataclass(slots=True)
class SessionSummary:
    session_id: str
    source: str
    workspace: str
    created_at: str
    updated_at: str
    run_count: int
    latest_run_id: str | None
    latest_status: str | None


@dataclass(slots=True)
class RunSummary:
    run_id: str
    session_id: str
    parent_run_id: str | None
    task: str
    status: str
    source: str
    started_at: str | None
    finished_at: str | None
    error: str | None
    conclusion: str | None
    answer: str | None
    output: str | None
    orchestrator_failed_rounds: int


class ObservabilitySqliteStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).resolve()
        self._lock = threading.Lock()
        self._log = get_logger(__name__)
        self._init_db()

    @contextmanager
    def _connect(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    workspace TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    run_count INTEGER NOT NULL DEFAULT 0,
                    latest_run_id TEXT,
                    latest_status TEXT,
                    session_payload TEXT
                );

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    parent_run_id TEXT,
                    task TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    source TEXT NOT NULL DEFAULT '',
                    workspace TEXT NOT NULL DEFAULT '',
                    started_at TEXT,
                    finished_at TEXT,
                    error TEXT,
                    conclusion TEXT,
                    answer TEXT,
                    output TEXT,
                    orchestrator_failed_rounds INTEGER NOT NULL DEFAULT 0,
                    result_payload TEXT,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_runs_session_finished
                    ON runs(session_id, finished_at DESC, started_at DESC);

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    run_id TEXT,
                    event_index INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id),
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );

                CREATE INDEX IF NOT EXISTS idx_events_session_run
                    ON events(session_id, run_id, event_index);
                """
            )

    def upsert_session(
        self,
        *,
        session_id: str,
        source: str,
        workspace: str,
        created_at: str | None = None,
        updated_at: str | None = None,
        latest_run_id: str | None = None,
        latest_status: str | None = None,
        session_payload: dict[str, Any] | None = None,
    ) -> None:
        created = created_at or _utc_now()
        updated = updated_at or created
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, source, workspace, created_at, updated_at,
                    latest_run_id, latest_status, session_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    source=excluded.source,
                    workspace=excluded.workspace,
                    updated_at=excluded.updated_at,
                    latest_run_id=COALESCE(excluded.latest_run_id, sessions.latest_run_id),
                    latest_status=COALESCE(excluded.latest_status, sessions.latest_status),
                    session_payload=COALESCE(excluded.session_payload, sessions.session_payload)
                """,
                (
                    session_id,
                    source,
                    workspace,
                    created,
                    updated,
                    latest_run_id,
                    latest_status,
                    _json_dumps(session_payload) if session_payload is not None else None,
                ),
            )

    def record_event(
        self,
        *,
        session_id: str,
        run_id: str | None,
        event_index: int,
        event: dict[str, Any],
        source: str,
        workspace: str,
        observed_at: str | None = None,
    ) -> None:
        now = observed_at or _utc_now()
        event_type = str(event.get("type") or "unknown")
        self.upsert_session(
            session_id=session_id,
            source=source,
            workspace=workspace,
            updated_at=now,
            latest_run_id=run_id,
            latest_status=str(event.get("status")) if event_type == "run_end" and event.get("status") else None,
        )
        with self._lock, self._connect() as conn:
            if run_id:
                if event_type == "run_begin":
                    task = str(event.get("task") or "")
                    conn.execute(
                        """
                        INSERT INTO runs (
                            run_id, session_id, parent_run_id, task, status, source, workspace, started_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(run_id) DO UPDATE SET
                            session_id=excluded.session_id,
                            parent_run_id=COALESCE(excluded.parent_run_id, runs.parent_run_id),
                            task=CASE WHEN excluded.task != '' THEN excluded.task ELSE runs.task END,
                            status='running',
                            source=excluded.source,
                            workspace=excluded.workspace,
                            started_at=COALESCE(runs.started_at, excluded.started_at)
                        """,
                        (
                            run_id,
                            session_id,
                            event.get("parent_run_id"),
                            task,
                            "running",
                            source,
                            workspace,
                            now,
                        ),
                    )
                elif event_type == "run_end":
                    conn.execute(
                        """
                        INSERT INTO runs (
                            run_id, session_id, status, source, workspace, finished_at, orchestrator_failed_rounds
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(run_id) DO UPDATE SET
                            session_id=excluded.session_id,
                            status=excluded.status,
                            source=excluded.source,
                            workspace=excluded.workspace,
                            finished_at=excluded.finished_at,
                            orchestrator_failed_rounds=excluded.orchestrator_failed_rounds
                        """,
                        (
                            run_id,
                            session_id,
                            event.get("status") or "unknown",
                            source,
                            workspace,
                            now,
                            int(event.get("orchestrator_failed_rounds") or 0),
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO runs (run_id, session_id, source, workspace)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(run_id) DO UPDATE SET
                            session_id=excluded.session_id,
                            source=excluded.source,
                            workspace=excluded.workspace
                        """,
                        (run_id, session_id, source, workspace),
                    )
            conn.execute(
                """
                INSERT INTO events (session_id, run_id, event_index, event_type, created_at, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, run_id, event_index, event_type, now, _json_dumps(event)),
            )
            conn.execute(
                """
                UPDATE sessions
                SET run_count=(
                    SELECT COUNT(*) FROM runs WHERE runs.session_id=sessions.session_id
                )
                WHERE session_id=?
                """,
                (session_id,),
            )

    def save_task_result(
        self,
        result: TaskResult,
        *,
        session_id: str,
        source: str,
        workspace: str,
    ) -> None:
        if not result.run_id:
            return
        now = _utc_now()
        self.upsert_session(
            session_id=session_id,
            source=source,
            workspace=workspace,
            updated_at=now,
            latest_run_id=result.run_id,
            latest_status=result.status.value,
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, session_id, parent_run_id, task, status, source, workspace,
                    started_at, finished_at, error, conclusion, answer, output,
                    orchestrator_failed_rounds, result_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    session_id=excluded.session_id,
                    parent_run_id=COALESCE(excluded.parent_run_id, runs.parent_run_id),
                    task=excluded.task,
                    status=excluded.status,
                    source=excluded.source,
                    workspace=excluded.workspace,
                    finished_at=excluded.finished_at,
                    error=excluded.error,
                    conclusion=excluded.conclusion,
                    answer=excluded.answer,
                    output=excluded.output,
                    orchestrator_failed_rounds=excluded.orchestrator_failed_rounds,
                    result_payload=excluded.result_payload
                """,
                (
                    result.run_id,
                    session_id,
                    result.parent_run_id,
                    result.task,
                    result.status.value,
                    source,
                    workspace,
                    None,
                    now,
                    result.error,
                    result.conclusion,
                    result.answer,
                    result.output,
                    result.orchestrator_failed_rounds,
                    result.model_dump_json(),
                ),
            )
            conn.execute(
                """
                UPDATE sessions
                SET updated_at=?, latest_run_id=?, latest_status=?,
                    run_count=(SELECT COUNT(*) FROM runs WHERE runs.session_id=sessions.session_id)
                WHERE session_id=?
                """,
                (now, result.run_id, result.status.value, session_id),
            )

    def save_client_session(self, session: Any, *, source: str = "client") -> None:
        workspace = session.workspace or ""
        payload = session.model_dump(mode="json")
        latest = session.entries[-1] if session.entries else None
        self.upsert_session(
            session_id=session.id,
            source=source,
            workspace=workspace,
            created_at=session.created_at,
            updated_at=session.updated_at,
            latest_run_id=latest.run_id if latest else None,
            latest_status=latest.status if latest else None,
            session_payload=payload,
        )
        with self._lock, self._connect() as conn:
            for entry in session.entries:
                conn.execute(
                    """
                    UPDATE runs
                    SET session_id=?, source=?, workspace=?
                    WHERE run_id=?
                    """,
                    (session.id, source, workspace, entry.run_id),
                )
            conn.execute(
                """
                UPDATE sessions
                SET run_count=(SELECT COUNT(*) FROM runs WHERE runs.session_id=sessions.session_id)
                WHERE session_id=?
                """,
                (session.id,),
            )

    def list_sessions(self, *, limit: int = 50) -> list[SessionSummary]:
        return self.search_sessions(limit=limit)

    def search_sessions(
        self,
        *,
        limit: int = 50,
        source: str | None = None,
        status: str | None = None,
        query: str | None = None,
    ) -> list[SessionSummary]:
        clauses = ["1=1"]
        params: list[Any] = []
        if source:
            clauses.append("source = ?")
            params.append(source)
        if status:
            clauses.append("latest_status = ?")
            params.append(status)
        if query:
            like = f"%{query}%"
            clauses.append(
                "(session_id LIKE ? OR workspace LIKE ? OR source LIKE ? OR COALESCE(latest_run_id, '') LIKE ?)"
            )
            params.extend([like, like, like, like])
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT session_id, source, workspace, created_at, updated_at, run_count, latest_run_id, latest_status
                FROM sessions
                WHERE {' AND '.join(clauses)}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
        return [SessionSummary(**dict(row)) for row in rows]

    def list_runs(
        self,
        session_id: str,
        *,
        status: str | None = None,
        query: str | None = None,
    ) -> list[RunSummary]:
        clauses = ["session_id=?"]
        params: list[Any] = [session_id]
        if status:
            clauses.append("status = ?")
            params.append(status)
        if query:
            like = f"%{query}%"
            clauses.append(
                "(run_id LIKE ? OR task LIKE ? OR COALESCE(answer, '') LIKE ? OR COALESCE(conclusion, '') LIKE ? OR COALESCE(output, '') LIKE ?)"
            )
            params.extend([like, like, like, like, like])
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT run_id, session_id, parent_run_id, task, status, source, started_at, finished_at,
                       error, conclusion, answer, output, orchestrator_failed_rounds
                FROM runs
                WHERE {' AND '.join(clauses)}
                ORDER BY COALESCE(started_at, finished_at) DESC, run_id DESC
                """,
                tuple(params),
            ).fetchall()
        return [RunSummary(**dict(row)) for row in rows]

    def get_run_detail(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT run_id, session_id, parent_run_id, task, status, source, workspace,
                       started_at, finished_at, error, conclusion, answer, output,
                       orchestrator_failed_rounds, result_payload
                FROM runs
                WHERE run_id=?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        payload = item.get("result_payload")
        item["result_payload"] = json.loads(str(payload)) if payload else None
        return item

    def get_session_payload(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT session_payload FROM sessions WHERE session_id=?",
                (session_id,),
            ).fetchone()
        if row is None or not row["session_payload"]:
            return None
        return json.loads(str(row["session_payload"]))

    def list_events(
        self,
        session_id: str,
        run_id: str | None = None,
        *,
        event_type: str | None = None,
        query: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT run_id, event_index, event_type, created_at, payload
            FROM events
            WHERE session_id=?
        """
        params: list[Any] = [session_id]
        if run_id is not None:
            sql += " AND run_id=?"
            params.append(run_id)
        if event_type:
            sql += " AND event_type=?"
            params.append(event_type)
        if query:
            sql += " AND payload LIKE ?"
            params.append(f"%{query}%")
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(str(row["payload"]))
            out.append(
                {
                    "run_id": row["run_id"],
                    "event_index": row["event_index"],
                    "event_type": row["event_type"],
                    "created_at": row["created_at"],
                    "payload": payload,
                }
            )
        return out


def safe_create_sqlite_store(db_path: Path | None) -> ObservabilitySqliteStore | None:
    if db_path is None:
        return None
    try:
        return ObservabilitySqliteStore(db_path)
    except Exception:
        get_logger(__name__).exception("observability_sqlite_init_failed", path=str(db_path))
        return None
