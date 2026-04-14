from uni_agent.agent.memory_llm_search import _normalize_keywords


def test_normalize_keywords_prepends_user_query_for_l0_match() -> None:
    """L0 lines usually contain the task text; English-only model keywords must not be the only terms."""
    kws = _normalize_keywords(["identity", "programming assistant"], "我是谁")
    assert kws[0] == "我是谁"
    assert "我是谁" in kws