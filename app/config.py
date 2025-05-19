from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    COINGECKO_API_KEY: str | None = None
    ALCHEMY_API_KEY: str | None = None

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None

    PROMETHEUS_PORT: int = 8093

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
