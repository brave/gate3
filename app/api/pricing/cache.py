import json

from app.api.common.models import CoinType
from app.core.cache import Cache

from .models import (
    TokenPriceRequest,
    TokenPriceResponse,
    CacheStatus,
    BatchTokenPriceRequests,
    VsCurrency,
)


class TokenPriceCache:
    CACHE_PREFIX = "price"
    DEFAULT_TTL = 60  # 1 minute in seconds

    @classmethod
    async def get(
        cls, batch: BatchTokenPriceRequests
    ) -> tuple[list[TokenPriceResponse], BatchTokenPriceRequests]:
        """
        Get cached prices for multiple tokens in a single Redis operation.

        Returns a tuple of (cached_responses, tokens_to_fetch)
        """
        batch_to_fetch = BatchTokenPriceRequests.from_vs_currency(batch.vs_currency)
        if batch.is_empty():
            return [], batch_to_fetch

        # Generate cache keys for all tokens
        cache_keys = [
            cls._get_cache_key(param=request, vs_currency=batch.vs_currency)
            for request in batch
        ]

        async with Cache.get_client() as redis:
            # Batch get all values
            cached_values = await redis.mget(cache_keys)
            cached_responses: list[TokenPriceResponse] = []

            # Process results
            for request, cached_value in zip(batch, cached_values):
                if cached_value:
                    data = json.loads(cached_value)
                    cached_responses.append(
                        TokenPriceResponse(**data, cache_status=CacheStatus.HIT)
                    )
                else:
                    batch_to_fetch.add(request)

            return cached_responses, batch_to_fetch

    @classmethod
    async def set(
        cls, responses: list[TokenPriceResponse], ttl: int = DEFAULT_TTL
    ) -> None:
        """
        Cache multiple token price responses in a single Redis operation
        """
        if not responses:
            return

        # Prepare data for mset
        pipe_data = {}
        for response in responses:
            cache_key = cls._get_cache_key(
                param=response, vs_currency=response.vs_currency
            )
            data = response.model_dump()
            data.pop("cache_status")
            pipe_data[cache_key] = json.dumps(data)

        async with Cache.get_client() as redis:
            # Use pipeline for atomic operation
            pipe = await redis.pipeline()
            try:
                for key, value in pipe_data.items():
                    await pipe.setex(key, ttl, value)
                await pipe.execute()
            finally:
                await pipe.aclose()

    @classmethod
    def _get_cache_key(
        cls, param: TokenPriceRequest | TokenPriceResponse, vs_currency: VsCurrency
    ) -> str:
        """Generate cache key for a token"""
        # For BTC, ADA, FIL, ZEC, etc., just use the coin type
        if param.coin_type not in [CoinType.ETH, CoinType.SOL]:
            return f"{cls.CACHE_PREFIX}:{param.coin_type.value.lower()}:{vs_currency.value.lower()}"

        if param.address:
            return f"{cls.CACHE_PREFIX}:{param.coin_type.value.lower()}:{param.chain_id.value}:{param.address.lower()}:{vs_currency.value.lower()}"

        return f"{cls.CACHE_PREFIX}:{param.coin_type.value.lower()}:{param.chain_id.value}:{vs_currency.value.lower()}"
