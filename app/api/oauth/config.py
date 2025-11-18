from pydantic import BaseModel, HttpUrl


class EnvironmentConfig(BaseModel):
    """Base environment config - all providers have OAuth URL."""

    oauth_url: HttpUrl
    client_id: str
    client_secret: str


class ProviderConfigBase(BaseModel):
    """Base class for OAuth provider configurations."""

    def get_env_config(self, environment: str):
        """Get environment-specific config."""
        return self.sandbox if environment == "sandbox" else self.production


class GeminiConfig(ProviderConfigBase):
    """Gemini OAuth configuration."""

    sandbox: EnvironmentConfig
    production: EnvironmentConfig


class BitflyerConfig(ProviderConfigBase):
    """Bitflyer OAuth configuration."""

    sandbox: EnvironmentConfig
    production: EnvironmentConfig


class UpholdConfig(ProviderConfigBase):
    """Uphold OAuth configuration."""

    class Config(EnvironmentConfig):
        api_url: HttpUrl

    sandbox: Config
    production: Config


class ZebpayConfig(ProviderConfigBase):
    """Zebpay OAuth configuration."""

    class Config(EnvironmentConfig):
        api_url: HttpUrl

    sandbox: Config
    production: Config


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
