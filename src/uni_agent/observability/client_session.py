from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from uni_agent.context.budgeting import derive_context_budgets
from uni_agent.context.token_budget import ContextBlock, fit_blocks_to_budget, render_blocks, count_tokens
from uni_agent.shared.models import TaskResult

_SESSION_ENTRY_SUMMARY_MAX_CHARS = 2000
_SESSION_PLANNER_MAX_ENTRIES = 20
_SESSION_PLANNER_CONTEXT_MAX_TOKENS = derive_context_budgets(256_000).session_context_max_tokens
_SESSION_RECENT_ENTRY_COUNT = 4


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
    tools_used: list[str] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    next_hints: list[str] = Field(default_factory=list)
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
    tools = [s.tool for s in result.plan if s.tool]
    if tools:
        chunks.append("tools=" + ",".join(tools[:8]))
    chunks.extend(_extract_key_findings(result)[:2])
    failures = _extract_failures(result)
    if failures:
        chunks.append(f"failures={'; '.join(failures[:2])}")
    text = " | ".join(chunks)
    if len(text) > _SESSION_ENTRY_SUMMARY_MAX_CHARS:
        text = text[: _SESSION_ENTRY_SUMMARY_MAX_CHARS] + "…"
    return text


def entry_summary_for_planner(entry: ClientSessionRunEntry) -> str:
    if entry.summary.strip():
        return entry.summary.strip()
    parts = [f"status={entry.status}; task={entry.task[:200]!r}"]
    if entry.key_findings:
        parts.append("findings=" + "; ".join(entry.key_findings[:2]))
    elif entry.conclusion:
        parts.append(entry.conclusion[:600] + ("…" if len(entry.conclusion) > 600 else ""))
    if entry.failures:
        parts.append("failures=" + "; ".join(entry.failures[:2]))
    elif entry.error:
        parts.append(entry.error[:300])
    return " | ".join(parts)[:_SESSION_ENTRY_SUMMARY_MAX_CHARS]


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    kept: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        kept.append(normalized)
    return kept


def _extract_key_findings(result: TaskResult) -> list[str]:
    findings: list[str] = []
    if result.conclusion:
        findings.append(result.conclusion.strip().replace("\n", " ")[:600])
    for step in result.plan:
        if step.output:
            head = next((line.strip() for line in step.output.splitlines() if line.strip()), "")
            if head:
                findings.append(head[:280])
        if len(findings) >= 4:
            break
    out = (result.output or "").strip()
    if out:
        first = next((line.strip() for line in out.splitlines() if line.strip()), "")
        if first:
            findings.append(first[:280])
    return _dedupe_keep_order(findings)


def _extract_failures(result: TaskResult) -> list[str]:
    failures: list[str] = []
    for step in result.plan:
        if step.status.value != "failed":
            continue
        detail = (step.error_detail or step.output or step.description).strip().replace("\n", " ")
        if detail:
            failures.append(f"{step.tool}: {detail[:240]}")
    if result.error:
        failures.append(result.error.strip().replace("\n", " ")[:280])
    return _dedupe_keep_order(failures)


def _extract_next_hints(result: TaskResult) -> list[str]:
    if result.status.value == "completed":
        return []
    failed = _extract_failures(result)
    if failed:
        return [f"Avoid repeating: {failed[0]}"]
    return []


def _entry_to_context_block(entry: ClientSessionRunEntry, *, index: int, recent: bool) -> ContextBlock:
    lines = [f"{index}. [{entry.run_id or '?'}] status={entry.status}; task={entry.task[:200]!r}"]
    deduped = False
    if entry.tools_used:
        lines.append(f"  tools: {', '.join(entry.tools_used[:8])}")
    if entry.key_findings:
        findings = _dedupe_keep_order(entry.key_findings[:3])
        deduped = deduped or len(entry.key_findings[:3]) != len(findings)
        lines.append("  findings:")
        lines.extend(f"  - {item}" for item in findings)
    if entry.failures:
        failures = _dedupe_keep_order(entry.failures[:2])
        deduped = deduped or len(entry.failures[:2]) != len(failures)
        lines.append("  failures:")
        lines.extend(f"  - {item}" for item in failures)
    if entry.next_hints:
        hints = _dedupe_keep_order(entry.next_hints[:2])
        deduped = deduped or len(entry.next_hints[:2]) != len(hints)
        lines.append("  next_hints:")
        lines.extend(f"  - {item}" for item in hints)
    priority = 90 - index if recent else 30 - index
    block = ContextBlock(
        kind="recent_turn" if recent else "memory_summary",
        text="\n".join(lines),
        priority=priority,
    )
    if deduped:
        block.metadata["labels"] = "deduped"
    return block


def _rolling_summary_block(entries: list[ClientSessionRunEntry]) -> ContextBlock | None:
    if not entries:
        return None
    raw_findings = [item for entry in entries for item in entry.key_findings]
    raw_failures = [item for entry in entries for item in entry.failures]
    findings = _dedupe_keep_order(raw_findings)[:5]
    failures = _dedupe_keep_order(raw_failures)[:4]
    deduped_findings = len(raw_findings) != len(_dedupe_keep_order(raw_findings))
    deduped_failures = len(raw_failures) != len(_dedupe_keep_order(raw_failures))
    deduped = deduped_findings or deduped_failures
    tasks = [entry.task[:100] for entry in entries[-3:]]
    lines = [f"Older session summary ({len(entries)} runs):"]
    if tasks:
        lines.append("  recent_old_tasks: " + " | ".join(tasks))
    if findings:
        lines.append("  confirmed_findings:")
        lines.extend(f"  - {item}" for item in findings)
    if failures:
        lines.append("  repeated_failures:")
        lines.extend(f"  - {item}" for item in failures)
    block = ContextBlock(kind="memory_summary", text="\n".join(lines), priority=20, metadata={"labels": "rolling_summary"})
    if deduped:
        block.metadata["labels"] = "rolling_summary,deduped"
    return block


def build_session_context_for_planner(
    entries: list[ClientSessionRunEntry],
    *,
    max_tokens: int = _SESSION_PLANNER_CONTEXT_MAX_TOKENS,
    model_name: str | None = None,
) -> str:
    """Concatenate compressed summaries for prior client turns (excludes current turn)."""
    if not entries:
        return ""
    slice_ = entries[-_SESSION_PLANNER_MAX_ENTRIES :]
    older = slice_[:-_SESSION_RECENT_ENTRY_COUNT]
    recent = slice_[-_SESSION_RECENT_ENTRY_COUNT:]
    blocks: list[ContextBlock] = []
    rolling = _rolling_summary_block(older)
    if rolling is not None:
        blocks.append(rolling)
    for i, entry in enumerate(recent, start=max(1, len(slice_) - len(recent) + 1)):
        blocks.append(_entry_to_context_block(entry, index=i, recent=True))
    fitted = fit_blocks_to_budget(blocks, max_tokens=max_tokens, model_name=model_name)
    text = render_blocks(fitted, separator="\n\n")
    if count_tokens(text, model_name) > max_tokens:
        return render_blocks(
            fit_blocks_to_budget(
                [ContextBlock(kind="memory_summary", text=text, priority=10)],
                max_tokens=max_tokens,
                model_name=model_name,
            ),
            separator="\n\n",
        )
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
        tools_used=[step.tool for step in result.plan if step.tool][:8],
        key_findings=_extract_key_findings(result),
        failures=_extract_failures(result),
        next_hints=_extract_next_hints(result),
        summary=summary,
    )
