from __future__ import annotations

import subprocess
from pathlib import Path


class SandboxError(RuntimeError):
    pass


class LocalSandbox:
    def __init__(
        self,
        workspace: Path,
        allowed_commands: set[str] | None = None,
        max_output_chars: int = 4000,
    ):
        self.workspace = workspace.resolve()
        self.allowed_commands = allowed_commands or {"pwd", "ls", "cat", "echo", "python", "python3", "rg"}
        self.max_output_chars = max_output_chars

    def run(self, command: list[str], timeout: int = 30) -> str:
        if not command:
            raise SandboxError("Empty command is not allowed.")

        binary = command[0]
        if binary not in self.allowed_commands:
            raise SandboxError(f"Command '{binary}' is not allowed in the local sandbox.")

        completed = subprocess.run(
            command,
            cwd=self.workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = completed.stdout.strip()
        error = completed.stderr.strip()
        if completed.returncode != 0:
            raise SandboxError(error or f"Command failed with exit code {completed.returncode}.")
        return self._truncate(output)

    def _truncate(self, output: str) -> str:
        if len(output) <= self.max_output_chars:
            return output
        return f"{output[: self.max_output_chars]}... [truncated]"
