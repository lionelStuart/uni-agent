from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


_METADATA_HOSTS = frozenset(
    {
        "metadata.google.internal",
        "metadata",
    }
)


def assert_public_http_url(url: str, *, allow_private_networks: bool) -> None:
    """Reject obvious SSRF targets unless allow_private_networks is True."""
    if allow_private_networks:
        return

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("http_fetch only supports http(s) URLs.")

    host = parsed.hostname
    if not host:
        raise ValueError("http_fetch requires a URL with a host.")

    host_lower = host.lower().rstrip(".")
    if host_lower in _METADATA_HOSTS or host_lower.endswith(".internal"):
        raise ValueError("http_fetch blocked host for safety.")

    if host_lower in ("localhost",) or host_lower.endswith(".localhost"):
        raise ValueError("http_fetch blocked host for safety.")

    if host_lower == "169.254.169.254":
        raise ValueError("http_fetch blocked host for safety.")

    bracketed = host
    if bracketed.startswith("[") and bracketed.endswith("]"):
        bracketed = bracketed[1:-1]

    try:
        ip = ipaddress.ip_address(bracketed)
    except ValueError:
        return

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise ValueError("http_fetch blocked address for safety.")

    if ip == ipaddress.ip_address("169.254.169.254"):
        raise ValueError("http_fetch blocked address for safety.")


def strip_url_fragment(url: str) -> str:
    """Remove #fragment if present (keeps validation on netloc)."""
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


def assert_http_fetch_host_allowlist(hostname: str | None, allowed_hosts: frozenset[str]) -> None:
    """If allowlist is non-empty, require hostname to match a rule (exact or suffix)."""
    if not allowed_hosts:
        return
    if not hostname:
        raise ValueError("http_fetch requires a URL with a host.")

    host = hostname.lower().rstrip(".")
    for rule in allowed_hosts:
        if rule.startswith("."):
            suffix = rule[1:].rstrip(".")
            if not suffix:
                continue
            if host == suffix or host.endswith(f".{suffix}"):
                return
        else:
            exact = rule.rstrip(".")
            if host == exact:
                return

    raise ValueError("http_fetch host is not allowed by UNI_AGENT_HTTP_FETCH_ALLOWED_HOSTS.")
