from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from uni_agent.shared.models import TaskResult

_SESSION_ENTRY_SUMMARY_MAX_CHARS = 2000
_SESSION_PLANNER_CONTEXT_MAX_CHARS = 12_000
_SESSION_PLANNER_MAX_ENTRIES = 20


def new_session_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{uuid4().hex[:4]}"


class ClientSessionRunEntry(BaseModel):
    """One task execution inside a client session."""

    run_id: str
    task: str
    status: str
    started_at: str = ""
    finished_at: str = ""
    error: str | None = None
    conclusion: str | None = None
    output_preview: str = ""
    plan_step_count: int = 0
    summary: str = Field(default="", description="Compressed line for later planner context in this session.")


class ClientSession(BaseModel):
    id: str
    created_at: str
    updated_at: str
    workspace: str = ""
    entries: list[ClientSessionRunEntry] = Field(default_factory=list)
    memory_last_extracted_index: int = Field(
        default=0,
        ge=0,
        description="Entries in ``entries[:index]`` have been persisted to the local memory folder.",
    )


class SessionStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir.resolve()

    def _path(self, session_id: str) -> Path:
        safe = session_id.replace("/", "").replace("\\", "")
        if not safe or ".." in session_id:
            raise ValueError("Invalid session id.")
        return self.base_dir / f"{safe}.json"

    def save(self, session: ClientSession) -> Path:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        session.updated_at = datetime.now(timezone.utc).isoformat()
        path = self._path(session.id)
        path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load(self, session_id: str) -> ClientSession:
        path = self._path(session_id)
        if not path.is_file():
            resolved = self.resolve_session_id(session_id)
            if resolved is None:
                raise FileNotFoundError(f"No session matching {session_id!r} under {self.base_dir}")
            path = self._path(resolved)
        return ClientSession.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def resolve_session_id(self, prefix_or_id: str) -> str | None:
        """Exact file stem match, else unique prefix match among ``*.json``."""
        stem = prefix_or_id.strip()
        if not stem:
            return None
        exact = self._path(stem)
        if exact.is_file():
            return stem
        matches = sorted(self.base_dir.glob(f"{stem}*.json"))
        if len(matches) == 1:
            return matches[0].stem
        if len(matches) > 1:
            names = [p.stem for p in matches]
            raise FileNotFoundError(f"Ambiguous session id prefix {stem!r}; matches: {names}")
        all_json = list(self.base_dir.glob("*.json"))
        sub = [p for p in all_json if stem in p.stem]
        if len(sub) == 1:
            return sub[0].stem
        if len(sub) > 1:
            names = [p.stem for p in sub]
            raise FileNotFoundError(f"Ambiguous session id substring {stem!r}; matches: {names}")
        return None

    def list_sessions(self, *, limit: int = 30) -> list[tuple[str, float]]:
        if not self.base_dir.is_dir():
            return []
        rows: list[tuple[str, float]] = []
        for p in self.base_dir.glob("*.json"):
            try:
                rows.append((p.stem, p.stat().st_mtime))
            except OSError:
                continue
        rows.sort(key=lambda x: -x[1])
        return rows[:limit]

    def new_session(self, workspace: Path) -> ClientSession:
        now = datetime.now(timezone.utc).isoformat()
        sid = new_session_id()
        return ClientSession(
            id=sid,
            created_at=now,
            updated_at=now,
            workspace=str(workspace.resolve()),
            entries=[],
        )


def compress_task_result_for_session(result: TaskResult) -> str:
    """Bounded one-block summary: conclusion-first, then status/tools/error/output head."""
    chunks: list[str] = []
    head_task = result.task.strip().replace("\n", " ")
    if len(head_task) > 240:
        head_task = head_task[:240] + "…"
    chunks.append(f"status={result.status.value}; task={head_task!r}")
    if result.conclusion:
        c = result.conclusion.strip().replace("\n", " ")
        if len(c) > 1100:
            c = c[:1100] + "…"
        chunks.append(c)
    tools = [s.tool for s in result.plan if s.tool]
    if tools:
        chunks.append("tools=" + ",".join(tools[:8]))
    if result.error and not result.conclusion:
        e = result.error.strip().replace("\n", " ")
        if len(e) > 400:
            e = e[:400] + "…"
        chunks.append(f"error={e}")
    out = (result.output or "").strip()
    if out and len(result.conclusion or "") < 80:
        first = out.splitlines()[0] if out else ""
        if len(first) > 360:
            first = first[:360] + "…"
        chunks.append(f"out_head={first!r}")
    text = " | ".join(chunks)
    if len(text) > _SESSION_ENTRY_SUMMARY_MAX_CHARS:
        text = text[: _SESSION_ENTRY_SUMMARY_MAX_CHARS] + "…"
    return text


def entry_summary_for_planner(entry: ClientSessionRunEntry) -> str:
    if entry.summary.strip():
        return entry.summary.strip()
    parts = [f"status={entry.status}; task={entry.task[:200]!r}"]
    if entry.conclusion:
        parts.append(entry.conclusion[:600] + ("…" if len(entry.conclusion) > 600 else ""))
    elif entry.error:
        parts.append(entry.error[:300])
    return " | ".join(parts)[:_SESSION_ENTRY_SUMMARY_MAX_CHARS]


def build_session_context_for_planner(entries: list[ClientSessionRunEntry]) -> str:
    """Concatenate compressed summaries for prior client turns (excludes current turn)."""
    if not entries:
        return ""
    slice_ = entries[-_SESSION_PLANNER_MAX_ENTRIES :]
    lines: list[str] = []
    for i, e in enumerate(slice_, start=1):
        summ = entry_summary_for_planner(e)
        rid = e.run_id or "?"
        lines.append(f"{i}. [{rid}] {summ}")
    text = "\n".join(lines)
    if len(text) > _SESSION_PLANNER_CONTEXT_MAX_CHARS:
        text = "...[truncated session memory]\n" + text[-_SESSION_PLANNER_CONTEXT_MAX_CHARS:]
    return text


def task_result_to_entry(result: TaskResult) -> ClientSessionRunEntry:
    preview = (result.output or "").strip()
    if len(preview) > 1500:
        preview = preview[:1500] + "\n... [truncated]"
    summary = compress_task_result_for_session(result)
    return ClientSessionRunEntry(
        run_id=result.run_id or "",
        task=result.task,
        status=result.status.value,
        finished_at=datetime.now(timezone.utc).isoformat(),
        error=result.error,
        conclusion=result.conclusion,
        output_preview=preview,
        plan_step_count=len(result.plan),
        summary=summary,
    )
