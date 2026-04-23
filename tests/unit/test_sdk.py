from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from uni_agent.sdk import AgentConfig, AgentClient, AgentRegistry, create_client


def test_agent_config_to_settings_default_persona(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    cfg = AgentConfig(
        name="CodeBot",
        description="Help with the repo.",
        workspace=tmp_path,
        skills_dir=tmp_path / "skills",
    )
    s = cfg.to_settings()
    assert s.workspace == tmp_path.resolve()
    assert s.skills_dir == (tmp_path / "skills").resolve()
    g = s.global_system_prompt or ""
    assert "CodeBot" in g
    assert "Help with the repo." in g


def test_agent_config_explicit_global_overrides_name(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    cfg = AgentConfig(
        name="IgnoredName",
        workspace=tmp_path,
        skills_dir=tmp_path / "skills",
        global_system_prompt="Custom prefix only.",
    )
    s = cfg.to_settings()
    assert s.global_system_prompt == "Custom prefix only."


def test_storage_namespace_separates_task_and_memory(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    cfg = AgentConfig(
        name="a",
        workspace=tmp_path,
        skills_dir=tmp_path / "skills",
        storage_namespace="team-a",
    )
    s = cfg.to_settings()
    assert s.task_log_dir == tmp_path / ".uni-agent" / "runs" / "team-a"
    assert s.memory_dir == (tmp_path / ".uni-agent" / "memory" / "team-a").resolve()


def test_create_client_uses_build_orchestrator_settings(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    mock_orch = MagicMock()
    cfg = AgentConfig(
        name="t",
        workspace=tmp_path,
        skills_dir=tmp_path / "skills",
    )
    with patch("uni_agent.sdk.client.build_orchestrator", return_value=mock_orch) as bo:
        c = create_client(cfg)
    bo.assert_called_once()
    _args, kwd = bo.call_args
    assert "settings" in kwd
    st = kwd["settings"]
    assert st.skills_dir == (tmp_path / "skills").resolve()
    assert c.orchestrator is mock_orch


def test_registry_get_or_create_returns_same_client(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    mock_orch = MagicMock()
    cfg = AgentConfig(
        name="r",
        workspace=tmp_path,
        skills_dir=tmp_path / "skills",
    )
    with patch("uni_agent.sdk.client.build_orchestrator", return_value=mock_orch):
        reg = AgentRegistry()
        c1 = reg.get_or_create("id1", cfg)
        c2 = reg.get_or_create("id1", cfg)
    assert c1 is c2
    with patch("uni_agent.sdk.client.build_orchestrator", return_value=MagicMock()) as bo2:
        c3 = reg.get_or_create("id1", cfg)
    bo2.assert_not_called()
    assert c3 is c1


def test_client_run_delegates(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    mock_orch = MagicMock()
    mock_orch.run.return_value = MagicMock()
    cfg = AgentConfig(
        name="c",
        workspace=tmp_path,
        skills_dir=tmp_path / "skills",
    )
    c = AgentClient(cfg, orchestrator=mock_orch)
    c.run("hello")
    mock_orch.run.assert_called_once_with("hello", plan_override=None, session_context=None)
