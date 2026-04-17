from uni_agent.agent.planner import HeuristicPlanner
from uni_agent.shared.models import SkillSpec
from uni_agent.tools.registry import ToolRegistry


def test_planner_ignores_skill_allowed_tools_for_palette() -> None:
    """Skills no longer restrict which built-in tools the planner may use."""
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
    plan = planner.create_plan(
        'shared search for refs then write the file out.txt with content "hi"', skills, tools
    )

    assert any(step.tool == "file_write" for step in plan)
    assert any(step.tool == "search_workspace" for step in plan)
