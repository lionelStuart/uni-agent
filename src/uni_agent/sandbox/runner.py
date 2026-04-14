from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from uni_agent.config.settings import DEFAULT_SANDBOX_ALLOWED_COMMANDS, parse_sandbox_allowed_commands

ApproveNonAllowlisted = Callable[[str, list[str]], bool]

_BUILTIN_SANDBOX_ALLOWLIST = parse_sandbox_allowed_commands(DEFAULT_SANDBOX_ALLOWED_COMMANDS)


class SandboxError(RuntimeError):
    pass


def prompt_tty_approve_disallowed_command(binary: str, argv: list[str]) -> bool:
    """Prompt on stderr; return True only if the user enters Y (case-insensitive). Non-TTY returns False."""
    if not sys.stdin.isatty():
        return False
    print(f"\n[sandbox] Command not on allowlist: {binary}", file=sys.stderr)
    print(f"[sandbox] argv: {argv!r}", file=sys.stderr)
    try:
        line = input("Allow this command once? [y/N] ")
    except EOFError:
        return False
    return line.strip().upper() == "Y"


class LocalSandbox:
    def __init__(
        self,
        workspace: Path,
        allowed_commands: set[str] | None = None,
        max_output_chars: int = 4000,
        command_timeout: int = 30,
        approve_non_allowlisted: ApproveNonAllowlisted | None = None,
    ):
        self.workspace = workspace.resolve()
        self.allowed_commands = allowed_commands or set(_BUILTIN_SANDBOX_ALLOWLIST)
        self.max_output_chars = max_output_chars
        self.command_timeout = command_timeout
        self._approve_non_allowlisted = approve_non_allowlisted

    def run(
        self,
        command: list[str],
        timeout: int | None = None,
        *,
        accept_exit_codes: frozenset[int] | None = None,
    ) -> str:
        if not command:
            raise SandboxError("Empty command is not allowed.")

        binary = command[0]
        if binary not in self.allowed_commands:
            if self._approve_non_allowlisted is None:
                raise SandboxError(f"Command '{binary}' is not allowed in the local sandbox.")
            if not self._approve_non_allowlisted(binary, command):
                raise SandboxError(
                    f"Command '{binary}' is not on the sandbox allowlist and was not approved."
                )

        effective_timeout = self.command_timeout if timeout is None else timeout
        completed = subprocess.run(
            command,
            cwd=self.workspace,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            check=False,
        )
        output = completed.stdout.strip()
        error = completed.stderr.strip()
        ok = frozenset({0}) if accept_exit_codes is None else accept_exit_codes
        if completed.returncode not in ok:
            raise SandboxError(error or f"Command failed with exit code {completed.returncode}.")
        return self._truncate(output)

    def _truncate(self, output: str) -> str:
        if len(output) <= self.max_output_chars:
            return output
        return f"{output[: self.max_output_chars]}... [truncated]"
