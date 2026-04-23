"""Load multiple :class:`AgentConfig` entries from a JSON or YAML manifest (Round 3)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from uni_agent.agent.orchestrator import StreamEventCallback
from uni_agent.sdk.client import create_client
from uni_agent.sdk.config import AgentConfig, PlannerBackend
from uni_agent.sdk.registry import AgentRegistry

_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")

_MANIFEST_EXTS = {".json", ".yaml", ".yml"}


def _resolve_path(base: Path, p: str | Path) -> Path:
    x = Path(p)
    return x.resolve() if x.is_absolute() else (base / x).resolve()


def _coerce_planner(v: object) -> PlannerBackend:
    if v is None or v == "":
        return "auto"
    s = str(v).strip()
    if s in ("auto", "heuristic", "pydantic_ai"):
        return s  # type: ignore[return-value]
    raise ValueError(f"invalid planner_backend: {v!r}")


def _one_config(entry: dict[str, Any], base_dir: Path) -> tuple[str, AgentConfig]:
    aid = entry.get("id")
    if not isinstance(aid, str) or not aid.strip():
        raise ValueError("each agent entry must have a non-empty string 'id'")
    aid = aid.strip()
    if not _ID_RE.match(aid):
        raise ValueError(f"invalid agent id (use letters, digits, ._- only): {aid!r}")

    ws = entry.get("workspace")
    if ws is None or str(ws).strip() == "":
        raise ValueError(f"agent {aid!r} missing 'workspace'")
    workspace = _resolve_path(base_dir, str(ws).strip())

    sk = entry.get("skills_dir")
    if sk is None or str(sk).strip() == "":
        raise ValueError(f"agent {aid!r} missing 'skills_dir'")
    skills_path = Path(str(sk).strip())
    if not skills_path.is_absolute():
        skills_path = (workspace / skills_path).resolve()
    else:
        skills_path = skills_path.resolve()

    st_ns = entry.get("storage_namespace")
    storage = str(st_ns).strip() if st_ns is not None else None
    if storage == "":
        storage = None

    cfg = AgentConfig(
        name=str(entry.get("name") or aid).strip() or aid,
        description=str(entry.get("description", "")).strip(),
        workspace=workspace,
        skills_dir=skills_path,
        storage_namespace=storage,
        model_name=entry.get("model_name") if entry.get("model_name") is not None else None,
        openai_base_url=entry.get("openai_base_url") if entry.get("openai_base_url") is not None else None,
        openai_api_key=entry.get("openai_api_key") if entry.get("openai_api_key") is not None else None,
        planner_backend=_coerce_planner(entry.get("planner_backend")),
        global_system_prompt=entry.get("global_system_prompt") if entry.get("global_system_prompt") is not None else None,
        planner_instructions=entry.get("planner_instructions") if entry.get("planner_instructions") is not None else None,
        conclusion_system_prompt=entry.get("conclusion_system_prompt")
        if entry.get("conclusion_system_prompt") is not None
        else None,
        run_conclusion_llm=entry.get("run_conclusion_llm") if entry.get("run_conclusion_llm") is not None else None,
    )
    return aid, cfg


def load_agent_configs_from_file(path: Path | str) -> dict[str, AgentConfig]:
    """Load a map ``agent_id -> AgentConfig`` from a manifest file.

    Supported: ``.json`` / ``.yaml`` / ``.yml``. Top level must be a **mapping** with key
    ``agents`` (a list of per-agent objects). **Relative** ``workspace`` in each entry
    is resolved from the **manifest file's directory**; **relative** ``skills_dir`` is
    resolved under that agent's ``workspace`` (or absolute as given).

    Example path layout is in ``examples/agents.example.yaml``.

    :raises FileNotFoundError: if the file does not exist
    :raises ValueError: on schema issues or duplicate ``id``
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    if path.suffix.lower() not in _MANIFEST_EXTS:
        raise ValueError(f"unsupported manifest extension: {path.suffix!r} (use .json, .yaml, or .yml)")

    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data: Any = json.loads(text)
    else:
        data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError("manifest root must be a JSON/YAML object")

    agents = data.get("agents")
    if not isinstance(agents, list) or not agents:
        raise ValueError("manifest must contain a non-empty 'agents' list")

    base_dir = path.parent.resolve()
    out: dict[str, AgentConfig] = {}
    for item in agents:
        if not isinstance(item, dict):
            raise TypeError("each 'agents' item must be a mapping")
        aid, cfg = _one_config(item, base_dir)
        if aid in out:
            raise ValueError(f"duplicate agent id: {aid!r}")
        out[aid] = cfg
    return out


def load_agent_registry_from_file(
    path: Path | str,
    *,
    on_event: StreamEventCallback | None = None,
) -> AgentRegistry:
    """Build an :class:`AgentRegistry` with one :class:`AgentClient` per manifest entry (same ``on_event`` for all)."""
    reg = AgentRegistry()
    for aid, cfg in load_agent_configs_from_file(path).items():
        reg.register(aid, create_client(cfg, on_event=on_event))
    return reg
