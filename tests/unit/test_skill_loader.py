from pathlib import Path

from uni_agent.skills.loader import SkillLoader


def test_skill_loader_reads_sample_skill() -> None:
    loader = SkillLoader(Path("skills"), Path(".").resolve())
    skills = loader.load_all()
    assert skills
    by_name = {s.name: s for s in skills}
    assert "general-assistant" in by_name
    ga = by_name["general-assistant"]
    assert ga.skill_load_format == "yaml_manifest"
    assert "General Assistant" in ga.instruction_text
    assert "code-runner" in by_name
    assert by_name["code-runner"].skill_load_format == "skill_md"
    assert "web-search" in by_name
    web = by_name["web-search"]
    assert web.skill_load_format == "skill_md"
    assert "Prefer `http_fetch`" in web.instruction_text
