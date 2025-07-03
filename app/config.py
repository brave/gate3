import os
from pydantic_settings import BaseSettings, SettingsConfigDict, Field


class Settings(BaseSettings):
    COINGECKO_API_KEY: str | None = None
    ALCHEMY_API_KEY: str | None = None

    REDIS_HOST: str = "redis-master"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None

    PROMETHEUS_PORT: int = 8090

    model_config = SettingsConfigDict(env_file=".env")

    class Config:
        fields = {
            'REDIS_PASSWORD': {
                'env': 'REDIS_PASSWORD'
            }
        }


settings = Settings()
