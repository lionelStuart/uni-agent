from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from uni_agent.observability.sqlite_store import ObservabilitySqliteStore
from uni_agent.shared.models import TaskResult, TaskRunRecord


class TaskStore:
    def __init__(
        self,
        base_dir: Path,
        *,
        sqlite_store: ObservabilitySqliteStore | None = None,
        session_id: str | None = None,
        source: str = "cli",
        workspace: str = "",
    ):
        self.base_dir = base_dir
        self.sqlite_store = sqlite_store
        self.session_id = session_id
        self.source = source
        self.workspace = workspace

    def next_run_id(self) -> str:
        return uuid4().hex[:12]

    def save(self, result: TaskResult) -> Path:
        if not result.run_id:
            raise ValueError("Task result must include run_id before saving.")

        self.base_dir.mkdir(parents=True, exist_ok=True)
        record = TaskRunRecord(
            run_id=result.run_id,
            task=result.task,
            status=result.status,
            result=result,
        )
        path = self.base_dir / f"{result.run_id}.json"
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        if self.sqlite_store is not None:
            session_id = self.session_id or f"run-{result.run_id}"
            self.sqlite_store.save_task_result(
                result,
                session_id=session_id,
                source=self.source,
                workspace=self.workspace,
            )
        return path

    def load(self, run_id: str) -> TaskRunRecord:
        path = self.base_dir / f"{run_id}.json"
        return TaskRunRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))
