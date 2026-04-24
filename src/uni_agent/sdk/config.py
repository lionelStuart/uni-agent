"""Declarative agent profile: maps to :class:`~uni_agent.config.settings.Settings` for ``build_orchestrator``."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from uni_agent.config.settings import Settings

PlannerBackend = Literal["auto", "heuristic", "pydantic_ai"]


class AgentConfig(BaseModel):
    """Process-local profile for one agent: skills root, workspace, and prompt / model overrides.

    Paths: ``workspace`` is resolved first; **relative** ``skills_dir`` is resolved under ``workspace``.
    """

    model_config = {"extra": "forbid", "arbitrary_types_allowed": True}

    name: str = Field(default="agent", min_length=1, description="Used in default global_system_prompt if no override is set.")
    description: str = Field(default="", description="Appended to default persona block when global_system_prompt is unset.")
    workspace: Path = Field(description="Sandbox cwd and skill path anchor.")
    skills_dir: Path = Field(description="Root whose immediate subdirectories are skills (see SkillLoader).")
    storage_namespace: str | None = Field(
        default=None,
        description=(
            "If set, task logs go under <workspace>/.uni-agent/runs/<namespace>/; "
            "memory under <workspace>/.uni-agent/memory/<namespace>/ to isolate multiple agents in one process."
        ),
    )
    model_name: str | None = Field(default=None, description="Overrides UNI_AGENT_MODEL_NAME when not None.")
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    ca_bundle: Path | None = Field(
        default=None,
        description="Optional CA bundle file for urllib-based HTTPS tools; relative paths resolve under workspace.",
    )
    skip_tls_verify: bool = Field(
        default=True,
        description="If true, urllib-based HTTPS tools disable TLS certificate verification. Insecure.",
    )
    planner_backend: PlannerBackend = "auto"
    global_system_prompt: str | None = Field(
        default=None,
        description="If set, used as the global prefix for planner / conclusion / goal-check. "
        "If None and name or description is non-empty, a default persona block is built.",
    )
    planner_instructions: str | None = None
    conclusion_system_prompt: str | None = None
    run_conclusion_llm: bool | None = None
    plan_goal_check_enabled: bool | None = Field(
        default=None,
        description="Overrides UNI_AGENT_PLAN_GOAL_CHECK_ENABLED when not None.",
    )

    def to_settings(self) -> Settings:
        """Build explicit ``Settings`` for this profile (call-site kwargs override same-named env)."""
        ws = self.workspace.expanduser().resolve()
        skills = self.skills_dir
        sk = skills if skills.is_absolute() else (ws / skills).resolve()

        gsp = self.global_system_prompt
        if gsp is None:
            parts: list[str] = []
            if self.name.strip():
                parts.append(f"You are the assistant **{self.name.strip()}**.")
            if self.description.strip():
                parts.append(self.description.strip())
            gsp = "\n\n".join(parts) if parts else None

        task_log = ws / ".uni-agent" / "runs"
        mem: Path | None = None
        if self.storage_namespace:
            ns = self.storage_namespace.strip().replace("..", "_").strip("/\\")  # no traversal
            if ns:
                task_log = task_log / ns
                mem = ws / ".uni-agent" / "memory" / ns

        kwargs: dict = {
            "workspace": ws,
            "skills_dir": sk,
            "task_log_dir": task_log,
            "planner_backend": self.planner_backend,
            "global_system_prompt": gsp,
            "planner_instructions": self.planner_instructions,
            "conclusion_system_prompt": self.conclusion_system_prompt,
        }
        if mem is not None:
            kwargs["memory_dir"] = mem
        if self.model_name is not None:
            kwargs["model_name"] = self.model_name
        if self.openai_base_url is not None:
            kwargs["openai_base_url"] = self.openai_base_url
        if self.openai_api_key is not None:
            kwargs["openai_api_key"] = self.openai_api_key
        if self.ca_bundle is not None:
            kwargs["ca_bundle"] = self.ca_bundle
        kwargs["skip_tls_verify"] = self.skip_tls_verify
        if self.run_conclusion_llm is not None:
            kwargs["run_conclusion_llm"] = self.run_conclusion_llm
        if self.plan_goal_check_enabled is not None:
            kwargs["plan_goal_check_enabled"] = self.plan_goal_check_enabled
        return Settings(**kwargs)
