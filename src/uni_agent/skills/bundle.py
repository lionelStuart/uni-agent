"""Codex / Claude Code / Cursor-style skill directories: ``SKILL.md`` + optional references and scripts."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from uni_agent.shared.models import SkillLoadFormat, SkillSpec

logger = logging.getLogger(__name__)

# English stopwords only; matcher uses these to reduce noise from long descriptions.
_DESCRIPTION_STOPWORDS = frozenset(
    {
        "when",
        "with",
        "from",
        "that",
        "this",
        "your",
        "will",
        "need",
        "have",
        "been",
        "were",
        "what",
        "which",
        "while",
        "where",
        "after",
        "before",
        "about",
        "into",
        "than",
        "then",
        "them",
        "they",
        "their",
        "there",
        "these",
        "those",
        "such",
        "only",
        "also",
        "just",
        "more",
        "most",
        "some",
        "very",
        "able",
        "user",
        "users",
        "skill",
        "skills",
        "agent",
        "codex",
        "cursor",
    }
)


def parse_skill_md(path: Path) -> tuple[dict[str, Any], str]:
    """Split YAML frontmatter and markdown body (Codex / Cursor ``SKILL.md`` convention)."""
    raw = path.read_text(encoding="utf-8")
    if raw.lstrip().startswith("---") is False:
        return {}, raw

    lines = raw.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, raw

    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, raw

    fm_text = "".join(lines[1:end])
    body = "".join(lines[end + 1 :])
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:
        logger.warning("Invalid YAML frontmatter in %s: %s", path, exc)
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, body


def discover_reference_paths(skill_root: Path) -> list[Path]:
    """Optional markdown references (Cursor layout + common filenames)."""
    paths: list[Path] = []
    for fname in ("reference.md", "examples.md", "REF.md"):
        p = skill_root / fname
        if p.is_file():
            paths.append(p)

    ref_dir = skill_root / "references"
    if ref_dir.is_dir():
        for p in sorted(ref_dir.glob("*.md")):
            if p.is_file():
                paths.append(p)
        for p in sorted(ref_dir.glob("*/*.md")):
            if p.is_file():
                paths.append(p)

    # Dedupe while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def discover_script_paths(skill_root: Path) -> list[Path]:
    d = skill_root / "scripts"
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.is_file())


def workspace_relative_posix(path: Path, workspace: Path | None) -> str:
    resolved = path.resolve()
    if workspace is None:
        return str(resolved)
    ws = workspace.resolve()
    try:
        return resolved.relative_to(ws).as_posix()
    except ValueError:
        return str(resolved)


def description_match_tokens(description: str, *, max_tokens: int = 24) -> list[str]:
    """Tokens for task matching when ``triggers`` is empty (Codex-style description-only skills)."""
    if not description.strip():
        return []
    lower = description.lower()
    tokens = re.findall(r"[a-z0-9]{4,}|[\u4e00-\u9fff]{2,}", lower)
    out: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        if t in seen or t in _DESCRIPTION_STOPWORDS:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= max_tokens:
            break
    return out


def planner_skill_context(selected_skills: list[SkillSpec]) -> str:
    """Concatenate non-empty ``instruction_text`` from matched skills (for LLM planner user prompt)."""
    parts = [s.instruction_text for s in selected_skills if s.instruction_text.strip()]
    if not parts:
        return ""
    return "\n\n".join(parts)


def build_instruction_text(
    *,
    name: str,
    load_format: SkillLoadFormat,
    skill_root: Path,
    main_body: str,
    reference_files: list[Path],
    script_files: list[Path],
    workspace: Path | None,
    inline_reference_max_chars: int,
    max_total_chars: int,
) -> tuple[str, list[str], list[str]]:
    """Compose planner-facing text; optionally inline small reference markdown files."""
    ref_rel = [workspace_relative_posix(p, workspace) for p in reference_files]
    script_rel = [workspace_relative_posix(p, workspace) for p in script_files]

    parts: list[str] = [
        f"### Active skill bundle: {name} ({load_format})\n",
        (main_body.strip() or "(no body in skill entry file)").strip(),
        "\n",
    ]

    inlined: list[str] = []
    listed_refs: list[str] = []

    for p, rel in zip(reference_files, ref_rel, strict=True):
        try:
            size = p.stat().st_size
        except OSError:
            listed_refs.append(rel)
            continue
        if size <= inline_reference_max_chars:
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                listed_refs.append(rel)
                continue
            if len(text) <= inline_reference_max_chars:
                inlined.append(f"#### Inlined reference: `{rel}`\n\n{text.strip()}\n")
            else:
                listed_refs.append(rel)
        else:
            listed_refs.append(rel)

    if inlined:
        parts.append("\n#### Bundled reference files (inlined)\n\n")
        parts.extend(inlined)

    if listed_refs:
        parts.append(
            "\n#### Bundled reference files (use `file_read` with path relative to workspace)\n\n"
        )
        parts.extend(f"- `{rel}`\n" for rel in listed_refs)

    if script_rel:
        parts.append(
            "\n#### Bundled scripts (sandbox cwd is workspace root; extend argv as needed)\n\n"
        )
        for rel in script_rel:
            parts.append(
                f"- `{rel}` — example: `shell_exec.command` = `[\"bash\", \"{rel}\"]` "
                f"or `[\"python3\", \"{rel}\"]`\n"
            )

    text = "".join(parts).strip()
    if len(text) > max_total_chars:
        text = text[: max_total_chars - 40] + "\n... [skill instruction bundle truncated]\n"

    return text, ref_rel, script_rel
