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


def test_heuristic_delegate_task_when_user_explicit() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    planner = HeuristicPlanner()

    plan = planner.create_plan("请用 delegate_task 只读 README.md 前几行", [], registry.list_tools())

    assert len(plan) == 1
    assert plan[0].tool == "delegate_task"
    assert "README" in plan[0].arguments["task"]


def test_heuristic_prefers_du_for_largest_folder_question() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    planner = HeuristicPlanner()

    plan = planner.create_plan("找到当前最大文件夹", [], registry.list_tools())

    shell = [step for step in plan if step.tool == "shell_exec"]
    assert shell
    assert shell[0].arguments["command"] == ["du", "-h", "-d", "1", "."]
    assert all(step.tool != "search_workspace" for step in plan)
