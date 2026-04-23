"""In-process cache: one :class:`AgentClient` per logical ``agent_id`` (same id → same instance)."""

from __future__ import annotations

from uni_agent.agent.orchestrator import StreamEventCallback
from uni_agent.sdk.client import AgentClient, create_client
from uni_agent.sdk.config import AgentConfig


class AgentRegistry:
    """Registry for multi-tenant or multi-skillpack deployments in one process.

    **Note:** updating ``AgentConfig`` for the same ``agent_id`` after the first
    ``get_or_create`` does not replace the cached client; register again or use a new id.
    """

    def __init__(self) -> None:
        self._clients: dict[str, AgentClient] = {}

    def register(self, agent_id: str, client: AgentClient) -> None:
        self._clients[agent_id] = client

    def get(self, agent_id: str) -> AgentClient:
        return self._clients[agent_id]

    def get_or_create(
        self,
        agent_id: str,
        config: AgentConfig,
        *,
        on_event: StreamEventCallback | None = None,
    ) -> AgentClient:
        if agent_id not in self._clients:
            self._clients[agent_id] = create_client(config, on_event=on_event)
        return self._clients[agent_id]

    def __contains__(self, agent_id: str) -> bool:  # pragma: no cover - trivial
        return agent_id in self._clients

    def __len__(self) -> int:  # pragma: no cover
        return len(self._clients)
