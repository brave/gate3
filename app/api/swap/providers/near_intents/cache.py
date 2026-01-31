from app.core.cache import Cache


class DepositSubmitRateLimiter:
    """Redis-based rate limiter for deposit submissions.

    Uses atomic SET NX EX to ensure consistent rate-limiting across
    multiple worker processes in distributed deployments.
    """

    CACHE_PREFIX = "swap:near_intents:deposit_submit"
    CACHE_EXPIRATION_SECONDS = 5

    @classmethod
    def _get_cache_key(cls, deposit_address: str) -> str:
        return f"{cls.CACHE_PREFIX}:{deposit_address}"

    @classmethod
    async def should_submit(cls, deposit_address: str) -> bool:
        """Check if deposit submission should proceed.

        Uses atomic SET NX EX to both check and acquire the rate limit lock.
        Returns True if submission should proceed, False if rate-limited.
        """
        cache_key = cls._get_cache_key(deposit_address)

        async with Cache.get_client() as redis:
            # SET NX EX is atomic: sets key only if not exists, with expiration
            # Returns True if set succeeded (we should submit), None/False if key exists
            result = await redis.set(
                cache_key, "1", nx=True, ex=cls.CACHE_EXPIRATION_SECONDS
            )
            return result is True
