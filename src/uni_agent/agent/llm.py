from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic_ai.models import Model, parse_model_id
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.profiles.qwen import qwen_model_profile
from pydantic_ai.providers.openai import OpenAIProvider


def _gateway_openai_profile(model_id: str) -> OpenAIModelProfile:
    """Merge provider-specific profile with flags that avoid ``tool_choice=required`` (Qwen thinking / Soul gateway)."""
    base: ModelProfile | None = qwen_model_profile(model_id)
    if base is None:
        base = OpenAIProvider.model_profile(model_id)
    if base is None:
        base = ModelProfile()
    return OpenAIModelProfile.from_profile(base).update(
        OpenAIModelProfile(openai_supports_tool_choice_required=False)
    )


def _is_qwen_openai_model(model_name: str) -> bool:
    try:
        provider_name, chat_model = parse_model_id(model_name)
    except Exception:
        return False
    if provider_name not in ("openai", "openai-chat", "openai-responses"):
        return False
    return "qwen" in chat_model.lower()


@runtime_checkable
class LLMProvider(Protocol):
    """Supplies model identity and whether an LLM-backed planner can run."""

    @property
    def model_id(self) -> str: ...

    def is_available(self) -> bool: ...


def build_planner_model(
    model_name: str,
    *,
    openai_base_url: str | None = None,
    openai_api_key: str | None = None,
) -> str | Model:
    """Build a PydanticAI model: use explicit OpenAI-compatible client when URL/key are set in config.

    If both URL/key overrides are absent, returns ``model_name`` unless the model looks like Qwen on the
    OpenAI-compatible API — then returns an :class:`OpenAIChatModel` with ``tool_choice`` forced to ``auto``
    via profile (fixes gateways that reject ``tool_choice=required`` in thinking mode).

    When overrides are set, builds an explicit :class:`OpenAIProvider` (same as ``UNI_AGENT_OPENAI_*``).
    """
    try:
        provider_name, chat_model = parse_model_id(model_name)
    except Exception:
        return model_name

    if provider_name not in ("openai", "openai-chat", "openai-responses"):
        return model_name

    profile = _gateway_openai_profile(chat_model)

    if openai_base_url is not None or openai_api_key is not None:
        oa_provider = OpenAIProvider(base_url=openai_base_url, api_key=openai_api_key)
        return OpenAIChatModel(chat_model, provider=oa_provider, profile=profile)

    if _is_qwen_openai_model(model_name):
        oa_provider = OpenAIProvider()
        return OpenAIChatModel(chat_model, provider=oa_provider, profile=profile)

    return model_name


@dataclass
class EnvLLMProvider:
    """Uses config (``UNI_AGENT_*``) and common vendor env vars for availability and overrides."""

    model_name: str
    openai_base_url: str | None = None
    openai_api_key: str | None = None

    @property
    def model_id(self) -> str:
        return self.model_name

    def is_available(self) -> bool:
        provider_name, _ = parse_model_id(self.model_name)
        if provider_name in ("openai", "openai-chat", "openai-responses"):
            if self.openai_base_url is not None:
                return True
            if self.openai_api_key:
                return True
            return bool(os.getenv("OPENAI_API_KEY"))
        if provider_name == "anthropic":
            return bool(os.getenv("ANTHROPIC_API_KEY"))
        return bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))
