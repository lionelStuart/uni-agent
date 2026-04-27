from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from uni_agent.shared.models import PlanStep, TaskStatus


class ActionRecord(BaseModel):
    step_id: str
    tool: str | None = None
    description: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: str = ""
    output_summary: str = ""


class FailureRecord(BaseModel):
    step_id: str
    tool: str | None = None
    failure_code: str | None = None
    error_type: str | None = None
    error_detail: str = ""


class RunWorkingMemory(BaseModel):
    facts_confirmed: list[str] = Field(default_factory=list)
    actions_attempted: list[ActionRecord] = Field(default_factory=list)
    artifacts_created: list[str] = Field(default_factory=list)
    recent_failures: list[FailureRecord] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    constraints_active: list[str] = Field(default_factory=list)

    def record_step(self, step: PlanStep) -> None:
        self.actions_attempted.append(
            ActionRecord(
                step_id=step.id,
                tool=step.tool,
                description=step.description,
                arguments=step.arguments,
                status=step.status.value,
                output_summary=_summarize_text(step.output),
            )
        )
        if step.status == TaskStatus.FAILED:
            self.recent_failures.append(
                FailureRecord(
                    step_id=step.id,
                    tool=step.tool,
                    failure_code=step.failure_code,
                    error_type=step.error_type,
                    error_detail=(step.error_detail or step.output or "")[:600],
                )
            )
            self.recent_failures = self.recent_failures[-8:]
        artifact = _artifact_from_step(step)
        if artifact and artifact not in self.artifacts_created:
            self.artifacts_created.append(artifact)

    def render_digest(self) -> str:
        lines: list[str] = ["Working memory (this run):"]
        if self.actions_attempted:
            lines.append("  recent actions:")
            for action in self.actions_attempted[-6:]:
                args = _compact_json(action.arguments)
                lines.append(f"  - {action.step_id} {action.tool} {action.status}: {args}")
        if self.recent_failures:
            lines.append("  recent failures:")
            for failure in self.recent_failures[-4:]:
                prefix = f"{failure.failure_code}: " if failure.failure_code else ""
                lines.append(f"  - {failure.step_id} {failure.tool}: {prefix}{failure.error_detail[:180]}")
        if self.artifacts_created:
            lines.append("  artifacts:")
            lines.extend(f"  - {path}" for path in self.artifacts_created[-8:])
        if self.open_questions:
            lines.append("  open questions:")
            lines.extend(f"  - {item}" for item in self.open_questions[-5:])
        return "\n".join(lines)


def _artifact_from_step(step: PlanStep) -> str | None:
    if step.status != TaskStatus.COMPLETED:
        return None
    if step.tool == "file_write":
        path = step.arguments.get("path")
        return path if isinstance(path, str) and path else None
    return None


def _summarize_text(text: str, *, max_chars: int = 220) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    summary = " / ".join(lines[:3])
    return summary[:max_chars]


def _compact_json(value: dict[str, Any], *, max_chars: int = 220) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        text = str(value)
    return text[:max_chars]
