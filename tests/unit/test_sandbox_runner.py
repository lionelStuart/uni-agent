from pathlib import Path

import pytest

from uni_agent.sandbox.runner import LocalSandbox, SandboxError


def test_sandbox_blocks_disallowed_commands() -> None:
    sandbox = LocalSandbox(Path("."))
    with pytest.raises(SandboxError):
        sandbox.run(["rm", "-rf", "/tmp/nope"])


def test_sandbox_runs_disallowed_after_approval() -> None:
    sandbox = LocalSandbox(Path("."), approve_non_allowlisted=lambda _b, _a: True)
    out = sandbox.run(["true"])
    assert out == ""


def test_sandbox_denies_when_approval_returns_false() -> None:
    sandbox = LocalSandbox(Path("."), approve_non_allowlisted=lambda _b, _a: False)
    with pytest.raises(SandboxError, match="not approved"):
        sandbox.run(["true"])

