from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

SkillLoadFormat = Literal["skill_md", "yaml_manifest"]


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    PARTIAL = "partial"
    NEEDS_REVIEW = "needs_review"


class ToolSpec(BaseModel):
    name: str
    description: str
    risk_level: str = "low"
    input_schema: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    status: Literal["ok", "error", "partial"] = "ok"
    summary: str = ""
    text: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    retryable: bool = False
    error_code: str | None = None

    @classmethod
    def from_text(cls, text: str) -> "ToolResult":
        summary = _first_non_empty_line(text)
        return cls(summary=summary, text=text)


class SkillSpec(BaseModel):
    name: str
    version: str
    description: str
    triggers: list[str] = Field(default_factory=list)
    priority: int = 0
    required_tools: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    entry: str = "prompt.md"
    path: str
    skill_load_format: SkillLoadFormat = "yaml_manifest"
    instruction_text: str = ""
    reference_paths: list[str] = Field(default_factory=list)
    script_paths: list[str] = Field(default_factory=list)


class PlanStep(BaseModel):
    id: str
    description: str
    tool: str | None = None
    skill: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    output: str = ""
    error_type: str | None = None
    error_detail: str | None = None
    failure_code: str | None = None
    verifications: list[dict[str, Any]] = Field(default_factory=list)
    tool_result: dict[str, Any] = Field(default_factory=dict)


class TaskResult(BaseModel):
    run_id: str | None = None
    task: str
    status: TaskStatus
    selected_skills: list[str] = Field(default_factory=list)
    available_tools: list[str] = Field(default_factory=list)
    plan: list[PlanStep] = Field(default_factory=list)
    output: str = ""
    answer: str = ""
    error: str | None = None
    orchestrator_failed_rounds: int = 0
    goal_check_mismatch_rounds: int = Field(
        default=0,
        description="Post-batch goal checks that reported not satisfied (each may trigger a re-plan).",
    )
    conclusion: str | None = None
    parent_run_id: str | None = None
    working_memory: dict[str, Any] = Field(default_factory=dict)
    run_stats: dict[str, Any] = Field(default_factory=dict)


class TaskRunRecord(BaseModel):
    run_id: str
    task: str
    status: TaskStatus
    result: TaskResult


def _first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:300]
    return ""
