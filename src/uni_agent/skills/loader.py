from __future__ import annotations

from pathlib import Path

import yaml

from uni_agent.shared.models import SkillSpec


class SkillLoader:
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir

    def load_all(self) -> list[SkillSpec]:
        if not self.skills_dir.exists():
            return []

        skills: list[SkillSpec] = []
        for manifest_path in sorted(self.skills_dir.glob("*/skill.yaml")):
            with manifest_path.open("r", encoding="utf-8") as handle:
                raw = yaml.safe_load(handle) or {}
            raw["path"] = str(manifest_path.parent.resolve())
            skills.append(SkillSpec.model_validate(raw))
        return skills

