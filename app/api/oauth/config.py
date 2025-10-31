from pydantic import BaseModel, HttpUrl


class EnvironmentConfig(BaseModel):
    """Base environment config - all providers have OAuth URL."""

    oauth_url: HttpUrl
    client_id: str
    client_secret: str


class GeminiConfig(BaseModel):
    """Gemini OAuth configuration."""

    sandbox: EnvironmentConfig
    production: EnvironmentConfig

    def get_env_config(self, environment: str) -> EnvironmentConfig:
        """Get environment-specific config."""
        return self.sandbox if environment == "sandbox" else self.production


class BitflyerConfig(BaseModel):
    """Bitflyer OAuth configuration."""

    sandbox: EnvironmentConfig
    production: EnvironmentConfig

    def get_env_config(self, environment: str) -> EnvironmentConfig:
        """Get environment-specific config."""
        return self.sandbox if environment == "sandbox" else self.production


class UpholdConfig(BaseModel):
    """Uphold OAuth configuration."""

    class Config(EnvironmentConfig):
        api_url: HttpUrl

    sandbox: Config
    production: Config

    def get_env_config(self, environment: str) -> Config:
        """Get environment-specific config."""
        return self.sandbox if environment == "sandbox" else self.production


class ZebpayConfig(BaseModel):
    """Zebpay OAuth configuration."""

    class Config(EnvironmentConfig):
        api_url: HttpUrl

    sandbox: Config
    production: Config

    def get_env_config(self, environment: str) -> Config:
        """Get environment-specific config."""
        return self.sandbox if environment == "sandbox" else self.production


class OAuthConfig(BaseModel):
    """
    OAuth provider configuration.
    Environment variables use nested structure with OAUTH__ prefix.
    Example: OAUTH__GEMINI__SANDBOX__CLIENT_ID
    """

    gemini: GeminiConfig
    bitflyer: BitflyerConfig
    uphold: UpholdConfig
    zebpay: ZebpayConfig
