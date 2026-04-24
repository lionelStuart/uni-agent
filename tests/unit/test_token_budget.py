from uni_agent.context.token_budget import (
    ContextBlock,
    count_tokens,
    fit_blocks_to_budget,
    render_blocks,
    truncate_to_tokens,
)


def test_count_tokens_counts_cjk_and_ascii() -> None:
    assert count_tokens("hello world") > 0
    assert count_tokens("今天的新闻热点") >= 4


def test_truncate_to_tokens_shrinks_text() -> None:
    text = "one two three four five six seven eight"
    truncated = truncate_to_tokens(text, 4)

    assert truncated
    assert len(truncated) < len(text)


def test_fit_blocks_to_budget_keeps_pinned_block() -> None:
    blocks = [
        ContextBlock(kind="system", text="must keep this constraint", pinned=True, priority=100),
        ContextBlock(kind="noise", text="x " * 400, priority=1),
    ]

    fitted = fit_blocks_to_budget(blocks, max_tokens=12)
    text = render_blocks(fitted)

    assert "must keep this constraint" in text


def test_fit_blocks_to_budget_prefers_higher_priority() -> None:
    blocks = [
        ContextBlock(kind="low", text="low priority context", priority=1),
        ContextBlock(kind="high", text="high priority finding", priority=50),
    ]

    fitted = fit_blocks_to_budget(blocks, max_tokens=count_tokens("high priority finding") + 1)
    text = render_blocks(fitted)

    assert "high priority finding" in text
