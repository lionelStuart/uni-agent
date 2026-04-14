from __future__ import annotations

from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


load_dotenv()

PlannerBackend = Literal["auto", "heuristic", "pydantic_ai"]

# Single source for CLI sandbox + planner hints (comma-separated).
DEFAULT_SANDBOX_ALLOWED_COMMANDS = "pwd,ls,cat,echo,rg,du"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UNI_AGENT_", extra="ignore")

    model_name: str = Field(default="openai:gpt-4.1-mini")
    openai_base_url: str | None = Field(
        default=None,
        description="OpenAI-compatible API base URL (e.g. https://host/v1). Maps to UNI_AGENT_OPENAI_BASE_URL.",
    )
    openai_api_key: str | None = Field(
        default=None,
        description="Optional API key override for OpenAI-compatible providers. Maps to UNI_AGENT_OPENAI_API_KEY.",
    )
    planner_backend: PlannerBackend = "auto"
    workspace: Path = Field(default_factory=lambda: Path(".").resolve())
    skills_dir: Path = Field(default_factory=lambda: Path("skills").resolve())
    task_log_dir: Path = Field(default_factory=lambda: Path(".uni-agent/runs").resolve())
    session_dir: Path = Field(default_factory=lambda: Path(".uni-agent/sessions").resolve())
    log_level: str = "INFO"
    sandbox_allowed_commands: str = Field(default=DEFAULT_SANDBOX_ALLOWED_COMMANDS)
    sandbox_prompt_for_disallowed: bool = Field(
        default=True,
        description="If true, non-allowlisted sandbox commands can be approved interactively (TTY only).",
    )
    sandbox_command_timeout_seconds: int = 30
    http_fetch_max_bytes: int = 500_000
    http_fetch_allow_private_networks: bool = False
    http_fetch_allowed_hosts: str = ""
    tool_step_retries: int = 0
    planner_instructions: str | None = Field(
        default=None,
        description="Override planner LLM system prompt; default is built-in DEFAULT_PLANNER_SYSTEM_PROMPT.",
    )
    global_system_prompt: str | None = Field(
        default=None,
        description="Optional prefix prepended to planner and conclusion system prompts.",
    )
    conclusion_system_prompt: str | None = Field(
        default=None,
        description="Override run-conclusion LLM system prompt; default is built-in DEFAULT_CONCLUSION_SYSTEM_PROMPT.",
    )
    llm_temperature: float | None = None
    llm_retries: int = 1
    orchestrator_max_failed_rounds: int = 5
    run_conclusion_llm: bool = Field(
        default=True,
        description="If true and an LLM is configured, synthesize a final natural-language conclusion after the run.",
    )


def get_settings() -> Settings:
    return Settings()


def parse_sandbox_allowed_commands(raw: str) -> set[str]:
    return {part.strip() for part in raw.split(",") if part.strip()}


def parse_http_fetch_allowed_hosts(raw: str) -> frozenset[str]:
    return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())
