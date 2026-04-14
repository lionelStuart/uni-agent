"""LLM-assisted memory search: query → keyword plan → L0 substring match → L1 → synthesized answer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from uni_agent.agent.llm import LLMProvider, build_planner_model
from uni_agent.observability.local_memory import collect_memory_hits_for_keywords


class MemoryKeywordPlan(BaseModel):
    keywords: list[str] = Field(
        default_factory=list,
        description="3–10 short keywords/phrases likely to appear in memory index lines (L0), mixed zh/en.",
    )


class MemoryAnswer(BaseModel):
    answer: str = Field(
        description="Answer using only the provided memory records; cite run_id when helpful."
    )


_KEYWORD_INSTRUCTIONS = (
    "You output search keywords for a personal memory index. Each index line (L0) is a short summary, "
    "often mixing Chinese and English. The user message is their question. "
    "Return 3–10 DISTINCT short keywords or phrases likely to appear verbatim or as substrings in those lines — "
    "e.g. names, products, errors, paths, service names. "
    "If the question is short (especially Chinese), include the exact phrase or key characters from it, "
    "because L0 often contains the original task text. Also add close synonyms or English tokens when useful."
)

_SYNTH_INSTRUCTIONS = (
    "You answer the user's question using ONLY the JSON memory records in the user message. "
    "If information is missing, say so clearly. "
    "Match the user's language when it is clearly Chinese or English. "
    "You may mention run_id when citing a specific turn."
)


def _normalize_keywords(raw: list[str], fallback: str) -> list[str]:
    """Merge model keywords with the raw user query (L0 often contains the task string verbatim).

    Without this, an English-only keyword plan for a Chinese question can miss every L0 line.
    """
    out: list[str] = []
    seen_lower: set[str] = set()

    def add(term: str) -> None:
        t = term.strip()
        if not t:
            return
        low = t.lower()
        if low in seen_lower:
            return
        seen_lower.add(low)
        out.append(t)

    fb = fallback.strip()
    if fb:
        add(fb[:200])
    for x in raw:
        add(str(x))
        if len(out) >= 14:
            break
    if not out and fb:
        add(fb[:200])
    return out


def _compact_l1_for_synth(l1: dict) -> dict[str, Any]:
    pv = str(l1.get("output_preview", ""))
    if len(pv) > 1500:
        pv = pv[:1500] + "…"
    return {
        "run_id": l1.get("run_id"),
        "session_id": l1.get("session_id"),
        "task": l1.get("task"),
        "status": l1.get("status"),
        "summary": l1.get("summary"),
        "conclusion": l1.get("conclusion"),
        "error": l1.get("error"),
        "output_preview": pv,
    }


def run_memory_search_llm(
    query: str,
    memory_dir: Path,
    provider: LLMProvider,
    *,
    model_settings: dict[str, Any] | None = None,
    keyword_retries: int = 1,
    synthesis_retries: int = 0,
    max_hits: int = 12,
    defer_model_check: bool = True,
) -> str:
    """Plan keywords with an LLM, scan L0, then synthesize an answer from matching L1 rows."""
    q = query.strip()
    if not q:
        return "Empty query."

    resolved_model = build_planner_model(
        provider.model_id,
        openai_base_url=getattr(provider, "openai_base_url", None),
        openai_api_key=getattr(provider, "openai_api_key", None),
    )

    kw_kwargs: dict[str, Any] = {
        "output_type": MemoryKeywordPlan,
        "instructions": _KEYWORD_INSTRUCTIONS,
        "defer_model_check": defer_model_check,
        "retries": keyword_retries,
    }
    if model_settings:
        kw_kwargs["model_settings"] = model_settings
    kw_agent: Agent[None, MemoryKeywordPlan] = Agent(resolved_model, **kw_kwargs)
    raw_kw: list[str] = []
    try:
        kw_result = kw_agent.run_sync(q)
        raw_kw = kw_result.output.keywords
    except Exception:
        raw_kw = []
    keywords = _normalize_keywords(raw_kw, q)

    hits = collect_memory_hits_for_keywords(memory_dir, keywords, max_entries=max_hits)
    if not hits:
        shown = ", ".join(keywords[:8]) + ("…" if len(keywords) > 8 else "")
        return (
            "未在本地记忆 L0 索引中匹配到与生成关键词相关的条目。"
            f"（关键词：{shown}）可尝试换一种问法，或在关闭 LLM 记忆搜索时使用字面子串搜索。"
        )

    records = [_compact_l1_for_synth(h["l1"]) for h in hits]
    blob = json.dumps({"memories": records}, ensure_ascii=False, indent=2)
    max_chars = 48_000
    if len(blob) > max_chars and records:
        trim = max(1, len(records) * max_chars // len(blob))
        records = records[:trim]
        blob = json.dumps({"memories": records}, ensure_ascii=False, indent=2)

    syn_kwargs: dict[str, Any] = {
        "output_type": MemoryAnswer,
        "instructions": _SYNTH_INSTRUCTIONS,
        "defer_model_check": defer_model_check,
        "retries": synthesis_retries,
    }
    if model_settings:
        syn_kwargs["model_settings"] = model_settings
    syn_agent: Agent[None, MemoryAnswer] = Agent(resolved_model, **syn_kwargs)
    user_block = f"User question:\n{q}\n\nMemory records (JSON):\n{blob}\n"
    ans = syn_agent.run_sync(user_block)
    foot = (
        f"\n\n---\n[memory_search] keywords={', '.join(keywords[:10])}"
        f"{'…' if len(keywords) > 10 else ''} | matched_entries={len(hits)}"
    )
    return ans.output.answer.strip() + foot
