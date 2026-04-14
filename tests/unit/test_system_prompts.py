from uni_agent.agent.system_prompts import (
    DEFAULT_PLANNER_SYSTEM_PROMPT,
    effective_conclusion_instructions,
    effective_planner_instructions,
)


def test_effective_planner_uses_default_without_overrides() -> None:
    text = effective_planner_instructions(override=None, global_prefix=None)
    assert text == DEFAULT_PLANNER_SYSTEM_PROMPT


def test_effective_planner_override_replaces_default() -> None:
    text = effective_planner_instructions(override="CUSTOM PLANNER", global_prefix=None)
    assert text == "CUSTOM PLANNER"


def test_global_prefix_prepended() -> None:
    text = effective_planner_instructions(override="BASE", global_prefix="PREFIX")
    assert text == "PREFIX\n\nBASE"


def test_effective_conclusion_strips_empty_global() -> None:
    text = effective_conclusion_instructions(override="C", global_prefix="   ")
    assert text == "C"
