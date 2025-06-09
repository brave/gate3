import json
from datetime import datetime, timedelta

from cachetools import TTLCache

from app.api.common.models import CoinType
from app.core.cache import Cache

from .models import (
    BatchTokenPriceRequests,
    CacheStatus,
    CoingeckoPlatform,
    TokenPriceRequest,
    TokenPriceResponse,
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
            for request in batch.requests
        ]

        async with Cache.get_client() as redis:
            # Batch get all values
            cached_values = await redis.mget(cache_keys)
            cached_responses: list[TokenPriceResponse] = []

            # Process results
            for request, cached_value in zip(batch.requests, cached_values):
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


class PlatformMapCache:
    """Two-level cache for CoinGecko platform mapping data.

    Level 1: Memory cache (TTLCache)
    - 1-minute TTL, cleared on restart
    - First line of defense to reduce Redis load

    Level 2: Redis cache
    - 1-day TTL, persistent across restarts
    - Source of truth, populates memory cache on miss

    Both caches are updated on set() and memory cache is populated from Redis on miss.
    """

    CACHE_KEY = "coingecko:platform_map"
    REDIS_TTL = timedelta(days=1)

    MEMCACHE_KEY = "platform_map"
    MEMCACHE_TTL = timedelta(hours=6)
    memcache = TTLCache(maxsize=1, ttl=MEMCACHE_TTL, timer=datetime.now)

    @classmethod
    async def get(cls) -> dict[str, CoingeckoPlatform] | None:
        # Check memory cache first
        if cls.MEMCACHE_KEY in cls.memcache:
            return cls.memcache[cls.MEMCACHE_KEY]

        # If memory cache is empty or expired, try Redis
        async with Cache.get_client() as redis:
            data_json = await redis.get(cls.CACHE_KEY)
            if not data_json:
                return None

            data = json.loads(data_json)
            platform_map = {
                platform_id: CoingeckoPlatform.model_validate(data)
                for platform_id, data in data.items()
            }

            # Update memcache
            cls.memcache[cls.MEMCACHE_KEY] = platform_map
            return platform_map

    @classmethod
    async def set(
        cls, platform_map: dict[str, CoingeckoPlatform], ttl: timedelta = REDIS_TTL
    ) -> None:
        # Update memcache
        cls.memcache[cls.MEMCACHE_KEY] = platform_map

        # Update Redis cache
        async with Cache.get_client() as redis:
            data = {
                platform_id: data.model_dump()
                for platform_id, data in platform_map.items()
            }
            await redis.setex(cls.CACHE_KEY, ttl, json.dumps(data))


class CoinMapCache:
    """Two-level cache for CoinGecko coin mapping data.

    Level 1: Memory cache (TTLCache)
    - 5-minute TTL, cleared on restart
    - First line of defense to reduce Redis load

    Level 2: Redis cache
    - 1-day TTL, persistent across restarts
    - Source of truth, populates memory cache on miss

    Both caches are updated on set() and memory cache is populated from Redis on miss.
    """

    CACHE_KEY = "coingecko:coin_map"
    REDIS_TTL = timedelta(days=1)

    MEMCACHE_KEY = "coin_map"
    MEMCACHE_TTL = timedelta(hours=6)
    memcache = TTLCache(maxsize=1, ttl=MEMCACHE_TTL, timer=datetime.now)

    @classmethod
    async def get(cls) -> dict[str, dict[str, str]] | None:
        # Check memory cache first
        if cls.MEMCACHE_KEY in cls.memcache:
            return cls.memcache[cls.MEMCACHE_KEY]

        # If memory cache is empty or expired, try Redis
        async with Cache.get_client() as redis:
            data = await redis.get(cls.CACHE_KEY)
            if not data:
                return None

            coin_map = json.loads(data)
            # Update memory cache
            cls.memcache[cls.MEMCACHE_KEY] = coin_map
            return coin_map

    @classmethod
    async def set(
        cls, coin_map: dict[str, dict[str, str]], ttl: timedelta = REDIS_TTL
    ) -> None:
        # Update memcache
        cls.memcache[cls.MEMCACHE_KEY] = coin_map

        # Update Redis cache
        async with Cache.get_client() as redis:
            await redis.setex(cls.CACHE_KEY, ttl, json.dumps(coin_map))
