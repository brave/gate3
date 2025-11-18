import os

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.api.oauth.config import OAuthConfig


class Settings(BaseSettings):
    # General
    ENVIRONMENT: str = "development"

    # API keys
    COINGECKO_API_KEY: str | None = None
    ALCHEMY_API_KEY: str | None = None

    # OAuth Provider credentials (nested)
    # Automatically uses OAUTH_ prefix from OAuthConfig
    oauth: OAuthConfig

    # Database config
    REDIS_HOST: str = "redis-master"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None

    # Monitoring
    SENTRY_DSN: str | None = None
    PROMETHEUS_PORT: int = 8090

    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env"),
        env_nested_delimiter="__",
    )


settings = Settings()
