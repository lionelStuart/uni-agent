"""Format ``delegate_task`` tool return text and truncation helpers."""

from __future__ import annotations

from uni_agent.shared.models import TaskResult, TaskStatus

MAX_DELEGATE_TASK_CHARS = 4_000
MAX_DELEGATE_CONTEXT_CHARS = 8_000
MAX_DELEGATE_SESSION_APPEND_CHARS = 8_000
OUTPUT_SNIPPET_CHARS = 3_000


def truncate(s: str, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "\n... [truncated]"


def format_delegate_result(
    *,
    child: TaskResult,
    parent_run_id: str | None,
) -> str:
    st = child.status.value
    concl = (child.conclusion or "").strip()
    out = child.output or ""
    snippet = truncate(out, OUTPUT_SNIPPET_CHARS).strip()
    pr = parent_run_id or ""
    cr = child.run_id or ""
    lines = [
        f"CHILD_RUN_ID={cr}",
        f"PARENT_RUN_ID={pr}",
        f"STATUS={st}",
        "CONCLUSION:",
        concl or "(none)",
        "",
        "OUTPUT_SNIPPET:",
        snippet or "(none)",
    ]
    if child.status == TaskStatus.FAILED and child.error:
        lines.extend(["", f"ERROR: {child.error}"])
    return "\n".join(lines)


def delegate_result_payload(*, child: TaskResult, parent_run_id: str | None) -> dict:
    return {
        "child_run_id": child.run_id or "",
        "parent_run_id": parent_run_id or "",
        "status": child.status.value,
        "conclusion": child.conclusion or "",
        "output_snippet": truncate(child.output or "", OUTPUT_SNIPPET_CHARS).strip(),
        "error": child.error or "",
        "child_run_stats": child.run_stats,
    }


def format_delegate_exception(exc: BaseException, *, parent_run_id: str | None) -> str:
    pr = parent_run_id or ""
    return "\n".join(
        [
            "CHILD_RUN_ID=",
            f"PARENT_RUN_ID={pr}",
            "STATUS=failed",
            "CONCLUSION:",
            "(none)",
            "",
            "OUTPUT_SNIPPET:",
            "(none)",
            "",
            f"ERROR: {exc}",
        ]
    )


def delegate_exception_payload(exc: BaseException, *, parent_run_id: str | None) -> dict:
    return {
        "child_run_id": "",
        "parent_run_id": parent_run_id or "",
        "status": TaskStatus.FAILED.value,
        "conclusion": "",
        "output_snippet": "",
        "error": str(exc),
        "child_run_stats": {},
    }
