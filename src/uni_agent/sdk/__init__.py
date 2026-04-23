"""Programmatic (SDK) entry: :class:`AgentConfig`, :class:`AgentClient`, and :class:`AgentRegistry`.

Streaming: pass ``on_event=`` to :func:`create_client`; event ``dict`` schema matches CLI
``--stream`` (NDJSON). See ``docs/sdk-streaming.md``. Concurrency: ``docs/sdk-concurrency.md``.
Runtime: ``build_orchestrator`` + ``.orchestrator`` — ``docs/sdk-runtime.md``.
"""

from __future__ import annotations

from uni_agent.sdk.client import AgentClient, create_client
from uni_agent.sdk.config import AgentConfig
from uni_agent.sdk.loader import load_agent_configs_from_file, load_agent_registry_from_file
from uni_agent.sdk.registry import AgentRegistry

__all__ = [
    "AgentConfig",
    "AgentClient",
    "AgentRegistry",
    "create_client",
    "load_agent_configs_from_file",
    "load_agent_registry_from_file",
]
