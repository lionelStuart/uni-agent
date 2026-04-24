"""Contract: `AgentConfig.to_settings()` maps fields consistently (Round 6 snapshot)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from uni_agent.sdk.config import AgentConfig

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sdk" / "to_settings_non_path.json"


@pytest.fixture
def _snapshot_non_path() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def test_to_settings_non_path_fields_match_snapshot(tmp_path: Path, _snapshot_non_path: dict) -> None:
    (tmp_path / "skills").mkdir()
    snap = _snapshot_non_path
    cfg = AgentConfig(
        name="SnapName",
        description="SnapDesc",
        workspace=tmp_path,
        skills_dir=tmp_path / "skills",
        storage_namespace="snap-ns",
        model_name=snap["model_name"],
        context_window_tokens=snap["context_window_tokens"],
        openai_base_url=snap["openai_base_url"],
        openai_api_key=snap["openai_api_key"],
        ca_bundle=snap["ca_bundle"],
        skip_tls_verify=snap["skip_tls_verify"],
        planner_backend=snap["planner_backend"],
        plan_goal_check_enabled=snap["plan_goal_check_enabled"],
        global_system_prompt=snap["global_system_prompt"],
        planner_instructions=snap["planner_instructions"],
        conclusion_system_prompt=snap["conclusion_system_prompt"],
        run_conclusion_llm=snap["run_conclusion_llm"],
    )
    s = cfg.to_settings()
    dumped = s.model_dump(mode="json")
    expected_non_path = {k: v for k, v in snap.items() if k != "ca_bundle"}
    for k, v in expected_non_path.items():
        assert dumped.get(k) == v, f"field {k!r}: expected {v!r}, got {dumped.get(k)!r}"
    assert s.ca_bundle == (tmp_path / snap["ca_bundle"]).resolve()


def test_to_settings_paths_for_storage_namespace(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    cfg = AgentConfig(
        name="a",
        workspace=tmp_path,
        skills_dir=tmp_path / "skills",
        storage_namespace="  ns2  ",
    )
    s = cfg.to_settings()
    assert s.task_log_dir == tmp_path / ".uni-agent" / "runs" / "ns2"
    assert s.memory_dir == (tmp_path / ".uni-agent" / "memory" / "ns2").resolve()
    assert s.workspace == tmp_path.resolve()
    assert s.skills_dir == (tmp_path / "skills").resolve()


def test_to_settings_resolves_relative_ca_bundle_under_workspace(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    cfg = AgentConfig(
        name="a",
        workspace=tmp_path,
        skills_dir=tmp_path / "skills",
        ca_bundle=Path("certs/corp-root.pem"),
    )

    s = cfg.to_settings()

    assert s.ca_bundle == (tmp_path / "certs" / "corp-root.pem").resolve()


def test_to_settings_propagates_skip_tls_verify(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    cfg = AgentConfig(
        name="a",
        workspace=tmp_path,
        skills_dir=tmp_path / "skills",
        skip_tls_verify=True,
    )

    s = cfg.to_settings()

    assert s.skip_tls_verify is True


def test_to_settings_can_disable_skip_tls_verify_explicitly(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    cfg = AgentConfig(
        name="a",
        workspace=tmp_path,
        skills_dir=tmp_path / "skills",
        skip_tls_verify=False,
    )

    s = cfg.to_settings()

    assert s.skip_tls_verify is False


def test_to_settings_can_disable_goal_check_explicitly(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    cfg = AgentConfig(
        name="a",
        workspace=tmp_path,
        skills_dir=tmp_path / "skills",
        plan_goal_check_enabled=False,
    )

    s = cfg.to_settings()

    assert s.plan_goal_check_enabled is False
