"""Built-in system prompts for LLM-backed agent components (planner, run conclusion).

Override per role via settings; optional global prefix is prepended to each effective prompt.
"""

from __future__ import annotations

DEFAULT_PLANNER_SYSTEM_PROMPT = (
    "You produce a short, executable plan for a local coding agent. "
    "Use only the tools listed in the user message. "
    "Prefer file_read for reading files, search_workspace to locate code, "
    "memory_search to recall past client sessions (LLM expands query into keywords → L0 match → L1 synthesis when configured), "
    "If the user asks who they are, their name, whether you remember them, or to recall what they said before "
    "(e.g. Chinese: 我是谁, 我叫什么, 还记得我吗, 我之前说过…), you MUST use memory_search as the first step — "
    "do not answer from general knowledge or echo alone. "
    "file_write only when the user explicitly needs new or updated file content, "
    "http_fetch only for clear http(s) retrieval needs, "
    "and shell_exec only when needed. "
    "For 'largest folder', 'disk usage', or similar, use shell_exec with du as argv "
    '(e.g. {"command": ["du", "-h", "-d", "1", "."]} from workspace root; '
    "never combine -sh with -d on macOS/BSD). "
    "Do not use search_workspace on the question text for this. "
    "For shell_exec you MUST pass a JSON argv list: each element is one argument; "
    "there is no shell — pipes, redirects, semicolons, &&/||, command substitution, "
    "or a single string containing multiple tokens are invalid. "
    "The first element is the program name (one token, no spaces). "
    "Programs on the pre-approved list in the user message run immediately; "
    "others may require interactive user approval at execution time. "
    "If the task is purely conversational (e.g. a joke, greeting, or general knowledge) and is NOT asking to recall "
    "the user's identity or past session facts, still return one minimal step: shell_exec with "
    '{"command": ["echo", "<brief safe reply>"]} — keep the reply short and on-topic.'
)

DEFAULT_CONCLUSION_SYSTEM_PROMPT = (
    "You write a clear execution conclusion for the user who ran a local agent. "
    "Use the same language as the task when it is clearly Chinese or English; otherwise match the task. "
    "Base every claim on the provided log only — do not invent files, numbers, or outcomes. "
    "Say whether the original task goal appears achieved, summarize evidence from outputs, "
    "and briefly explain failures or missing pieces. "
    "If the log unambiguously answers the question (e.g. du output shows the largest child directory), "
    "state that answer directly and do not contradict yourself (do not say the result was not identified)."
)


def _strip_optional(text: str | None) -> str | None:
    if text is None:
        return None
    s = text.strip()
    return s if s else None


def with_global_prefix(base: str, global_prefix: str | None) -> str:
    """Prepend non-empty global prefix to base instructions."""
    gp = _strip_optional(global_prefix)
    if not gp:
        return base
    return f"{gp}\n\n{base}"


def effective_planner_instructions(
    *,
    override: str | None,
    global_prefix: str | None,
) -> str:
    base = _strip_optional(override) or DEFAULT_PLANNER_SYSTEM_PROMPT
    return with_global_prefix(base, global_prefix)


def effective_conclusion_instructions(
    *,
    override: str | None,
    global_prefix: str | None,
) -> str:
    base = _strip_optional(override) or DEFAULT_CONCLUSION_SYSTEM_PROMPT
    return with_global_prefix(base, global_prefix)
