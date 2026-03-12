from pathlib import Path

import pytest

from uni_agent.sandbox.runner import LocalSandbox, SandboxError


def test_sandbox_blocks_disallowed_commands() -> None:
    sandbox = LocalSandbox(Path("."))
    with pytest.raises(SandboxError):
        sandbox.run(["rm", "-rf", "/tmp/nope"])

