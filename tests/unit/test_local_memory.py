import json
from pathlib import Path

from uni_agent.agent.planner import HeuristicPlanner
from uni_agent.observability.client_session import ClientSession, ClientSessionRunEntry
from uni_agent.observability.local_memory import (
    MEMORY_INDEX_FILE,
    MEMORY_L1_SUBDIR,
    collect_memory_hits_for_keywords,
    count_memory_records,
    l0_from_l1,
    persist_incremental_for_client_session,
    persist_new_session_entries,
    search_memory_directory,
)
from uni_agent.tools.builtins import register_builtin_handlers
from uni_agent.tools.registry import ToolRegistry
from uni_agent.sandbox.runner import LocalSandbox


def test_persist_and_search_round_trip(tmp_path: Path) -> None:
    mem = tmp_path / "mem"
    entries = [
        ClientSessionRunEntry(
            run_id="run-a",
            task="hello world",
            status="completed",
            summary="status=completed; task='hello world' | all good",
            conclusion="done",
        )
    ]
    rep = persist_new_session_entries(
        memory_dir=mem, session_id="sess-1", entries=entries, start_index=0
    )
    assert rep.written == 1
    assert rep.new_checkpoint == 1
    assert rep.items[0].action == "created"
    assert rep.items[0].run_id == "run-a"
    assert (mem / MEMORY_INDEX_FILE).is_file()
    assert (mem / MEMORY_L1_SUBDIR).is_dir()
    assert list((mem / MEMORY_L1_SUBDIR).glob("*.json"))
    assert count_memory_records(mem) == 1

    out = search_memory_directory(mem, "hello")
    assert "hello world" in out
    assert "run-a" in out
    assert MEMORY_L1_SUBDIR in out or "l1=" in out

    out_miss = search_memory_directory(mem, "nope_not_in_records")
    assert "No memory records match" in out_miss


def test_incremental_checkpoint_advances(tmp_path: Path) -> None:
    mem = tmp_path / "mem"
    session = ClientSession(
        id="s1",
        created_at="t",
        updated_at="t",
        entries=[
            ClientSessionRunEntry(run_id="r1", task="a", status="completed"),
        ],
        memory_last_extracted_index=0,
    )
    r1 = persist_incremental_for_client_session(memory_dir=mem, session=session)
    assert r1.written == 1
    assert session.memory_last_extracted_index == 1

    r2 = persist_incremental_for_client_session(memory_dir=mem, session=session)
    assert r2.written == 0
    assert session.memory_last_extracted_index == 1


def test_upsert_same_run_id_recomputes_l0(tmp_path: Path) -> None:
    mem = tmp_path / "mem"
    e1 = ClientSessionRunEntry(
        run_id="same-run",
        task="first title alpha",
        status="completed",
        summary="s1",
    )
    persist_new_session_entries(memory_dir=mem, session_id="s", entries=[e1], start_index=0)
    assert count_memory_records(mem) == 1
    assert "alpha" in search_memory_directory(mem, "alpha")

    e2 = ClientSessionRunEntry(
        run_id="same-run",
        task="second title beta only",
        status="completed",
        summary="s2",
    )
    rep = persist_new_session_entries(memory_dir=mem, session_id="s", entries=[e2], start_index=0)
    assert rep.written == 1
    assert rep.items[0].action == "updated"
    assert count_memory_records(mem) == 1
    assert "beta" in search_memory_directory(mem, "beta")
    assert "No memory records match" in search_memory_directory(mem, "alpha")


def test_search_indexes_l0_not_deep_l1_only(tmp_path: Path) -> None:
    """Keyword buried only in a long output_preview tail must not match (not in L0)."""
    mem = tmp_path / "mem"
    secret = "SECRET_DEEP_TOKEN_XYZ"
    long_prev = ("a" * 400) + secret
    e = ClientSessionRunEntry(
        run_id="r1",
        task="short",
        status="completed",
        summary="brief",
        output_preview=long_prev,
    )
    persist_new_session_entries(memory_dir=mem, session_id="s", entries=[e], start_index=0)
    l0 = l0_from_l1(
        {
            "task": e.task,
            "status": e.status,
            "summary": e.summary,
            "output_preview": e.output_preview,
            "run_id": e.run_id,
        }
    )
    assert secret not in l0
    assert "No memory records match" in search_memory_directory(mem, secret)
    assert "brief" in search_memory_directory(mem, "brief")


def test_memory_search_tool_uses_passed_dir(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    memory_dir = tmp_path / "custom_mem"
    workspace.mkdir()
    rec = {
        "schema_version": 1,
        "task": "banana project",
        "session_id": "x",
        "run_id": "y",
    }
    memory_dir.mkdir()
    (memory_dir / "a.json").write_text(json.dumps(rec), encoding="utf-8")

    reg = ToolRegistry()
    reg.register_builtin_tools()
    register_builtin_handlers(
        reg,
        workspace,
        LocalSandbox(workspace),
        memory_dir=memory_dir,
    )
    text = reg.execute("memory_search", {"query": "banana"})
    assert "banana project" in text


def test_collect_memory_hits_for_keywords_union_match(tmp_path: Path) -> None:
    mem = tmp_path / "mem"
    e = ClientSessionRunEntry(
        run_id="r99",
        task="alpha beta topic",
        status="completed",
        summary="gamma note",
    )
    persist_new_session_entries(memory_dir=mem, session_id="s", entries=[e], start_index=0)
    hits = collect_memory_hits_for_keywords(mem, ["gamma", "nope"], max_entries=5)
    assert len(hits) == 1
    assert hits[0]["l1"]["run_id"] == "r99"
    hits2 = collect_memory_hits_for_keywords(mem, ["nope_only"], max_entries=5)
    assert hits2 == []


def test_heuristic_planner_memory_search_phrases() -> None:
    reg = ToolRegistry()
    reg.register_builtin_tools()
    tools = reg.list_tools()
    h = HeuristicPlanner()
    p1 = h.create_plan("memory search Qwen gateway", [], tools)
    assert len(p1) == 1 and p1[0].tool == "memory_search"
    assert p1[0].arguments["query"] == "Qwen gateway"
    p2 = h.create_plan("搜索记忆：上次说的端口", [], tools)
    assert len(p2) == 1 and p2[0].tool == "memory_search"
    assert "端口" in p2[0].arguments["query"]
    p3 = h.create_plan("我是谁", [], tools)
    assert len(p3) == 1 and p3[0].tool == "memory_search"
    assert p3[0].arguments["query"] == "我是谁"


def test_pydantic_planner_identity_routes_to_memory_before_llm() -> None:
    from unittest.mock import MagicMock

    from uni_agent.agent.pydantic_planner import PydanticAIPlanner

    reg = ToolRegistry()
    reg.register_builtin_tools()
    tools = reg.list_tools()
    prov = MagicMock()
    prov.is_available.return_value = True
    prov.model_id = "test-model"
    prov.openai_base_url = None
    prov.openai_api_key = None
    planner = PydanticAIPlanner(provider=prov, defer_model_check=True, retries=0)
    llm_spy = MagicMock(side_effect=AssertionError("planner LLM must not run for recall-self tasks"))
    planner._agent.run_sync = llm_spy  # type: ignore[method-assign]
    steps = planner.create_plan("我是谁", [], tools)
    assert len(steps) == 1 and steps[0].tool == "memory_search"
    llm_spy.assert_not_called()
