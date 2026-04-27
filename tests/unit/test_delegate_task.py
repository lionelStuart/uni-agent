from pathlib import Path

import pytest

from uni_agent.bootstrap import build_orchestrator
from uni_agent.sandbox.runner import LocalSandbox
from uni_agent.shared.models import TaskResult, TaskStatus
from uni_agent.tools.builtins import register_builtin_handlers
from uni_agent.tools.registry import ToolRegistry


def test_child_orchestrator_has_no_delegate_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNI_AGENT_TASK_LOG_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("UNI_AGENT_SKILLS_DIR", str(tmp_path / "skills"))
    monkeypatch.setenv("UNI_AGENT_WORKSPACE", str(tmp_path / "ws"))
    (tmp_path / "skills").mkdir()
    (tmp_path / "ws").mkdir()

    orch = build_orchestrator(enable_delegate_tool=False, stream_event=None)
    names = orch.tool_registry.names()
    assert "delegate_task" not in names


def test_readonly_profile_excludes_shell_and_delegate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNI_AGENT_TASK_LOG_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("UNI_AGENT_SKILLS_DIR", str(tmp_path / "skills"))
    monkeypatch.setenv("UNI_AGENT_WORKSPACE", str(tmp_path / "ws"))
    (tmp_path / "skills").mkdir()
    (tmp_path / "ws").mkdir()

    orch = build_orchestrator(
        enable_delegate_tool=False,
        tool_profile="readonly",
        stream_event=None,
    )
    names = set(orch.tool_registry.names())
    assert names == {"file_read", "search_workspace", "memory_search", "command_lookup"}


def test_delegate_format_contains_run_ids() -> None:
    from uni_agent.tools.delegate_format import format_delegate_result

    child = TaskResult(
        run_id="childid12",
        task="sub",
        status=TaskStatus.COMPLETED,
        output="out",
        conclusion="done",
    )
    text = format_delegate_result(child=child, parent_run_id="parentid12")
    assert "CHILD_RUN_ID=childid12" in text
    assert "PARENT_RUN_ID=parentid12" in text
    assert "STATUS=completed" in text


def test_wrap_child_stream_adds_delegation_meta() -> None:
    from uni_agent.tools.delegation_stream import wrap_child_stream

    seen: list[dict] = []

    def inner(ev: dict) -> None:
        seen.append(ev)

    wrapped = wrap_child_stream("par123", inner)
    assert wrapped is not None
    wrapped({"type": "run_begin", "run_id": "c1"})
    assert len(seen) == 1
    assert seen[0]["delegation"]["phase"] == "child"
    assert seen[0]["delegation"]["parent_run_id"] == "par123"


def test_delegate_handler_outside_run_returns_failed_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("UNI_AGENT_TASK_LOG_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("UNI_AGENT_SKILLS_DIR", str(tmp_path / "skills"))
    monkeypatch.setenv("UNI_AGENT_WORKSPACE", str(tmp_path / "ws"))
    (tmp_path / "skills").mkdir()
    (tmp_path / "ws").mkdir()

    reg = ToolRegistry()
    reg.register_builtin_tools(include_delegate_task=True, tool_profile="full")
    sandbox = LocalSandbox(tmp_path / "ws", allowed_commands={"pwd"}, command_timeout=5)
    register_builtin_handlers(
        reg,
        tmp_path / "ws",
        sandbox,
        enable_delegate_tool=True,
        delegate_parent_stream_event=None,
    )
    out = reg.execute("delegate_task", {"task": "hello"})
    assert "STATUS=failed" in out or "failed" in out.lower()
    assert "CHILD_RUN_ID=" in out

    structured = reg.execute_result("delegate_task", {"task": "hello"})
    assert structured.status == "error"
    assert structured.payload["status"] == "failed"
    assert structured.error_code == "delegate_context_missing"
