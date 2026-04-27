from __future__ import annotations

from types import SimpleNamespace

from uni_agent.bootstrap import build_orchestrator
from uni_agent.config.settings import Settings


def test_build_orchestrator_composes_user_and_langfuse_and_keeps_delegate_parent_stream(tmp_path, monkeypatch) -> None:
    calls = {
        "compose_inputs": None,
        "delegate_parent_stream_event": None,
        "orchestrator_stream_event": None,
        "lf_calls": [],
        "user_calls": [],
        "sqlite_calls": [],
    }
    ws = tmp_path / "ws"
    skills = tmp_path / "skills"
    runs = tmp_path / "runs"
    ws.mkdir()
    skills.mkdir()
    runs.mkdir()

    settings = Settings(workspace=ws, skills_dir=skills, task_log_dir=runs, model_name="openai:gpt-4.1-mini")

    def user_stream(event):
        calls["user_calls"].append(event)

    def langfuse_stream(event):
        calls["lf_calls"].append(event)

    def sqlite_stream(event):
        calls["sqlite_calls"].append(event)

    def fake_langfuse_builder(_cfg: Settings):
        return langfuse_stream

    def fake_sqlite_builder(_store, *, session_id, source, workspace):
        assert session_id is None
        assert source == "cli"
        assert workspace == str(ws.resolve())
        return sqlite_stream

    def fake_compose(callbacks):
        calls["compose_inputs"] = list(callbacks)

        def merged(event):
            for cb in callbacks:
                if cb is not None:
                    cb(event)

        return merged

    def fake_register_builtin_handlers(_tool_registry, _workspace, _sandbox, *, delegate_parent_stream_event, **_kwargs):
        calls["delegate_parent_stream_event"] = delegate_parent_stream_event

    def fake_orchestrator(*args, **kwargs):
        calls["orchestrator_stream_event"] = kwargs.get("stream_event")
        return "orch"

    # Keep bootstrap path simple and avoid real tool/provider initialization.
    monkeypatch.setattr("uni_agent.bootstrap.build_langfuse_stream_handler", fake_langfuse_builder)
    monkeypatch.setattr("uni_agent.bootstrap.build_webhook_stream_handler", lambda **_kwargs: None)
    monkeypatch.setattr("uni_agent.bootstrap.safe_create_sqlite_store", lambda _path: object())
    monkeypatch.setattr("uni_agent.bootstrap.build_sqlite_stream_handler", fake_sqlite_builder)
    monkeypatch.setattr("uni_agent.bootstrap.compose_stream_callbacks", fake_compose)
    monkeypatch.setattr("uni_agent.bootstrap.register_builtin_handlers", fake_register_builtin_handlers)
    monkeypatch.setattr("uni_agent.bootstrap.Orchestrator", fake_orchestrator)
    monkeypatch.setattr(
        "uni_agent.bootstrap.SkillLoader",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr("uni_agent.bootstrap.TaskStore", lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(
        "uni_agent.bootstrap.EnvLLMProvider",
        lambda *args, **kwargs: SimpleNamespace(is_available=lambda: False),
    )

    assert build_orchestrator(stream_event=user_stream, settings=settings) == "orch"
    assert calls["compose_inputs"] == [user_stream, langfuse_stream, None, sqlite_stream]
    assert calls["delegate_parent_stream_event"] is user_stream
    assert callable(calls["orchestrator_stream_event"])

    calls["orchestrator_stream_event"]({"type": "run_begin", "run_id": "r-1"})
    assert calls["user_calls"] == [{"type": "run_begin", "run_id": "r-1"}]
    assert calls["lf_calls"] == [{"type": "run_begin", "run_id": "r-1"}]
    assert calls["sqlite_calls"] == [{"type": "run_begin", "run_id": "r-1"}]


def test_build_langfuse_stream_handler_returns_none_without_dependency(tmp_path, monkeypatch) -> None:
    from uni_agent.observability.langfuse import build_langfuse_stream_handler

    monkeypatch.setattr(
        "uni_agent.observability.langfuse._import_langfuse",
        lambda: None,
    )

    settings = Settings(
        workspace=tmp_path,
        skills_dir=tmp_path / "skills",
        task_log_dir=tmp_path / "runs",
        observability_langfuse_enabled=True,
        observability_langfuse_public_key="pk",
        observability_langfuse_secret_key="sk",
        model_name="x",
    )
    # build_langfuse_stream_handler reads host/public/secret from settings only; workspace is irrelevant
    assert build_langfuse_stream_handler(settings) is None
