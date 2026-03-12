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
    status: TaskStatus = TaskStatus.PENDING


class TaskResult(BaseModel):
    task: str
    status: TaskStatus
    selected_skills: list[str] = Field(default_factory=list)
    available_tools: list[str] = Field(default_factory=list)
    plan: list[PlanStep] = Field(default_factory=list)
    output: str = ""

