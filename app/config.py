from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    COINGECKO_API_KEY: str
    COINGECKO_API_URL: str

    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_DB: int
    REDIS_PASSWORD: str | None = None

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
