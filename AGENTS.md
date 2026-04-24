# AGENTS.md

## Local verification

- Prefer the local virtual environment at `.venv/` for Python commands and tests.
- A typical local check is to activate `.venv` and run the project from the repo root.
- Use `uni-agent client` to start an interactive agent session for end-to-end verification.
- While the client is running, observe the agent's startup and step execution output to confirm whether the intended behavior was achieved.
- When validating a feature, prefer confirming both:
  - the visible execution process in `uni-agent client`
  - the final result returned by the agent
