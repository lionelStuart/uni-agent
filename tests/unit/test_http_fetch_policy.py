import pytest

from uni_agent.tools.http_fetch_policy import assert_public_http_url


def test_public_https_url_allowed() -> None:
    assert_public_http_url("https://example.com/path", allow_private_networks=False)


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/",
        "http://localhost/",
        "http://192.168.1.1/",
        "http://10.0.0.1/",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",
    ],
)
def test_private_and_loopback_blocked(url: str) -> None:
    with pytest.raises(ValueError):
        assert_public_http_url(url, allow_private_networks=False)


def test_private_allowed_when_configured() -> None:
    assert_public_http_url("http://127.0.0.1/", allow_private_networks=True)
