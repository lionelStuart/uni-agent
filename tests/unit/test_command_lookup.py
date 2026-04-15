import json

import pytest

from uni_agent.agent.pydantic_planner import PydanticAIPlanner
from uni_agent.agent.llm import EnvLLMProvider
from uni_agent.tools.command_lookup import run_command_lookup
from uni_agent.tools.registry import ToolRegistry


def test_run_command_lookup_resolves_echo() -> None:
    out = run_command_lookup(name="echo", prefix=None, include_help=True, max_list=60)
    data = json.loads(out)
    assert data["mode"] == "resolve"
    assert data["name"] == "echo"
    assert data["found"] is True
    assert data["path"]
    assert "help_excerpt" in data  # may be null if the binary prints nothing for --help/-h


def test_run_command_lookup_unknown_command() -> None:
    out = run_command_lookup(name="zzznonexistent999xyz", prefix=None, include_help=False, max_list=60)
    data = json.loads(out)
    assert data["found"] is False
    assert data["path"] is None


def test_run_command_lookup_prefix_returns_sorted_names() -> None:
    out = run_command_lookup(name=None, prefix="py", include_help=True, max_list=20)
    data = json.loads(out)
    assert data["mode"] == "list"
    assert data["prefix"] == "py"
    assert isinstance(data["names"], list)
    assert data["count"] == len(data["names"])


def test_run_command_lookup_requires_name_or_prefix() -> None:
    with pytest.raises(ValueError, match="requires"):
        run_command_lookup(name=None, prefix=None, include_help=True, max_list=60)


def test_pydantic_planner_validates_command_lookup() -> None:
    planner = PydanticAIPlanner(provider=EnvLLMProvider("openai:gpt-4.1-mini"), defer_model_check=True)
    assert planner._arguments_valid("command_lookup", {"name": "git"})
    assert planner._arguments_valid("command_lookup", {"prefix": "gi"})
    assert planner._arguments_valid(
        "command_lookup", {"name": "ls", "include_help": False}
    )
    assert not planner._arguments_valid("command_lookup", {})
    assert not planner._arguments_valid("command_lookup", {"name": ""})
    assert not planner._arguments_valid("command_lookup", {"max_list": 999})


def test_command_lookup_registry_execute() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    from uni_agent.tools.builtins import register_builtin_handlers
    from uni_agent.sandbox.runner import LocalSandbox
    from pathlib import Path

    ws = Path(".")
    register_builtin_handlers(registry, ws, LocalSandbox(ws))
    raw = registry.execute("command_lookup", {"name": "echo", "include_help": False})
    data = json.loads(raw)
    assert data["found"] is True
