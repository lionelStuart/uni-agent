from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class EvalWeights(BaseModel):
    goal: float = 0.25
    trajectory: float = 0.20
    efficiency: float = 0.10
    stability: float = 0.15
    safety: float = 0.10
    llm_judge: float = 0.20

    def normalized(self) -> "EvalWeights":
        total = (
            self.goal
            + self.trajectory
            + self.efficiency
            + self.stability
            + self.safety
            + self.llm_judge
        )
        if total <= 0:
            return EvalWeights()
        return EvalWeights(
            goal=self.goal / total,
            trajectory=self.trajectory / total,
            efficiency=self.efficiency / total,
            stability=self.stability / total,
            safety=self.safety / total,
            llm_judge=self.llm_judge / total,
        )


class EvalAssertions(BaseModel):
    status: str = "completed"
    output_contains: list[str] = Field(default_factory=list)
    output_not_contains: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    expected_tool_sequence: list[str] = Field(default_factory=list)
    max_steps: int | None = None
    max_failed_steps: int = 0
    max_loop_guard_triggers: int = 0
    max_verifier_failures: int = 0
    file_contains: dict[str, str] = Field(default_factory=dict)
    tool_payload_contains: dict[str, str] = Field(default_factory=dict)


class EvalCase(BaseModel):
    id: str
    description: str = ""
    task: str
    plan: str | None = None
    assertions: EvalAssertions = Field(default_factory=EvalAssertions)
    weights: EvalWeights = Field(default_factory=EvalWeights)
    source_path: Path | None = None


class DimensionScore(BaseModel):
    score: float
    passed: bool
    reasons: list[str] = Field(default_factory=list)


class EvalCaseResult(BaseModel):
    id: str
    description: str = ""
    run_id: str | None = None
    status: str
    overall_score: float
    passed: bool
    scores: dict[str, DimensionScore]
    failures: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    steps_total: int = 0


class EvalSuiteResult(BaseModel):
    cases_total: int
    cases_passed: int
    pass_rate: float
    average_score: float
    results: list[EvalCaseResult]


EvalOutputFormat = Literal["summary", "json"]
