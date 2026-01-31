from unittest.mock import AsyncMock, patch

import pytest

from .cache import DepositSubmitRateLimiter


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    with patch("app.api.swap.providers.near_intents.cache.Cache") as mock_cache:
        mock_redis_client = AsyncMock()
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_redis_client)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_cache.get_client.return_value = mock_context
        yield mock_redis_client


@pytest.mark.asyncio
async def test_should_submit_returns_true_when_key_not_exists(mock_redis):
    """First submission for a deposit address should proceed."""
    mock_redis.set.return_value = True  # Key was set (didn't exist)

    result = await DepositSubmitRateLimiter.should_submit("deposit_addr_123")

    assert result is True
    mock_redis.set.assert_called_once_with(
        "swap:near_intents:deposit_submit:deposit_addr_123",
        "1",
        nx=True,
        ex=5,
    )


@pytest.mark.asyncio
async def test_should_submit_returns_false_when_key_exists(mock_redis):
    """Subsequent submission within interval should be rate-limited."""
    mock_redis.set.return_value = None  # Key already exists

    result = await DepositSubmitRateLimiter.should_submit("deposit_addr_123")

    assert result is False


def test_cache_key_format():
    """Verify cache key format includes proper prefix."""
    key = DepositSubmitRateLimiter._get_cache_key("test_addr")
    assert key == "swap:near_intents:deposit_submit:test_addr"
