from enum import Enum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.api.common.annotations import (
    ADDRESS_DESCRIPTION,
    CHAIN_ID_DESCRIPTION,
    COIN_DESCRIPTION,
)


class HealthStatus(str, Enum):
    OK = "OK"
    KO = "KO"


class Tags(str, Enum):
    """API documentation tags for grouping endpoints in Swagger UI."""

    HEALTH = "Health"
    NFT = "NFT"
    OAUTH = "OAuth Proxy"
    PRICING = "Pricing"
    SWAP = "Swap"
    TOKENS = "Tokens"


class PingResponse(BaseModel):
    redis: HealthStatus


class Coin(str, Enum):
    ADA = "ADA"
    BTC = "BTC"
    ETH = "ETH"
    FIL = "FIL"
    SOL = "SOL"
    ZEC = "ZEC"


class _c(BaseModel):
    coin: Coin
    chain_id: str
    simplehash_id: str
    alchemy_id: str
    near_intents_id: str | None = None
    has_nft_support: bool


class ChainSpec(BaseModel):
    coin: Coin = Field(description="Coin identifier")
    chain_id: str = Field(description="Chain identifier")

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class Chain(Enum):
    # EVM chains
    ETHEREUM = _c(
        coin=Coin.ETH,
        chain_id="0x1",
        simplehash_id="ethereum",
        alchemy_id="eth-mainnet",
        near_intents_id="eth",
        has_nft_support=True,
    )
    ARBITRUM = _c(
        coin=Coin.ETH,
        chain_id="0xa4b1",
        simplehash_id="arbitrum",
        alchemy_id="arb-mainnet",
        near_intents_id="arb",
        has_nft_support=True,
    )
    AVALANCHE = _c(
        coin=Coin.ETH,
        chain_id="0xa86a",
        simplehash_id="avalanche",
        alchemy_id="avax-mainnet",
        near_intents_id="avax",
        has_nft_support=True,
    )
    BASE = _c(
        coin=Coin.ETH,
        chain_id="0x2105",
        simplehash_id="base",
        alchemy_id="base-mainnet",
        near_intents_id="base",
        has_nft_support=True,
    )
    BNB_CHAIN = _c(
        coin=Coin.ETH,
        chain_id="0x38",
        simplehash_id="bsc",
        alchemy_id="bnb-mainnet",
        near_intents_id="bsc",
        has_nft_support=False,
    )
    OPTIMISM = _c(
        coin=Coin.ETH,
        chain_id="0xa",
        simplehash_id="optimism",
        alchemy_id="opt-mainnet",
        near_intents_id="op",
        has_nft_support=True,
    )
    POLYGON = _c(
        coin=Coin.ETH,
        chain_id="0x89",
        simplehash_id="polygon",
        alchemy_id="polygon-mainnet",
        near_intents_id="pol",
        has_nft_support=True,
    )

    # Non-EVM chains
    BITCOIN = _c(
        coin=Coin.BTC,
        chain_id="bitcoin_mainnet",
        simplehash_id="bitcoin",
        alchemy_id="bitcoin-mainnet",
        near_intents_id="btc",
        has_nft_support=False,
    )
    SOLANA = _c(
        coin=Coin.SOL,
        chain_id="0x65",
        simplehash_id="solana",
        alchemy_id="solana-mainnet",
        near_intents_id="sol",
        has_nft_support=True,
    )
    FILECOIN = _c(
        coin=Coin.FIL,
        chain_id="f",
        simplehash_id="filecoin",
        alchemy_id="filecoin-mainnet",
        near_intents_id=None,
        has_nft_support=False,
    )
    CARDANO = _c(
        coin=Coin.ADA,
        chain_id="cardano_mainnet",
        simplehash_id="cardano",
        alchemy_id="cardano-mainnet",
        near_intents_id="cardano",
        has_nft_support=False,
    )
    ZCASH = _c(
        coin=Coin.ZEC,
        chain_id="zcash_mainnet",
        simplehash_id="zcash",
        alchemy_id="zcash-mainnet",
        near_intents_id="zec",
        has_nft_support=False,
    )

    def __getattr__(self, name):
        """Delegate attribute access to the chain info"""
        # Only delegate specific attributes to avoid recursion
        if name in [
            "coin",
            "chain_id",
            "simplehash_id",
            "alchemy_id",
            "near_intents_id",
            "has_nft_support",
        ]:
            return getattr(self.value, name)

        return super().__getattr__(name)

    @classmethod
    def get(cls, coin: str, chain_id: str):
        for chain in cls:
            if chain.coin.value == coin.upper() and chain.chain_id == chain_id.lower():
                return chain

        return None

    @classmethod
    def get_by_near_intents_id(cls, near_intents_id: str):
        for chain in cls:
            if chain.near_intents_id == near_intents_id.lower():
                return chain
        return None

    def to_spec(self) -> ChainSpec:
        return ChainSpec(coin=self.coin, chain_id=self.chain_id)

    def __eq__(self, other: Chain) -> bool:
        return self.coin == other.coin and self.chain_id == other.chain_id

    def __str__(self):
        return f"<{self.__class__.__name__}.{self.name}: coin={self.coin.value} chain_id={self.chain_id}>"

    def __repr__(self):
        return self.__str__()


class TokenSource(str, Enum):
    COINGECKO = "coingecko"
    JUPITER_LST = "jupiter_lst"
    JUPITER_VERIFIED = "jupiter_verified"
    BRAVE = "brave"
    NEAR_INTENTS = "near_intents"
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
    near_intents_asset_id: str | None = Field(None, description="NEAR Intents asset ID")

    @property
    def chain(self) -> Chain | None:
        return Chain.get(self.coin.value, self.chain_id)

    def is_native(self) -> bool:
        return not self.address
