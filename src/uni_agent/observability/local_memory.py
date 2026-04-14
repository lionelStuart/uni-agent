"""Persist session turns: L0 lines live in ``memory_index.json``; L1 bodies under ``l1/``.

- **Index**: ``memory_index.json`` lists ``run_id``, ``session_id``, ``l0``, ``l1_rel``, timestamps.
- **L1 files**: ``l1/<ts>_<uuid>_<slug>.json`` hold only the full payload (``data`` object).
- **Search**: matches stored ``l0`` in the index; loads matching ``l1`` files for display.
- **Legacy**: older combined ``*.json`` at store root (not the index file) still searchable until migrated on upsert.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from uni_agent.observability.client_session import ClientSession, ClientSessionRunEntry

MEMORY_INDEX_FILE = "memory_index.json"
MEMORY_L1_SUBDIR = "l1"

MEMORY_INDEX_SCHEMA = 3
MEMORY_L1_FILE_SCHEMA = 2
# Legacy: single-file v2 record (l0+l1 in one JSON at store root)
MEMORY_RECORD_SCHEMA = 2

_L0_MAX_CHARS = 520
_MEMORY_SEARCH_MAX_FILES = 400
_MEMORY_SEARCH_MAX_SNIPPET = 900
_MAX_KEYWORDS_FOR_L0_SCAN = 16

_TOP_LEVEL_META = frozenset(
    {
        "schema_version",
        "l0",
        "l1",
        "created_at",
        "updated_at",
        "saved_at",
        "data",
    }
)

_L0_PREVIEW_CHARS = 160


@dataclass(frozen=True)
class MemoryPersistItem:
    run_id: str
    action: Literal["created", "updated"]
    file_name: str
    l0_preview: str


@dataclass(frozen=True)
class MemoryPersistReport:
    written: int
    new_checkpoint: int
    items: list[MemoryPersistItem]


def _preview_l0(l0: str) -> str:
    one = l0.replace("\n", " ").strip()
    if len(one) <= _L0_PREVIEW_CHARS:
        return one
    return one[:_L0_PREVIEW_CHARS] + "…"


def _slug_run_id(run_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", run_id.strip())[:24]
    return s or "unknown"


def l0_from_l1(l1: dict) -> str:
    """Derive a single-line L0 index string from L1 (no LLM)."""
    parts: list[str] = []
    task = str(l1.get("task", "")).replace("\n", " ").strip()
    if len(task) > 160:
        task = task[:160] + "…"
    if task:
        parts.append(task)

    summ = str(l1.get("summary", "")).replace("\n", " ").strip()
    if summ:
        if len(summ) > 260:
            summ = summ[:260] + "…"
        parts.append(summ)

    concl = str(l1.get("conclusion", "")).replace("\n", " ").strip()
    if concl:
        short = concl[:220] + ("…" if len(concl) > 220 else "")
        if short not in summ:
            parts.append(short)

    prev = str(l1.get("output_preview", "")).replace("\n", " ").strip()
    if prev:
        head = prev[:140] + ("…" if len(prev) > 140 else "")
        parts.append(f"out:{head}")

    st = str(l1.get("status", "")).strip()
    if st:
        parts.append(f"status={st}")
    rid = str(l1.get("run_id", "")).strip()
    if rid:
        parts.append(f"run={rid}")

    text = " | ".join(parts)
    if len(text) > _L0_MAX_CHARS:
        text = text[:_L0_MAX_CHARS] + "…"
    return text


def _session_entry_to_l1(session_id: str, e: ClientSessionRunEntry) -> dict:
    return {
        "session_id": session_id,
        "run_id": e.run_id,
        "task": e.task,
        "status": e.status,
        "started_at": e.started_at,
        "finished_at": e.finished_at,
        "error": e.error,
        "conclusion": e.conclusion,
        "summary": e.summary,
        "output_preview": e.output_preview,
        "plan_step_count": e.plan_step_count,
    }


def parse_memory_record(data: dict) -> tuple[str, dict, str | None, str | None]:
    """Return ``(l0_for_match, l1, created_at, updated_at)`` for legacy combined files."""
    if isinstance(data.get("l1"), dict):
        l1 = dict(data["l1"])
        l0_stored = str(data.get("l0", "")).strip()
        l0 = l0_stored if l0_stored else l0_from_l1(l1)
        return (
            l0,
            l1,
            data.get("created_at"),
            data.get("updated_at"),
        )
    l1 = {k: v for k, v in data.items() if k not in _TOP_LEVEL_META}
    l0 = l0_from_l1(l1)
    return l0, l1, data.get("saved_at"), None


def _load_index(memory_dir: Path) -> dict[str, Any]:
    path = memory_dir / MEMORY_INDEX_FILE
    if not path.is_file():
        return {"schema_version": MEMORY_INDEX_SCHEMA, "entries": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": MEMORY_INDEX_SCHEMA, "entries": []}
    if not isinstance(data.get("entries"), list):
        data["entries"] = []
    return data


def _save_index(memory_dir: Path, doc: dict[str, Any]) -> None:
    path = memory_dir / MEMORY_INDEX_FILE
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _index_entry_for_run(entries: list[dict[str, Any]], run_id: str) -> dict[str, Any] | None:
    for ent in entries:
        if str(ent.get("run_id", "")) == run_id:
            return ent
    return None


def _write_l1_file(path: Path, l1: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": MEMORY_L1_FILE_SCHEMA, "data": l1}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_l1_file(path: Path) -> dict | None:
    """Load L1 ``data`` from a file under ``l1/`` (or legacy-shaped JSON)."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data.get("data"), dict):
        return dict(data["data"])
    if isinstance(data.get("l1"), dict):
        return dict(data["l1"])
    ign = _TOP_LEVEL_META | {"schema_version"}
    return {k: v for k, v in data.items() if k not in ign} or None


