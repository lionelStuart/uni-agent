import pytest

from uni_agent.tools.http_fetch_policy import assert_http_fetch_host_allowlist


def test_allowlist_blocks_unknown_host() -> None:
    allowed = frozenset({"example.com"})
    with pytest.raises(ValueError):
        assert_http_fetch_host_allowlist("evil.com", allowed)


def test_allowlist_allows_exact_host() -> None:
    assert_http_fetch_host_allowlist("example.com", frozenset({"example.com"})) is None


def test_allowlist_supports_suffix_rule() -> None:
    allowed = frozenset({".github.com"})
    assert_http_fetch_host_allowlist("api.github.com", allowed) is None
