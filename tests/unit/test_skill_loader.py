from pathlib import Path

from uni_agent.skills.loader import SkillLoader


def test_skill_loader_reads_sample_skill() -> None:
    loader = SkillLoader(Path("skills"))
    skills = loader.load_all()
    assert skills
    assert skills[0].name == "general-assistant"

