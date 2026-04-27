from __future__ import annotations

from pathlib import Path

import yaml

from uni_agent.evals.models import EvalCase


def load_eval_cases(path: Path) -> list[EvalCase]:
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted(
            item
            for item in path.rglob("*")
            if item.is_file()
            and item.suffix.lower() in {".yaml", ".yml"}
            and "plans" not in item.relative_to(path).parts
        )
    else:
        raise FileNotFoundError(f"Eval path does not exist: {path}")

    cases: list[EvalCase] = []
    for file in files:
        payload = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"Eval case must be a mapping: {file}")
        case = EvalCase.model_validate(payload)
        cases.append(case.model_copy(update={"source_path": file}))
    if not cases:
        raise ValueError(f"No eval case YAML files found under: {path}")
    return cases
