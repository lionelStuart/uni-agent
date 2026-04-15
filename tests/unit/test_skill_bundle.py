from pathlib import Path

from uni_agent.skills.bundle import parse_skill_md, planner_skill_context
from uni_agent.skills.loader import SkillLoader
from uni_agent.shared.models import SkillSpec


def test_parse_skill_md_frontmatter_and_body(tmp_path: Path) -> None:
    p = tmp_path / "SKILL.md"
    p.write_text(
        "---\nname: demo\ndescription: Use when testing skill loader.\n---\n\n# Body\n\nHello.\n",
        encoding="utf-8",
    )
    fm, body = parse_skill_md(p)
    assert fm["name"] == "demo"
    assert "testing" in fm["description"]
    assert "# Body" in body
    assert "Hello." in body


def test_skill_loader_loads_skill_md_and_discovers_assets(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    skills = tmp_path / "skills"
    sdir = skills / "demo-skill"
    sdir.mkdir(parents=True)
    (sdir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Widget frobnitz alignment for tests.\n"
        "triggers:\n  - frobnitz\npriority: 3\n---\n\n# Demo\n\nRun the frobnitz workflow.\n",
        encoding="utf-8",
    )
    ref = sdir / "references"
    ref.mkdir()
    (ref / "extra.md").write_text("More detail.", encoding="utf-8")
    scr = sdir / "scripts"
    scr.mkdir()
    (scr / "run.sh").write_text("#!/bin/sh\necho ok\n", encoding="utf-8")

    loader = SkillLoader(skills, ws)
    loaded = loader.load_all()
    assert len(loaded) == 1
    spec = loaded[0]
    assert spec.name == "demo-skill"
    assert spec.skill_load_format == "skill_md"
    assert "frobnitz workflow" in spec.instruction_text
    assert "Inlined reference" in spec.instruction_text or "extra.md" in spec.instruction_text
    assert any("run.sh" in line for line in spec.script_paths) or "run.sh" in spec.instruction_text


def test_skill_loader_merges_skill_yaml_with_skill_md(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    skills = tmp_path / "skills"
    sdir = skills / "merged"
    sdir.mkdir(parents=True)
    (sdir / "SKILL.md").write_text(
        "---\nname: from-md\ndescription: MD wins for name in merge test.\n---\n\nBody.\n",
        encoding="utf-8",
    )
    (sdir / "skill.yaml").write_text(
        "name: ignored\n"
        "version: '2.0.0'\n"
        "allowed_tools:\n  - file_read\n"
        "triggers:\n  - mergecue\n",
        encoding="utf-8",
    )
    spec = SkillLoader(skills, ws).load_all()[0]
    assert spec.name == "from-md"
    assert spec.version == "2.0.0"
    assert "file_read" in spec.allowed_tools
    assert "mergecue" in spec.triggers


def test_planner_skill_context_joins_instructions() -> None:
    a = SkillSpec(
        name="a",
        version="1",
        description="d",
        path="/x",
        instruction_text="First block.",
    )
    b = SkillSpec(
        name="b",
        version="1",
        description="d",
        path="/y",
        instruction_text="",
    )
    c = SkillSpec(
        name="c",
        version="1",
        description="d",
        path="/z",
        instruction_text="Second block.",
    )
    text = planner_skill_context([a, b, c])
    assert "First block." in text
    assert "Second block." in text
