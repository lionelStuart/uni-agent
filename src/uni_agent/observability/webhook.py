from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from uni_agent.observability.logging import get_logger

StreamEventCallback = Any


def build_webhook_stream_handler(
    *,
    webhook_url: str | None,
    timeout_seconds: float,
    headers: dict[str, str] | None = None,
) -> StreamEventCallback | None:
    if not webhook_url:
        return None
    hdrs = {"content-type": "application/json"}
    if headers:
        hdrs.update(headers)
    log = get_logger(__name__)

    def _send(event: dict[str, Any]) -> None:
        body = json.dumps(event, ensure_ascii=False).encode("utf-8")
        req = Request(webhook_url, data=body, headers=hdrs, method="POST")
        try:
            with urlopen(req, timeout=timeout_seconds) as resp:
                if resp.status >= 400:
                    log.warning("observability_webhook_http_error", status=resp.status, url=webhook_url)
        except URLError:
            log.exception("observability_webhook_failed", url=webhook_url)
        except Exception:
            log.exception("observability_webhook_failed", url=webhook_url)

    return _send
