from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.http import RetryTransport, create_http_client


class MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, responses: list[httpx.Response]):
        self.responses = list(responses)
        self.attempt = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = self.responses[min(self.attempt, len(self.responses) - 1)]
        self.attempt += 1
        return response


def _make_response(status_code: int, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status_code=status_code, headers=headers or {})


def _make_retry_transport(mock, **kwargs):
    return RetryTransport(transport=mock, **kwargs)


@pytest.mark.asyncio
async def test_no_retry_on_success():
    mock = MockTransport([_make_response(200)])
    transport = _make_retry_transport(mock)

    request = httpx.Request("GET", "https://example.com")
    response = await transport.handle_async_request(request)

    assert response.status_code == 200
    assert mock.attempt == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [429, 502, 503, 504])
async def test_retries_then_succeeds(status_code):
    mock = MockTransport([_make_response(status_code), _make_response(200)])
    transport = _make_retry_transport(mock, initial_delay=0.0, jitter_factor=0.0)

    request = httpx.Request("GET", "https://example.com")
    response = await transport.handle_async_request(request)

    assert response.status_code == 200
    assert mock.attempt == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 404, 500])
async def test_no_retry_on_non_retryable(status_code):
    mock = MockTransport([_make_response(status_code)])
    transport = _make_retry_transport(mock)

    request = httpx.Request("GET", "https://example.com")
    response = await transport.handle_async_request(request)

    assert response.status_code == status_code
    assert mock.attempt == 1


@pytest.mark.asyncio
async def test_returns_last_response_when_retries_exhausted():
    mock = MockTransport(
        [_make_response(503), _make_response(503), _make_response(503)]
    )
    transport = _make_retry_transport(
        mock, max_retries=2, initial_delay=0.0, jitter_factor=0.0
    )

    request = httpx.Request("GET", "https://example.com")
    response = await transport.handle_async_request(request)

    assert response.status_code == 503
    assert mock.attempt == 3


@pytest.mark.asyncio
async def test_respects_retry_after_header():
    mock = MockTransport(
        [_make_response(429, headers={"retry-after": "0.0"}), _make_response(200)]
    )
    transport = _make_retry_transport(mock, initial_delay=0.1, jitter_factor=0.0)

    with patch("app.core.http.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        request = httpx.Request("GET", "https://example.com")
        response = await transport.handle_async_request(request)

    assert response.status_code == 200
    mock_sleep.assert_called_once_with(0.0)


@pytest.mark.asyncio
async def test_caps_retry_after_at_max_delay():
    mock = MockTransport(
        [_make_response(429, headers={"retry-after": "60"}), _make_response(200)]
    )
    transport = _make_retry_transport(
        mock, initial_delay=0.1, max_delay=4.0, jitter_factor=0.0
    )

    with patch("app.core.http.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        request = httpx.Request("GET", "https://example.com")
        response = await transport.handle_async_request(request)

    assert response.status_code == 200
    mock_sleep.assert_called_once_with(4.0)


@pytest.mark.asyncio
async def test_backoff_delays_increase_exponentially():
    mock = MockTransport(
        [_make_response(503) for _ in range(3)] + [_make_response(200)]
    )
    transport = _make_retry_transport(
        mock,
        max_retries=3,
        initial_delay=0.5,
        multiplier=2.0,
        max_delay=4.0,
        jitter_factor=0.0,
    )

    with patch("app.core.http.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        request = httpx.Request("GET", "https://example.com")
        response = await transport.handle_async_request(request)

    assert response.status_code == 200
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [0.5, 1.0, 2.0]


@pytest.mark.asyncio
async def test_stops_retrying_when_total_time_exceeded():
    mock = MockTransport([_make_response(503) for _ in range(4)])
    transport = _make_retry_transport(
        mock, max_retries=3, initial_delay=0.0, jitter_factor=0.0, max_total_time=0.0
    )

    request = httpx.Request("GET", "https://example.com")
    response = await transport.handle_async_request(request)

    assert response.status_code == 503
    assert mock.attempt == 1


@pytest.mark.asyncio
async def test_create_http_client_returns_async_client():
    client = create_http_client(timeout=5.0)
    try:
        assert isinstance(client, httpx.AsyncClient)
    finally:
        await client.aclose()
