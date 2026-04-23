"""`AgentRegistry` contract: one client per id, register/get, missing get errors (Round 6)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from uni_agent.sdk import AgentConfig, AgentRegistry, create_client


def test_registry_get_missing_raises_keyerror() -> None:
    reg = AgentRegistry()
    with pytest.raises(KeyError):
        reg.get("nope")


def test_register_get_len_contains(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    cfg = AgentConfig(
        name="a",
        workspace=tmp_path,
        skills_dir=tmp_path / "skills",
    )
    with patch("uni_agent.sdk.client.build_orchestrator", return_value=MagicMock()):
        c = create_client(cfg)
    reg = AgentRegistry()
    assert len(reg) == 0
    reg.register("x", c)
    assert "x" in reg
    assert len(reg) == 1
    assert reg.get("x") is c


def test_different_ids_distinct_clients(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    cfg = AgentConfig(
        name="a",
        workspace=tmp_path,
        skills_dir=tmp_path / "skills",
    )
    m1, m2 = MagicMock(), MagicMock()
    with patch("uni_agent.sdk.client.build_orchestrator", side_effect=[m1, m2]):
        reg = AgentRegistry()
        a = reg.get_or_create("id-a", cfg)
        b = reg.get_or_create("id-b", cfg)
    assert a is not b
    assert a.orchestrator is m1
    assert b.orchestrator is m2


def test_get_or_create_ignores_later_config_for_same_id(tmp_path: Path) -> None:
    """First successful `get_or_create` wins; later calls do not rebuild."""
    (tmp_path / "skills").mkdir()
    base = dict(workspace=tmp_path, skills_dir=tmp_path / "skills")
    cfg1 = AgentConfig(name="one", **base)
    cfg2 = AgentConfig(name="two", **base)
    m1, m2 = MagicMock(), MagicMock()
    with patch("uni_agent.sdk.client.build_orchestrator", side_effect=[m1, m2]):
        reg = AgentRegistry()
        c1 = reg.get_or_create("same", cfg1)
        c2 = reg.get_or_create("same", cfg2)
    assert c1 is c2
    assert c1.config.name == "one"
    assert c1.orchestrator is m1
