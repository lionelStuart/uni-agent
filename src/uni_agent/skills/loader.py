from __future__ import annotations

import logging
from pathlib import Path

import yaml

from uni_agent.shared.models import SkillSpec
from uni_agent.skills.bundle import (
    build_instruction_text,
    discover_reference_paths,
    discover_script_paths,
    parse_skill_md,
)

logger = logging.getLogger(__name__)

_DEFAULT_MAX_INSTRUCTION = 60_000
_DEFAULT_INLINE_REF = 6_000


def _normalize_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value]
    if isinstance(value, str):
        return [value]
    return [str(value)]


class SkillLoader:
    """Load every immediate child directory of ``skills_dir`` that contains ``SKILL.md`` or ``skill.yaml``."""

    def __init__(
        self,
        skills_dir: Path,
        workspace: Path | None = None,
        *,
        inline_reference_max_chars: int = _DEFAULT_INLINE_REF,
        max_instruction_chars: int = _DEFAULT_MAX_INSTRUCTION,
    ) -> None:
        self.skills_dir = Path(skills_dir)
        self.workspace = Path(workspace).resolve() if workspace is not None else None
        self.inline_reference_max_chars = max(0, inline_reference_max_chars)
        self.max_instruction_chars = max(1, max_instruction_chars)

    def load_all(self) -> list[SkillSpec]:
        root = self.skills_dir
        if not root.exists() or not root.is_dir():
            return []

        skills: list[SkillSpec] = []
        for child in sorted(root.iterdir(), key=lambda p: p.name):
            if not child.is_dir():
                continue
            spec = self._load_skill_directory(child)
            if spec is not None:
                skills.append(spec)
        return skills

    def _load_skill_directory(self, d: Path) -> SkillSpec | None:
        skill_md = d / "SKILL.md"
        manifest = d / "skill.yaml"

        if skill_md.is_file():
            return self._load_skill_md_dir(d, skill_md, manifest)
        if manifest.is_file():
            return self._load_yaml_manifest_dir(d, manifest)
        return None

    def _load_skill_md_dir(self, d: Path, skill_md: Path, manifest: Path) -> SkillSpec | None:
        fm, body = parse_skill_md(skill_md)
        yaml_raw: dict = {}
        if manifest.is_file():
            try:
                yaml_raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError) as exc:
                logger.warning("Skipping invalid skill.yaml in %s: %s", d, exc)
                yaml_raw = {}
        if not isinstance(yaml_raw, dict):
            yaml_raw = {}

        name = str(fm.get("name") or yaml_raw.get("name") or d.name)
        version = str(fm.get("version") or yaml_raw.get("version") or "0.0.0")
        description = fm.get("description", yaml_raw.get("description", ""))
        if not isinstance(description, str):
            description = str(description)

        triggers = _normalize_str_list(fm.get("triggers", yaml_raw.get("triggers", [])))

        priority_val = fm.get("priority", yaml_raw.get("priority", 0))
        try:
            priority = int(priority_val)
        except (TypeError, ValueError):
            priority = 0

        allowed = _normalize_str_list(fm.get("allowed_tools", yaml_raw.get("allowed_tools", [])))
        required = _normalize_str_list(fm.get("required_tools", yaml_raw.get("required_tools", [])))

        entry = "SKILL.md"
        if yaml_raw.get("entry"):
            entry = str(yaml_raw["entry"])

        ref_paths = discover_reference_paths(d)
        script_paths = discover_script_paths(d)
        instr, ref_rel, script_rel = build_instruction_text(
            name=name,
            load_format="skill_md",
            skill_root=d,
            main_body=body,
            reference_files=ref_paths,
            script_files=script_paths,
            workspace=self.workspace,
            inline_reference_max_chars=self.inline_reference_max_chars,
            max_total_chars=self.max_instruction_chars,
        )
        return SkillSpec(
            name=name,
            version=version,
            description=description,
            triggers=triggers,
            priority=priority,
            required_tools=required,
            allowed_tools=allowed,
            entry=entry,
            path=str(d.resolve()),
            skill_load_format="skill_md",
            instruction_text=instr,
            reference_paths=ref_rel,
            script_paths=script_rel,
        )

    def _load_yaml_manifest_dir(self, d: Path, manifest: Path) -> SkillSpec | None:
        try:
            raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            logger.warning("Invalid skill manifest %s: %s", manifest, exc)
            return None
        if not isinstance(raw, dict):
            return None
        raw["path"] = str(d.resolve())
        try:
            spec = SkillSpec.model_validate(raw)
        except Exception as exc:
            logger.warning("SkillSpec validation failed for %s: %s", manifest, exc)
            return None

        entry_path = d / spec.entry
        body = ""
        if entry_path.is_file():
            try:
                body = entry_path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("Could not read skill entry %s: %s", entry_path, exc)

        ref_paths = discover_reference_paths(d)
        script_paths = discover_script_paths(d)
        instr, ref_rel, script_rel = build_instruction_text(
            name=spec.name,
            load_format="yaml_manifest",
            skill_root=d,
            main_body=body,
            reference_files=ref_paths,
            script_files=script_paths,
            workspace=self.workspace,
            inline_reference_max_chars=self.inline_reference_max_chars,
            max_total_chars=self.max_instruction_chars,
        )
        return spec.model_copy(
            update={
                "instruction_text": instr,
                "reference_paths": ref_rel,
                "script_paths": script_rel,
                "skill_load_format": "yaml_manifest",
            }
        )
