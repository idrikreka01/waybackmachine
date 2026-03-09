import logging
import time

import httpx

from waybackmachine.config import (
    COOLDOWN_BACKOFF_SECONDS,
    COOLDOWN_EXTRA_ATTEMPTS,
    REQUEST_DELAY,
    REQUEST_TIMEOUT,
    RETRY_ATTEMPTS,
    RETRY_BACKOFF_BASE,
    RETRYABLE_STATUSES,
)

LOG = logging.getLogger(__name__)


def get_with_retry(client: httpx.Client, url: str) -> httpx.Response:
    if REQUEST_DELAY > 0:
        time.sleep(REQUEST_DELAY)
    last_exc: Exception | None = None
    total_attempts = RETRY_ATTEMPTS + COOLDOWN_EXTRA_ATTEMPTS
    for attempt in range(total_attempts):
        try:
            resp = client.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code in RETRYABLE_STATUSES:
                last_exc = httpx.HTTPStatusError(
                    f"Server returned {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
                if attempt < total_attempts - 1:
                    if attempt < RETRY_ATTEMPTS - 1:
                        delay = RETRY_BACKOFF_BASE**attempt
                        reason = "Retryable status, backing off"
                    else:
                        delay = COOLDOWN_BACKOFF_SECONDS
                        reason = "Retryable status, long cooldown before retry"
                    LOG.warning(
                        reason,
                        extra={
                            "url": url,
                            "status": resp.status_code,
                            "attempt": attempt + 1,
                            "delay_s": delay,
                        },
                    )
                    time.sleep(delay)
                else:
                    raise last_exc
                continue
            return resp
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            last_exc = e
            if attempt < total_attempts - 1:
                if attempt < RETRY_ATTEMPTS - 1:
                    delay = RETRY_BACKOFF_BASE**attempt
                    reason = "Request failed, backing off"
                else:
                    delay = COOLDOWN_BACKOFF_SECONDS
                    reason = "Request failed, long cooldown before retry"
                LOG.warning(
                    reason,
                    extra={
                        "url": url,
                        "error": str(e),
                        "attempt": attempt + 1,
                        "delay_s": delay,
                    },
                )
                time.sleep(delay)
            else:
                raise
    if last_exc:
        raise last_exc
    raise RuntimeError("get_with_retry exhausted retries")
