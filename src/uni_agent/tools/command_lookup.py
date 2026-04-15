"""Resolve commands on PATH and optionally capture --help; list executables by basename prefix."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

# Single PATH segment, e.g. git, python3, my-tool
CMD_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.+-]{0,255}$")
# Prefix for discovery listing (no glob metacharacters)
CMD_PREFIX_RE = re.compile(r"^[a-zA-Z0-9_.+-]{1,32}$")

_HELP_MAX_CHARS = 12_000
_LIST_MAX_DEFAULT = 60
_LIST_MAX_HARD = 200
_HELP_TIMEOUT = 15.0


def run_command_lookup(
    *,
    name: str | None,
    prefix: str | None,
    include_help: bool,
    max_list: int,
) -> str:
    """Build JSON text for the command_lookup tool."""
    has_name = bool(name and str(name).strip())
    has_prefix = bool(prefix and str(prefix).strip())

    if not has_name and not has_prefix:
        raise ValueError("command_lookup requires non-empty 'name' and/or 'prefix'.")

    if has_name:
        n = str(name).strip()
        if not CMD_NAME_RE.match(n):
            raise ValueError(
                "command_lookup 'name' must be a single command token (letters, digits, ._+-)."
            )
        return _resolve_one(n, include_help=include_help)

    p = str(prefix).strip()
    if not CMD_PREFIX_RE.match(p):
        raise ValueError("command_lookup 'prefix' must be 1–32 chars of [a-zA-Z0-9_.+-].")
    cap = max(1, min(_LIST_MAX_HARD, int(max_list)))
    return _list_by_prefix(p, cap)


def _resolve_one(name: str, *, include_help: bool) -> str:
    path = shutil.which(name)
    payload: dict = {
        "mode": "resolve",
        "name": name,
        "found": path is not None,
        "path": path,
    }
    if path and include_help:
        excerpt, flag = _try_help_excerpt(path)
        payload["help_flag_tried"] = flag
        payload["help_excerpt"] = excerpt
    out = json.dumps(payload, ensure_ascii=False, indent=2)
    return _truncate_text(out, _HELP_MAX_CHARS + 500)


def _try_help_excerpt(resolved_path: str) -> tuple[str | None, str | None]:
    for flag in ("--help", "-h", "help"):
        try:
            completed = subprocess.run(
                [resolved_path, flag],
                capture_output=True,
                text=True,
                timeout=_HELP_TIMEOUT,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        combined = (completed.stdout or "") + (
            ("\n" + completed.stderr) if completed.stderr else ""
        )
        if combined.strip():
            return _truncate_text(combined.strip(), _HELP_MAX_CHARS), flag
    return None, None


def _list_by_prefix(prefix: str, max_results: int) -> str:
    pl = prefix.lower()
    found: list[str] = []
    seen: set[str] = set()
    for raw in os.environ.get("PATH", "").split(os.pathsep):
        if not raw or len(found) >= max_results:
            break
        try:
            d = Path(raw)
            if not d.is_dir():
                continue
            for child in sorted(d.iterdir()):
                if len(found) >= max_results:
                    break
                try:
                    if not child.is_file():
                        continue
                    if not os.access(child, os.X_OK):
                        continue
                except OSError:
                    continue
                base = child.name
                if base.lower().startswith(pl) and base not in seen:
                    seen.add(base)
                    found.append(base)
        except OSError:
            continue
    found.sort()
    payload = {
        "mode": "list",
        "prefix": prefix,
        "count": len(found),
        "names": found,
        "hint": "Use mode 'resolve' with a specific name to get the absolute path and optional --help.",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}\n... [truncated at {max_chars} characters]"