def _find_legacy_combined_path(memory_dir: Path, run_id: str) -> Path | None:
    if not run_id.strip():
        return None
    for p in memory_dir.glob("*.json"):
        if p.name == MEMORY_INDEX_FILE:
            continue
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        _, l1, _, _ = parse_memory_record(raw)
        if str(l1.get("run_id", "")) == run_id:
            return p
    return None


def find_record_path_by_run_id(memory_dir: Path, run_id: str) -> Path | None:
    """Resolved path to L1 file, or legacy combined JSON at store root."""
    memory_dir = memory_dir.resolve()
    if not memory_dir.is_dir():
        return None
    idx = _load_index(memory_dir)
    ent = _index_entry_for_run(list(idx.get("entries", [])), run_id)
    if ent:
        p = memory_dir / str(ent.get("l1_rel", ""))
        if p.is_file():
            return p
    return _find_legacy_combined_path(memory_dir, run_id)


def collect_memory_hits_for_keywords(
    memory_dir: Path,
    keywords: list[str],
    *,
    max_entries: int = 15,
) -> list[dict[str, Any]]:
    """Collect memory rows where **any** normalized keyword is a substring of **L0** (case-insensitive).

    Each hit is ``{"l1_rel", "l0", "l1"}``. Index entries are scanned first (newest ``updated_at``),
    then legacy combined JSON at the store root (excluding ``memory_index.json``).
    """
    memory_dir = memory_dir.resolve()
    if not memory_dir.is_dir():
        return []
    norm_kws: list[str] = []
    for k in keywords:
        s = str(k).strip().lower()
        if s and s not in norm_kws:
            norm_kws.append(s)
    norm_kws = norm_kws[:_MAX_KEYWORDS_FOR_L0_SCAN]
    if not norm_kws:
        return []

    hits: list[dict[str, Any]] = []
    seen_run: set[str] = set()

    idx_path = memory_dir / MEMORY_INDEX_FILE
    if idx_path.is_file():
        idx = _load_index(memory_dir)
        ordered = sorted(
            list(idx.get("entries", [])),
            key=lambda e: str(e.get("updated_at", e.get("created_at", ""))),
            reverse=True,
        )
        for ent in ordered:
            if len(hits) >= max_entries:
                break
            l0_text = str(ent.get("l0", "")).lower()
            if not any(k in l0_text for k in norm_kws):
                continue
            rel = str(ent.get("l1_rel", ""))
            l1 = read_l1_file(memory_dir / rel)
            if not l1:
                continue
            rid = str(l1.get("run_id", ""))
            if rid in seen_run:
                continue
            seen_run.add(rid)
            hits.append({"l1_rel": rel, "l0": str(ent.get("l0", "")), "l1": l1})

    index_run_ids = {str(e.get("run_id", "")) for e in _load_index(memory_dir).get("entries", [])}
    for path in sorted(
        [p for p in memory_dir.glob("*.json") if p.name != MEMORY_INDEX_FILE],
        key=lambda p: p.stat().st_mtime_ns,
        reverse=True,
    ):
        if len(hits) >= max_entries:
            break
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        l0_match, l1, _, _ = parse_memory_record(data)
        rid = str(l1.get("run_id", ""))
        if rid and rid in index_run_ids:
            continue
        if rid in seen_run:
            continue
        l0_lower = l0_match.lower()
        if not any(k in l0_lower for k in norm_kws):
            continue
        if rid:
            seen_run.add(rid)
        hits.append({"l1_rel": path.name, "l0": l0_match, "l1": l1})

    return hits


