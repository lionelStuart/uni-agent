from pydantic_ai.models.openai import OpenAIChatModel

from uni_agent.agent.llm import EnvLLMProvider, build_planner_model


def test_build_planner_model_uses_string_without_overrides() -> None:
    assert build_planner_model("openai:gpt-4.1-mini") == "openai:gpt-4.1-mini"


def test_qwen_model_uses_openai_chat_with_tool_choice_compat_without_url_override(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    resolved = build_planner_model("openai:qwen3.5-plus")
    assert isinstance(resolved, OpenAIChatModel)
    assert resolved.profile.openai_supports_tool_choice_required is False


def test_build_planner_model_builds_openai_chat_with_base_url() -> None:
    resolved = build_planner_model(
        "openai:custom-model",
        openai_base_url="http://localhost:11434/v1",
        openai_api_key=None,
    )
    assert isinstance(resolved, OpenAIChatModel)
    assert resolved.profile.openai_supports_tool_choice_required is False


def test_env_llm_provider_available_with_only_base_url() -> None:
    provider = EnvLLMProvider(
        "openai:gpt-4.1-mini",
        openai_base_url="http://localhost:11434/v1",
        openai_api_key=None,
    )
    assert provider.is_available()
