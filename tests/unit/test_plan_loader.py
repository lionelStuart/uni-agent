from pathlib import Path

import pytest

from uni_agent.agent.plan_loader import load_plan_file


def test_load_plan_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "plan.yaml"
    path.write_text(
        """
steps:
  - id: step-1
    description: read
    tool: file_read
    arguments:
      path: README.md
""".strip(),
        encoding="utf-8",
    )

    plan = load_plan_file(path)

    assert len(plan) == 1
    assert plan[0].tool == "file_read"
    assert plan[0].arguments["path"] == "README.md"


def test_load_plan_rejects_unknown_suffix(tmp_path: Path) -> None:
    path = tmp_path / "plan.txt"
    path.write_text("steps: []", encoding="utf-8")
    with pytest.raises(ValueError):
        load_plan_file(path)
