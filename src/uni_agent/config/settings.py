from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

DelegateToolProfile = Literal["full", "readonly"]

from dotenv import load_dotenv
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


load_dotenv()

PlannerBackend = Literal["auto", "heuristic", "pydantic_ai"]

# Single source for CLI sandbox + planner hints (comma-separated).
# Includes python3/python for the run_python builtin (workspace-scoped snippets).
DEFAULT_SANDBOX_ALLOWED_COMMANDS = "pwd,ls,cat,echo,rg,du,python3,python"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UNI_AGENT_", extra="ignore")

    model_name: str = Field(default="openai:gpt-4.1-mini")
    context_window_tokens: int = Field(
        default=256_000,
        ge=8_192,
        description=(
            "Configured model context window in tokens. Used to derive token-aware compression budgets "
            "for session_context, prior_context, goal-check, and conclusion digests."
        ),
    )
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
    memory_dir: Path | None = Field(
        default=None,
        description=(
            "Memory store directory. Unset → ``<UNI_AGENT_WORKSPACE>/.uni-agent/memory``. "
            "Relative paths resolve under ``workspace`` (not process cwd)."
        ),
    )
    ca_bundle: Path | None = Field(
        default=None,
        description=(
            "Optional CA bundle file for urllib-based HTTPS tools (for example http_fetch / web_search). "
            "Relative paths resolve under ``workspace``."
        ),
    )
    skip_tls_verify: bool = Field(
        default=True,
        description=(
            "If true, urllib-based HTTPS tools (for example http_fetch / web_search) disable TLS certificate "
            "verification. Insecure; use only for controlled environments."
        ),
    )
    memory_extract_enabled: bool = Field(
        default=True,
        description="If true, interactive client persists new session turns to memory_dir after idle delay.",
    )
    memory_idle_extract_seconds: float = Field(
        default=20.0,
        ge=0.0,
        description="REPL idle seconds before flushing new session entries to memory_dir; 0 disables idle flush.",
    )
    memory_search_use_llm: bool = Field(
        default=True,
        description="If true and an LLM is configured, memory_search expands query via LLM, matches L0, then answers from L1.",
    )
    memory_search_max_hits: int = Field(
        default=12,
        ge=1,
        le=30,
        description="Max L1 memory rows passed to the synthesis step when using LLM memory_search.",
    )
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
    plan_goal_check_enabled: bool = Field(
        default=True,
        description=(
            "If true and an LLM is configured, after each batch of steps that all **completed**, run a goal check; "
            "if the task is not yet satisfied, inject feedback into the next plan (re-plan loop, capped by "
            "plan_goal_check_max_replan_rounds)."
        ),
    )
    plan_goal_check_max_replan_rounds: int = Field(
        default=3,
        ge=0,
        le=20,
        description="Max number of re-plan attempts after a goal check reports not satisfied (0 = no extra re-plans on goal miss).",
    )
    plan_goal_check_system_prompt: str | None = Field(
        default=None,
        description="Optional override for the goal-check LLM system prompt (default: DEFAULT_GOAL_CHECK_SYSTEM_PROMPT).",
    )
    observability_langfuse_enabled: bool = Field(
        default=False,
        description=(
            "If true, stream events are exported to Langfuse when the langfuse package and credentials are available."
        ),
    )
    observability_langfuse_host: str | None = Field(
        default=None,
        description="Optional Langfuse host endpoint. If unset, Langfuse client default is used.",
    )
    observability_langfuse_public_key: str | None = Field(
        default=None,
        description="Langfuse public API key. Required for export unless service uses other auth mechanism.",
    )
    observability_langfuse_secret_key: str | None = Field(
        default=None,
        description="Langfuse secret API key. Required for export unless service uses other auth mechanism.",
    )
    observability_langfuse_debug: bool = Field(
        default=False,
        description="Enable verbose Langfuse debug logging in the sink.",
    )
    observability_langfuse_trace_name: str = Field(
        default="uni-agent-run",
        description="Base name used for run traces in Langfuse.",
    )
    observability_langfuse_trace_input_max_chars: int = Field(
        default=4000,
        description="Max chars to serialize task metadata into each Langfuse trace input payload.",
    )
    delegate_max_failed_rounds: int | None = Field(
        default=None,
        description=(
            "Optional cap on failed replan rounds for **child** runs started by delegate_task. "
            "Unset → same as orchestrator_max_failed_rounds."
        ),
    )
    delegate_tool_profile: DelegateToolProfile = Field(
        default="full",
        description="Tool set for child runs: full (same builtins as parent except delegate) or readonly subset.",
    )

    @model_validator(mode="after")
    def _anchor_memory_dir_under_workspace(self) -> Self:
        ws = self.workspace.resolve()
        md = self.memory_dir
        if md is None:
            anchored = (ws / ".uni-agent" / "memory").resolve()
        else:
            p = Path(md)
            anchored = p.resolve() if p.is_absolute() else (ws / p).resolve()
        object.__setattr__(self, "memory_dir", anchored)
        ca = self.ca_bundle
        if ca is not None:
            p = Path(ca)
            anchored_ca = p.resolve() if p.is_absolute() else (ws / p).resolve()
            object.__setattr__(self, "ca_bundle", anchored_ca)
        return self


def get_settings() -> Settings:
    return Settings()


def parse_sandbox_allowed_commands(raw: str) -> set[str]:
    return {part.strip() for part in raw.split(",") if part.strip()}


def parse_http_fetch_allowed_hosts(raw: str) -> frozenset[str]:
    return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())
