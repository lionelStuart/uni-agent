import shutil

import pytest

from uni_agent.agent.llm import EnvLLMProvider
from uni_agent.agent.pydantic_planner import PydanticAIPlanner
from uni_agent.sandbox.runner import LocalSandbox, SandboxError
from uni_agent.tools.builtins import register_builtin_handlers
from uni_agent.tools.registry import ToolRegistry

_py = "python3" if shutil.which("python3") else ("python" if shutil.which("python") else None)
requires_python = pytest.mark.skipif(_py is None, reason="python3/python not on PATH")


@requires_python
def test_run_python_prints_stdout(tmp_path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    registry = ToolRegistry()
    registry.register_builtin_tools()
    register_builtin_handlers(registry, workspace, LocalSandbox(workspace))
    out = registry.execute("run_python", {"source": 'print("hello-run-python")'})
    assert "hello-run-python" in out


@requires_python
def test_run_python_syntax_error_raises(tmp_path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    registry = ToolRegistry()
    registry.register_builtin_tools()
    register_builtin_handlers(registry, workspace, LocalSandbox(workspace))
    with pytest.raises(SandboxError):
        registry.execute("run_python", {"source": "this is not valid python !!!"})


def test_run_python_pydantic_validation() -> None:
    planner = PydanticAIPlanner(provider=EnvLLMProvider("openai:gpt-4.1-mini"), defer_model_check=True)
    assert planner._arguments_valid("run_python", {"source": "print(1)"})
    assert not planner._arguments_valid("run_python", {"source": ""})
    assert not planner._arguments_valid("run_python", {"timeout_seconds": 200})


@requires_python
def test_sandbox_append_stderr_on_success(tmp_path) -> None:
    sandbox = LocalSandbox(
        tmp_path,
        allowed_commands={"python3", "python"},
        command_timeout=30,
    )
    (tmp_path / "s.py").write_text("import sys\nprint('out')\nprint('err', file=sys.stderr)\n", encoding="utf-8")
    out = sandbox.run([_py, "s.py"], append_stderr=True)
    assert "out" in out
    assert "err" in out
