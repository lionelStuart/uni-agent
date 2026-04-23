"""High-level client wrapping :func:`~uni_agent.bootstrap.build_orchestrator`."""

from __future__ import annotations

from uni_agent.agent.orchestrator import Orchestrator, StreamEventCallback
from uni_agent.bootstrap import build_orchestrator
from uni_agent.sdk.config import AgentConfig
from uni_agent.shared.models import PlanStep, TaskResult


def create_client(
    config: AgentConfig,
    *,
    on_event: StreamEventCallback | None = None,
) -> AgentClient:
    """Create a client: one :class:`Orchestrator` per call via :func:`uni_agent.bootstrap.build_orchestrator` with
    ``settings=config.to_settings()`` and the given ``stream_event`` (``on_event``). No parallel bootstrap path.
    """
    return AgentClient(config, on_event=on_event)


class AgentClient:
    """Programmatic entry: ``run`` / ``replay`` with optional stream callback (orchestrator ``stream_event``)."""

    def __init__(
        self,
        config: AgentConfig,
        *,
        on_event: StreamEventCallback | None = None,
        orchestrator: Orchestrator | None = None,
    ) -> None:
        self._config = config
        self._orchestrator = orchestrator or build_orchestrator(
            stream_event=on_event,
            settings=config.to_settings(),
        )

    @property
    def config(self) -> AgentConfig:
        return self._config

    @property
    def orchestrator(self) -> Orchestrator:
        """The same :class:`~uni_agent.agent.orchestrator.Orchestrator` used by :meth:`run` / :meth:`replay`.

        For tools/tests/telemetry (e.g. ``.tool_registry``). Per-call custom streaming is not a hot-swap: use
        a new :func:`create_client` (new ``build_orchestrator``) if a different stream callback is required.
        """
        return self._orchestrator

    def run(
        self,
        task: str,
        plan_override: list[PlanStep] | None = None,
        *,
        session_context: str | None = None,
    ) -> TaskResult:
        return self._orchestrator.run(
            task,
            plan_override=plan_override,
            session_context=session_context,
        )

    def replay(self, run_id: str) -> TaskResult:
        return self._orchestrator.replay(run_id)
