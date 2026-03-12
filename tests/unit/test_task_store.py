from pathlib import Path

from uni_agent.observability.task_store import TaskStore
from uni_agent.shared.models import TaskResult, TaskStatus


def test_task_store_round_trip(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "runs")
    result = TaskResult(
        run_id="run-123",
        task="demo",
        status=TaskStatus.COMPLETED,
        output="ok",
    )

    store.save(result)
    loaded = store.load("run-123")

    assert loaded.run_id == "run-123"
    assert loaded.result.output == "ok"
