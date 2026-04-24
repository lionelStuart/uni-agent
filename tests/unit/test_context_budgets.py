from uni_agent.context.budgeting import derive_context_budgets


def test_derive_context_budgets_uses_context_window() -> None:
    small = derive_context_budgets(32_000)
    large = derive_context_budgets(256_000)

    assert large.context_window_tokens == 256_000
    assert small.context_window_tokens == 32_000
    assert large.session_context_max_tokens > small.session_context_max_tokens
    assert large.prior_context_max_tokens > small.prior_context_max_tokens
    assert large.conclusion_max_tokens > small.conclusion_max_tokens
