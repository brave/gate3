import asyncio
import logging
import random
import time

import httpx

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 502, 503, 504}
DEFAULT_MAX_RETRIES = 3
DEFAULT_INITIAL_DELAY = 0.5
DEFAULT_MULTIPLIER = 2.0
DEFAULT_MAX_DELAY = 4.0
DEFAULT_JITTER_FACTOR = 0.5
DEFAULT_MAX_TOTAL_TIME = 30.0


class RetryTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_delay: float = DEFAULT_INITIAL_DELAY,
        multiplier: float = DEFAULT_MULTIPLIER,
        max_delay: float = DEFAULT_MAX_DELAY,
        jitter_factor: float = DEFAULT_JITTER_FACTOR,
        max_total_time: float = DEFAULT_MAX_TOTAL_TIME,
    ):
        self._wrapped = transport or httpx.AsyncHTTPTransport()
        self._max_retries = max_retries
        self._initial_delay = initial_delay
        self._multiplier = multiplier
        self._max_delay = max_delay
        self._jitter_factor = jitter_factor
        self._max_total_time = max_total_time

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        delay = self._initial_delay
        start = time.monotonic()

        for attempt in range(self._max_retries + 1):
            response = await self._wrapped.handle_async_request(request)

            if response.status_code not in RETRYABLE_STATUS_CODES:
                return response

            elapsed = time.monotonic() - start
            if attempt == self._max_retries or elapsed >= self._max_total_time:
                return response

            wait = delay
            if response.status_code == 429:
                retry_after = response.headers.get("retry-after")
                if retry_after:
                    try:
                        wait = max(0, min(float(retry_after), self._max_delay))
                    except ValueError:
                        pass

            jitter = random.uniform(0, self._jitter_factor * wait)
            wait += jitter

            remaining = self._max_total_time - elapsed
            if wait >= remaining:
                return response

            logger.warning(
                "Retrying %s (attempt %d/%d, status %d, waiting %.2fs)",
                request.url.host,
                attempt + 1,
                self._max_retries,
                response.status_code,
                wait,
            )

            await response.aclose()
            await asyncio.sleep(wait)

            delay = min(delay * self._multiplier, self._max_delay)

        return response

    async def aclose(self) -> None:
        await self._wrapped.aclose()


def create_http_client(
    *,
    headers: httpx.Headers | dict[str, str] | None = None,
    **kwargs,
) -> httpx.AsyncClient:
    transport = RetryTransport()

    if "transport" in kwargs:
        logger.warning(
            "Ignoring 'transport' provided via kwargs in create_http_client; "
            "using RetryTransport instead."
        )
        kwargs.pop("transport")

    if "headers" in kwargs:
        logger.warning(
            "Ignoring 'headers' provided via kwargs in create_http_client; "
            "use the explicit 'headers' parameter instead."
        )
        kwargs.pop("headers")
    return httpx.AsyncClient(transport=transport, headers=headers, **kwargs)
