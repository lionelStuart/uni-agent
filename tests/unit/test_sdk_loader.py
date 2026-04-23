"""Manifest loader for multiple AgentConfig entries."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from uni_agent.sdk import load_agent_configs_from_file, load_agent_registry_from_file


def test_load_agent_configs_yaml(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "skills").mkdir()
    manifest = tmp_path / "agents.yaml"
    manifest.write_text(
        """
version: 1
agents:
  - id: alpha
    name: Alpha
    workspace: ws
    skills_dir: skills
    storage_namespace: ns-a
    planner_backend: heuristic
  - id: beta
    name: Beta
    workspace: ws
    skills_dir: skills
    planner_backend: heuristic
""",
        encoding="utf-8",
    )
    cfgs = load_agent_configs_from_file(manifest)
    assert set(cfgs) == {"alpha", "beta"}
    assert cfgs["alpha"].name == "Alpha"
    assert cfgs["alpha"].workspace == ws.resolve()
    assert cfgs["alpha"].skills_dir == (ws / "skills").resolve()


def test_load_agent_configs_json(tmp_path: Path) -> None:
    ws = tmp_path / "w"
    ws.mkdir()
    (ws / "sk").mkdir()
    manifest = tmp_path / "m.json"
    manifest.write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "id": "j1",
                        "workspace": "w",
                        "skills_dir": "sk",
                        "planner_backend": "heuristic",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cfgs = load_agent_configs_from_file(manifest)
    assert list(cfgs.keys()) == ["j1"]


def test_duplicate_id_errors(tmp_path: Path) -> None:
    m = tmp_path / "d.yaml"
    m.write_text(
        """
agents:
  - id: x
    workspace: "."
    skills_dir: s
  - id: x
    workspace: "."
    skills_dir: s
""",
        encoding="utf-8",
    )
    (tmp_path / "s").mkdir()
    with pytest.raises(ValueError, match="duplicate"):
        load_agent_configs_from_file(m)


def test_load_registry_registers_clients(tmp_path: Path) -> None:
    ws = tmp_path / "ww"
    ws.mkdir()
    (ws / "skills").mkdir()
    man = tmp_path / "a.yaml"
    man.write_text(
        """
agents:
  - id: r1
    workspace: ww
    skills_dir: skills
    planner_backend: heuristic
""",
        encoding="utf-8",
    )
    with patch("uni_agent.sdk.loader.create_client", return_value=MagicMock()) as cc:
        reg = load_agent_registry_from_file(man, on_event=None)
    assert "r1" in reg  # type: ignore[operator]
    assert cc.call_count == 1
