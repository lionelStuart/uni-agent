---
name: code-runner
description: >-
  Use when the user needs to run short Python code in the workspace: calculations, data transforms,
  quick scripts, or validating snippets against project packages. Prefer run_python over shell_exec
  for Python one-offs; cwd is the workspace root.
version: "1.0.0"
triggers:
  - python
  - 执行代码
  - 运行代码
  - run python
  - 算一下
  - snippet
priority: 3
allowed_tools:
  - run_python
  - command_lookup
  - file_read
  - search_workspace
---

# Code runner (Python)

## When to use

- Numeric or logical **calculation** the model should not do by hand.
- **Quick Python** to parse, transform, or probe data that already lives in the repo.
- **Smoke-test** a small import from the project (`import mypkg` with cwd = workspace).

## Prefer `run_python`

- Pass the full script as `source`. The runtime writes a temp file under `.uni-agent/code_run/`, executes it with `python3` or `python`, then removes the file.
- **Working directory** is the **workspace root** — use relative paths for project files.
- Optional `timeout_seconds` (1–120, default 30). Stderr is included in the tool output when non-empty.
- Do not start long-lived servers or background jobs.

## If flags or CLIs are unclear

Use `command_lookup` with `name` to read `--help` before composing `shell_exec` argv.

## Safety

- Treat user-supplied code as trusted only within this workspace context.
- Avoid exfiltrating secrets; do not paste tokens into `source`.
