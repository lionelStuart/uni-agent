from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Iterable

try:  # pragma: no cover - optional dependency
    import tiktoken  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    tiktoken = None

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_WORDISH_RE = re.compile(r"[A-Za-z0-9_]+|[^\w\s]", re.UNICODE)


@dataclass(slots=True)
class ContextBlock:
    kind: str
    text: str
    priority: int = 0
    pinned: bool = False
    token_estimate: int = 0
    metadata: dict[str, str] = field(default_factory=dict)


def _append_label(block: ContextBlock, label: str) -> None:
    existing = {
        item.strip().lower()
        for item in (block.metadata.get("labels") or "").split(",")
        if item.strip()
    }
    normalized = label.strip().lower()
    if normalized and normalized not in existing:
        existing.add(normalized)
        block.metadata["labels"] = ",".join(sorted(existing))


def _format_block_labels(block: ContextBlock) -> str:
    explicit = [item.strip().lower() for item in (block.metadata.get("labels") or "").split(",") if item.strip()]
    if explicit:
        labels = explicit
    else:
        labels = []
    fallback = {
        "recent_turn": "recent_turn",
        "memory_summary": "rolling_summary",
        "system": "system_hint",
        "prior_step": "recent_step",
        "task": "task",
        "status": "status",
        "error": "error",
        "aggregate": "aggregate",
    }
    if not labels and block.kind in fallback:
        labels = [fallback[block.kind]]
    return "".join(f"[{label}]" for label in labels) + (" " if labels else "")


def count_tokens(text: str, model_name: str | None = None) -> int:
    normalized = (text or "").strip()
    if not normalized:
        return 0
    if tiktoken is not None:
        try:  # pragma: no cover - depends on optional package
            enc = tiktoken.encoding_for_model(model_name or "gpt-4o-mini")
        except Exception:  # pragma: no cover - depends on optional package
            try:
                enc = tiktoken.get_encoding("cl100k_base")
            except Exception:
                enc = None
        if enc is not None:
            try:
                return len(enc.encode(normalized))
            except Exception:
                pass
    cjk_count = len(_CJK_RE.findall(normalized))
    non_cjk = _CJK_RE.sub(" ", normalized)
    wordish = len(_WORDISH_RE.findall(non_cjk))
    char_bucket = math.ceil(len(non_cjk) / 4)
    return max(1, cjk_count + max(wordish, char_bucket // 2))


def truncate_to_tokens(text: str, max_tokens: int, model_name: str | None = None) -> str:
    if max_tokens <= 0:
        return ""
    normalized = (text or "").strip()
    if not normalized:
        return ""
    if count_tokens(normalized, model_name) <= max_tokens:
        return normalized
    suffix = "\n... [truncated]"
    if max_tokens <= count_tokens(suffix, model_name):
        return normalized[: max(1, min(len(normalized), max_tokens))]
    low, high = 1, len(normalized)
    best = normalized[:1]
    while low <= high:
        mid = (low + high) // 2
        candidate = normalized[:mid].rstrip() + suffix
        if count_tokens(candidate, model_name) <= max_tokens:
            best = candidate
            low = mid + 1
        else:
            high = mid - 1
    return best


def fit_blocks_to_budget(
    blocks: Iterable[ContextBlock],
    max_tokens: int,
    model_name: str | None = None,
) -> list[ContextBlock]:
    prepared: list[tuple[int, ContextBlock]] = []
    for idx, block in enumerate(blocks):
        text = (block.text or "").strip()
        if not text:
            continue
        token_estimate = block.token_estimate or count_tokens(text, model_name)
        prepared.append(
            (
                idx,
                ContextBlock(
                    kind=block.kind,
                    text=text,
                    priority=block.priority,
                    pinned=block.pinned,
                    token_estimate=token_estimate,
                    metadata=dict(block.metadata),
                ),
            )
        )
    if max_tokens <= 0 or not prepared:
        return []

    prepared.sort(key=lambda item: (not item[1].pinned, -item[1].priority, item[0]))
    kept: list[tuple[int, ContextBlock]] = []
    remaining = max_tokens

    for idx, block in prepared:
        current = block.token_estimate or count_tokens(block.text, model_name)
        if current <= remaining:
            block.token_estimate = current
            kept.append((idx, block))
            remaining -= current
            continue
        if remaining <= 0:
            continue
        if block.pinned or block.priority > 0:
            truncated = truncate_to_tokens(block.text, remaining, model_name)
            if truncated.strip():
                block.text = truncated
                block.token_estimate = count_tokens(truncated, model_name)
                _append_label(block, "truncated")
                kept.append((idx, block))
                remaining -= block.token_estimate

    kept.sort(key=lambda item: item[0])
    return [block for _, block in kept]


def render_blocks(blocks: Iterable[ContextBlock], *, separator: str = "\n\n") -> str:
    rendered = []
    for block in blocks:
        text = block.text.strip()
        if not text:
            continue
        prefix = _format_block_labels(block)
        rendered.append(f"{prefix}{text}" if prefix else text)
    return separator.join(rendered).strip()
