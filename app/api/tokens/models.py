from enum import Enum

from pydantic import BaseModel, Field

from app.api.common.annotations import (
    ADDRESS_DESCRIPTION,
    CHAIN_ID_DESCRIPTION,
    COIN_DESCRIPTION,
)
from app.api.common.models import Coin


class TokenSource(str, Enum):
    COINGECKO = "coingecko"
    JUPITER_LST = "jupiter_lst"
    JUPITER_VERIFIED = "jupiter_verified"
    BRAVE = "brave"
    UNKNOWN = "unknown"


class TokenType(str, Enum):
    ERC20 = "ERC20"
    ERC721 = "ERC721"
    ERC1155 = "ERC1155"
    SPL_TOKEN = "SPL_TOKEN"
    SPL_TOKEN_2022 = "SPL_TOKEN_2022"
    UNKNOWN = "UNKNOWN"


class TokenInfo(BaseModel):
    coin: Coin = Field(..., description=COIN_DESCRIPTION)
    chain_id: str = Field(..., description=CHAIN_ID_DESCRIPTION)
    address: str | None = Field(default=None, description=ADDRESS_DESCRIPTION)
    name: str = Field(..., description="Token name")
    symbol: str = Field(..., description="Token symbol")
    decimals: int = Field(..., description="Token decimals")
    logo: str | None = Field(None, description="Token logo URL")
    sources: list[TokenSource] = Field(..., description="Token sources")
    token_type: TokenType = Field(..., description="Token type")


class TokenSearchResponse(BaseModel):
    results: list[TokenInfo] = Field(..., description="Search results")
    offset: int = Field(..., description="Offset for pagination")
    limit: int = Field(..., description="Limit for pagination")
    total: int = Field(..., description="Total number of results")
    query: str = Field(..., description="Search query")
