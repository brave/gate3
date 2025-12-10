import json
from datetime import timedelta

from app.core.cache import Cache

from .models import SwapProvider, TokenInfo


class SupportedTokensCache:
    """
    Single-level Redis cache for supported tokens per provider.

    # This cache only applies to providers that expose an API endpoint for
    # listing supported tokens. For providers that do not offer such an
    # endpoint, this cache is not applicable.
    """

    CACHE_PREFIX = "swap:tokens"
    DEFAULT_TTL = timedelta(hours=24)

    @classmethod
    def _get_cache_key(cls, provider: SwapProvider) -> str:
        return f"{cls.CACHE_PREFIX}:{provider.value}"

    @classmethod
    async def get(cls, provider: SwapProvider) -> list[TokenInfo] | None:
        cache_key = cls._get_cache_key(provider)

        async with Cache.get_client() as redis:
            data = await redis.get(cache_key)
            if not data:
                return None

            # Deserialize JSON to list of TokenInfo models
            tokens_data = json.loads(data)
            return [TokenInfo.model_validate(token) for token in tokens_data]

    @classmethod
    async def set(
        cls,
        provider: SwapProvider,
        tokens: list[TokenInfo],
        ttl: timedelta = DEFAULT_TTL,
    ) -> None:
        if not tokens:
            return

        cache_key = cls._get_cache_key(provider)

        # Serialize TokenInfo list to JSON
        tokens_data = [token.model_dump(mode="json") for token in tokens]
        data = json.dumps(tokens_data)

        async with Cache.get_client() as redis:
            await redis.setex(cache_key, ttl, data)
