"""Construct a configured :class:`~uni_agent.agent.orchestrator.Orchestrator` (CLI and delegate_task)."""

from __future__ import annotations

from uni_agent.agent.llm import EnvLLMProvider
from uni_agent.agent.orchestrator import Orchestrator, StreamEventCallback
from uni_agent.agent.planner import HeuristicPlanner
from uni_agent.agent.pydantic_planner import PydanticAIPlanner
from uni_agent.agent.goal_check import GoalCheckSynthesizer
from uni_agent.agent.run_conclusion import RunConclusionSynthesizer
from uni_agent.config.settings import (
    DelegateToolProfile,
    Settings,
    get_settings,
    parse_http_fetch_allowed_hosts,
    parse_sandbox_allowed_commands,
)
from uni_agent.observability.logging import configure_logging
from uni_agent.observability.task_store import TaskStore
from uni_agent.sandbox.runner import LocalSandbox, prompt_tty_approve_disallowed_command
from uni_agent.skills.loader import SkillLoader
from uni_agent.tools.builtins import register_builtin_handlers
from uni_agent.tools.registry import ToolRegistry


def _sandbox_approval_callback(settings: Settings):
    if not settings.sandbox_prompt_for_disallowed:
        return None
    return prompt_tty_approve_disallowed_command


def build_orchestrator(
    *,
    stream_event: StreamEventCallback | None = None,
    enable_delegate_tool: bool = True,
    tool_profile: DelegateToolProfile = "full",
    max_failed_rounds_override: int | None = None,
    settings: Settings | None = None,
) -> Orchestrator:
    """Assemble planner, tools, sandbox, and task store.

    :param enable_delegate_tool: When false (child runs), ``delegate_task`` is not registered.
    :param tool_profile: ``full`` or ``readonly`` (subset of builtins). Parent CLI uses ``full``.
    :param max_failed_rounds_override: If set, replaces ``orchestrator_max_failed_rounds`` for this instance.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    tool_registry = ToolRegistry()
    tool_registry.register_builtin_tools(
        include_delegate_task=enable_delegate_tool,
        tool_profile=tool_profile,
    )
    allowed_commands = parse_sandbox_allowed_commands(settings.sandbox_allowed_commands)
    sandbox = LocalSandbox(
        settings.workspace,
        allowed_commands=allowed_commands,
        command_timeout=settings.sandbox_command_timeout_seconds,
        approve_non_allowlisted=_sandbox_approval_callback(settings),
    )
    provider = EnvLLMProvider(
        settings.model_name,
        openai_base_url=settings.openai_base_url,
        openai_api_key=settings.openai_api_key,
    )
    model_settings = None
    if settings.llm_temperature is not None:
        model_settings = {"temperature": settings.llm_temperature}
    register_builtin_handlers(
        tool_registry,
        settings.workspace,
        sandbox,
        http_fetch_max_bytes=settings.http_fetch_max_bytes,
        http_fetch_allow_private_networks=settings.http_fetch_allow_private_networks,
        http_fetch_allowed_hosts=parse_http_fetch_allowed_hosts(settings.http_fetch_allowed_hosts),
        http_fetch_timeout_seconds=settings.sandbox_command_timeout_seconds,
        ca_bundle_path=settings.ca_bundle,
        skip_tls_verify=settings.skip_tls_verify,
        memory_dir=settings.memory_dir,
        memory_llm_provider=provider,
        memory_search_use_llm=settings.memory_search_use_llm,
        memory_search_max_hits=settings.memory_search_max_hits,
        memory_search_model_settings=model_settings,
        memory_search_keyword_retries=settings.llm_retries,
        enable_delegate_tool=enable_delegate_tool,
        delegate_parent_stream_event=stream_event if enable_delegate_tool else None,
    )
    skill_loader = SkillLoader(settings.skills_dir, settings.workspace)
    heuristic = HeuristicPlanner()

    allowed_shell = frozenset(allowed_commands)
    if settings.planner_backend == "heuristic":
        planner = heuristic
    elif settings.planner_backend == "pydantic_ai":
        planner = PydanticAIPlanner(
            provider=provider,
            fallback=heuristic,
            planner_instructions=settings.planner_instructions,
            global_system_prompt=settings.global_system_prompt,
            model_settings=model_settings,
            retries=settings.llm_retries,
            allowed_shell_commands=allowed_shell,
        )
    else:
        planner = (
            PydanticAIPlanner(
                provider=provider,
                fallback=heuristic,
                planner_instructions=settings.planner_instructions,
                global_system_prompt=settings.global_system_prompt,
                model_settings=model_settings,
                retries=settings.llm_retries,
                allowed_shell_commands=allowed_shell,
            )
            if provider.is_available()
            else heuristic
        )
    task_store = TaskStore(settings.task_log_dir)
    conclusion_syn: RunConclusionSynthesizer | None = None
    if settings.run_conclusion_llm and provider.is_available():
        conclusion_syn = RunConclusionSynthesizer(
            provider=provider,
            model_settings=model_settings,
            retries=0,
            conclusion_system_prompt=settings.conclusion_system_prompt,
            global_system_prompt=settings.global_system_prompt,
        )
    goal_check: GoalCheckSynthesizer | None = None
    if settings.plan_goal_check_enabled and provider.is_available():
        goal_check = GoalCheckSynthesizer(
            provider=provider,
            model_settings=model_settings,
            retries=0,
            goal_check_system_prompt=settings.plan_goal_check_system_prompt,
            global_system_prompt=settings.global_system_prompt,
        )
    max_rounds = (
        max_failed_rounds_override
        if max_failed_rounds_override is not None
        else settings.orchestrator_max_failed_rounds
    )
    return Orchestrator(
        skill_loader=skill_loader,
        tool_registry=tool_registry,
        planner=planner,
        task_store=task_store,
        max_step_retries=settings.tool_step_retries,
        max_failed_rounds=max_rounds,
        conclusion_synthesizer=conclusion_syn,
        stream_event=stream_event,
        goal_check=goal_check,
        plan_goal_check_max_replan_rounds=settings.plan_goal_check_max_replan_rounds,
    )
