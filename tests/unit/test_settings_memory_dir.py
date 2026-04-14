from pathlib import Path

from uni_agent.config.settings import Settings


def test_memory_dir_defaults_under_workspace(monkeypatch, tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("UNI_AGENT_WORKSPACE", str(proj))
    monkeypatch.delenv("UNI_AGENT_MEMORY_DIR", raising=False)
    s = Settings()
    assert s.memory_dir == (proj / ".uni-agent" / "memory").resolve()


def test_memory_dir_relative_is_under_workspace(monkeypatch, tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("UNI_AGENT_WORKSPACE", str(proj))
    monkeypatch.setenv("UNI_AGENT_MEMORY_DIR", "custom_mem")
    s = Settings()
    assert s.memory_dir == (proj / "custom_mem").resolve()