def _format_search_hit(*, l1_rel: str, l0_match: str, l1: dict) -> str:
    task = str(l1.get("task", "")).strip()
    summ = str(l1.get("summary", "")).strip()
    concl = str(l1.get("conclusion", "")).strip()
    body = "\n".join(
        part
        for part in (
            f"L0: {l0_match}",
            f"task: {task}" if task else "",
            f"summary: {summ}" if summ else "",
            f"conclusion: {concl}" if concl else "",
        )
        if part
    )
    if len(body) > _MEMORY_SEARCH_MAX_SNIPPET:
        body = body[:_MEMORY_SEARCH_MAX_SNIPPET] + "…"
    return (
        f"l1={l1_rel}\n"
        f"session={l1.get('session_id', '')} run_id={l1.get('run_id', '')}\n"
        f"{body}"
    )


def persist_new_session_entries(
    *,
    memory_dir: Path,
    session_id: str,
    entries: list[ClientSessionRunEntry],
    start_index: int,
) -> MemoryPersistReport:
    """Write or upsert by ``run_id``; refresh index ``l0`` and L1 file under ``l1/``."""
    if start_index < 0:
        start_index = 0
    if start_index >= len(entries):
        return MemoryPersistReport(0, start_index, [])

    memory_dir = memory_dir.resolve()
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / MEMORY_L1_SUBDIR).mkdir(parents=True, exist_ok=True)

    idx = _load_index(memory_dir)
    entries_list: list[dict[str, Any]] = list(idx.setdefault("entries", []))
    now = datetime.now(timezone.utc).isoformat()
    written = 0
    items: list[MemoryPersistItem] = []

    for i in range(start_index, len(entries)):
        e = entries[i]
        l1 = _session_entry_to_l1(session_id, e)
        l0 = l0_from_l1(l1)
        preview = _preview_l0(l0)

        idx_ent = _index_entry_for_run(entries_list, e.run_id)
        legacy = _find_legacy_combined_path(memory_dir, e.run_id) if not idx_ent else None

        if idx_ent is not None:
            rel = str(idx_ent["l1_rel"])
            l1_path = memory_dir / rel
            _write_l1_file(l1_path, l1)
            idx_ent["l0"] = l0
            idx_ent["session_id"] = session_id
            idx_ent["updated_at"] = now
            items.append(
                MemoryPersistItem(
                    run_id=e.run_id,
                    action="updated",
                    file_name=rel.replace("\\", "/"),
                    l0_preview=preview,
                )
            )
        elif legacy is not None:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            fname = f"{ts}_{uuid4().hex[:8]}_{_slug_run_id(e.run_id)}.json"
            rel = f"{MEMORY_L1_SUBDIR}/{fname}"
            l1_path = memory_dir / rel
            _write_l1_file(l1_path, l1)
            entries_list.append(
                {
                    "run_id": e.run_id,
                    "session_id": session_id,
                    "l0": l0,
                    "l1_rel": rel,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            try:
                legacy.unlink()
            except OSError:
                pass
            items.append(
                MemoryPersistItem(
                    run_id=e.run_id,
                    action="created",
                    file_name=rel,
                    l0_preview=preview,
                )
            )
        else:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            fname = f"{ts}_{uuid4().hex[:8]}_{_slug_run_id(e.run_id)}.json"
            rel = f"{MEMORY_L1_SUBDIR}/{fname}"
            l1_path = memory_dir / rel
            _write_l1_file(l1_path, l1)
            entries_list.append(
                {
                    "run_id": e.run_id,
                    "session_id": session_id,
                    "l0": l0,
                    "l1_rel": rel,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            items.append(
                MemoryPersistItem(
                    run_id=e.run_id,
                    action="created",
                    file_name=rel,
                    l0_preview=preview,
                )
            )
        written += 1

    idx["entries"] = entries_list
    _save_index(memory_dir, idx)
    return MemoryPersistReport(written=written, new_checkpoint=len(entries), items=items)


def search_memory_directory(
    memory_dir: Path,
    query: str,
    *,
    limit: int = 20,
    max_files_scan: int = _MEMORY_SEARCH_MAX_FILES,
) -> str:
    """Match ``query`` against **L0** in ``memory_index.json``; load ``l1/`` for hits."""
    q = query.strip()
    if not q:
        return "memory_search requires a non-empty query string."
    memory_dir = memory_dir.resolve()
    if not memory_dir.is_dir():
        return f"(no memory directory yet: {memory_dir})"

    needle = q.lower()
    hits: list[str] = []
    seen_run: set[str] = set()
    scanned = 0

    idx_path = memory_dir / MEMORY_INDEX_FILE
    idx: dict[str, Any] = _load_index(memory_dir)
    if idx_path.is_file():
        ordered = sorted(
            list(idx.get("entries", [])),
            key=lambda e: str(e.get("updated_at", e.get("created_at", ""))),
            reverse=True,
        )
        for ent in ordered:
            if len(hits) >= limit:
                break
            scanned += 1
            if scanned > max_files_scan:
                break
            l0_match = str(ent.get("l0", ""))
            if needle not in l0_match.lower():
                continue
            rel = str(ent.get("l1_rel", ""))
            l1 = read_l1_file(memory_dir / rel)
            if not l1:
                continue
            rid = str(l1.get("run_id", ""))
            if rid:
                seen_run.add(rid)
            hits.append(_format_search_hit(l1_rel=rel, l0_match=l0_match, l1=l1))

    index_run_ids = {str(e.get("run_id", "")) for e in idx.get("entries", [])}

    root_json = sorted(
        [p for p in memory_dir.glob("*.json") if p.name != MEMORY_INDEX_FILE],
        key=lambda p: p.stat().st_mtime_ns,
        reverse=True,
    )
    for path in root_json:
        if len(hits) >= limit:
            break
        if scanned >= max_files_scan:
            break
        scanned += 1
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except OSError:
            continue
        except json.JSONDecodeError:
            if needle in raw.lower():
                hits.append(f"file={path.name}\n(raw record; JSON parse failed)\n{raw[:_MEMORY_SEARCH_MAX_SNIPPET]}")
            continue
        l0_match, l1, _ca, _ua = parse_memory_record(data)
        rid = str(l1.get("run_id", ""))
        if rid and rid in seen_run:
            continue
        if rid and rid in index_run_ids:
            continue
        if needle not in l0_match.lower():
            continue
        if rid:
            seen_run.add(rid)
        hits.append(
            _format_search_hit(l1_rel=path.name, l0_match=l0_match, l1=l1)
        )

    if not hits:
        return f"No memory records match {q!r} (L0 index; scanned up to {scanned} entries/files)."
    return "\n\n---\n\n".join(hits)


def count_memory_records(memory_dir: Path) -> int:
    memory_dir = memory_dir.resolve()
    if not memory_dir.is_dir():
        return 0
    idx = _load_index(memory_dir)
    index_run_ids = {str(e.get("run_id", "")) for e in idx.get("entries", [])}
    n = len(idx.get("entries", []))
    for p in memory_dir.glob("*.json"):
        if p.name == MEMORY_INDEX_FILE:
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        _, l1, _, _ = parse_memory_record(data)
        rid = str(l1.get("run_id", ""))
        if rid and rid not in index_run_ids:
            n += 1
    return n


def persist_incremental_for_client_session(*, memory_dir: Path, session: ClientSession) -> MemoryPersistReport:
    """Advance ``session.memory_last_extracted_index`` after writing new records."""
    report = persist_new_session_entries(
        memory_dir=memory_dir,
        session_id=session.id,
        entries=session.entries,
        start_index=session.memory_last_extracted_index,
    )
    session.memory_last_extracted_index = report.new_checkpoint
    return report
