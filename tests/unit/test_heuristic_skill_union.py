from uni_agent.agent.planner import HeuristicPlanner
from uni_agent.shared.models import SkillSpec
from uni_agent.tools.registry import ToolRegistry


def test_union_allowed_tools_skips_disallowed_file_write() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    tools = registry.list_tools()
    skills = [
        SkillSpec(
            name="search-skill",
            version="1",
            description="search",
            triggers=["shared"],
            allowed_tools=["search_workspace"],
            path="/tmp/search-skill",
        ),
        SkillSpec(
            name="shell-skill",
            version="1",
            description="shell",
            triggers=["shared"],
            allowed_tools=["shell_exec"],
            path="/tmp/shell-skill",
        ),
    ]

    planner = HeuristicPlanner()
    plan = planner.create_plan('shared write the file out.txt with content "hi"', skills, tools)

    assert all(step.tool != "file_write" for step in plan)
    assert all(step.tool != "file_read" for step in plan)
    assert any(step.tool == "search_workspace" for step in plan)
