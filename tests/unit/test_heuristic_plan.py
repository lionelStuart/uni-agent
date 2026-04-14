from uni_agent.agent.planner import HeuristicPlanner
from uni_agent.tools.registry import ToolRegistry


def test_heuristic_plan_includes_file_write() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    planner = HeuristicPlanner()

    plan = planner.create_plan('write the file notes.txt with content "hello"', [], registry.list_tools())

    write_steps = [step for step in plan if step.tool == "file_write"]
    assert write_steps
    assert write_steps[0].arguments["path"] == "notes.txt"
    assert write_steps[0].arguments["content"] == "hello"


def test_heuristic_skips_read_when_write_targets_same_path() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    planner = HeuristicPlanner()

    plan = planner.create_plan('write the file README.md with content "x"', [], registry.list_tools())

    assert any(step.tool == "file_write" for step in plan)
    assert all(step.tool != "file_read" for step in plan)


def test_heuristic_adds_http_fetch_for_urls() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    planner = HeuristicPlanner()

    plan = planner.create_plan("download https://example.com/path", [], registry.list_tools())

    fetch_steps = [step for step in plan if step.tool == "http_fetch"]
    assert fetch_steps
    assert fetch_steps[0].arguments["url"].startswith("https://example.com/path")
