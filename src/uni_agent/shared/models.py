from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ToolSpec(BaseModel):
    name: str
    description: str
    risk_level: str = "low"
    input_schema: dict[str, Any] = Field(default_factory=dict)


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


class TaskResult(BaseModel):
    run_id: str | None = None
    task: str
    status: TaskStatus
    selected_skills: list[str] = Field(default_factory=list)
    available_tools: list[str] = Field(default_factory=list)
    plan: list[PlanStep] = Field(default_factory=list)
    output: str = ""
    error: str | None = None


class TaskRunRecord(BaseModel):
    run_id: str
    task: str
    status: TaskStatus
    result: TaskResult
