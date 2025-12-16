from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # General
    ENVIRONMENT: str = "development"

    # API keys
    COINGECKO_API_KEY: str | None = None
    ALCHEMY_API_KEY: str | None = None
    NEAR_INTENTS_JWT: str | None = None

    # Database config
    REDIS_HOST: str = "redis-master"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None

    # Swap providers
    NEAR_INTENTS_BASE_URL: str = "https://1click.chaindefuser.com"

    # Monitoring
    SENTRY_DSN: str | None = None
    PROMETHEUS_PORT: int = 8090

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
