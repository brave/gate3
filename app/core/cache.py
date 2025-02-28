import redis.asyncio as redis

from app.config import settings


class Cache:
    _redis_client: redis.Redis | None = None

    @classmethod
    async def init(cls) -> None:
        cls._redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
        )

    @classmethod
    async def get_client(cls) -> redis.Redis:
        if cls._redis_client is None:
            await cls.init()
        return cls._redis_client

    @classmethod
    async def ping(cls) -> bool:
        if cls._redis_client:
            return await cls._redis_client.ping()
        return False

    @classmethod
    async def close(cls) -> None:
        if cls._redis_client:
            await cls._redis_client.aclose()
            cls._redis_client = None
