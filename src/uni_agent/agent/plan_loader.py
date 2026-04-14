from __future__ import annotations

import json
from pathlib import Path

import yaml

from uni_agent.shared.models import PlanStep


def load_plan_file(path: Path) -> list[PlanStep]:
    """Load a static plan from YAML or JSON (suffix decides format)."""
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        payload = yaml.safe_load(text) or {}
    elif suffix == ".json":
        payload = json.loads(text)
    else:
        raise ValueError(f"Unsupported plan file type '{suffix}' (use .yaml, .yml, or .json).")

    if not isinstance(payload, dict):
        raise ValueError("Plan file must contain a mapping with a 'steps' list.")

    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("Plan file must include a non-empty 'steps' list.")

    return [PlanStep.model_validate(item) for item in raw_steps]
