from enum import Enum

from pydantic import BaseModel


class HealthStatus(str, Enum):
    OK = "OK"
    KO = "KO"


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
    has_nft_support: bool


class Chain(Enum):
    # EVM chains
    ETHEREUM = _c(
        coin=Coin.ETH,
        chain_id="0x1",
        simplehash_id="ethereum",
        alchemy_id="eth-mainnet",
        has_nft_support=True,
    )
    ARBITRUM = _c(
        coin=Coin.ETH,
        chain_id="0xa4b1",
        simplehash_id="arbitrum",
        alchemy_id="arb-mainnet",
        has_nft_support=True,
    )
    AVALANCHE = _c(
        coin=Coin.ETH,
        chain_id="0xa86a",
        simplehash_id="avalanche",
        alchemy_id="avax-mainnet",
        has_nft_support=True,
    )
    BASE = _c(
        coin=Coin.ETH,
        chain_id="0x2105",
        simplehash_id="base",
        alchemy_id="base-mainnet",
        has_nft_support=True,
    )
    BNB_CHAIN = _c(
        coin=Coin.ETH,
        chain_id="0x38",
        simplehash_id="bsc",
        alchemy_id="bnb-mainnet",
        has_nft_support=False,
    )
    OPTIMISM = _c(
        coin=Coin.ETH,
        chain_id="0xa",
        simplehash_id="optimism",
        alchemy_id="opt-mainnet",
        has_nft_support=True,
    )
    POLYGON = _c(
        coin=Coin.ETH,
        chain_id="0x89",
        simplehash_id="polygon",
        alchemy_id="polygon-mainnet",
        has_nft_support=True,
    )

    # Non-EVM chains
    BITCOIN = _c(
        coin=Coin.BTC,
        chain_id="bitcoin_mainnet",
        simplehash_id="bitcoin",
        alchemy_id="bitcoin-mainnet",
        has_nft_support=False,
    )
    SOLANA = _c(
        coin=Coin.SOL,
        chain_id="0x65",
        simplehash_id="solana",
        alchemy_id="sol-mainnet",
        has_nft_support=True,
    )
    FILECOIN = _c(
        coin=Coin.FIL,
        chain_id="f",
        simplehash_id="filecoin",
        alchemy_id="filecoin-mainnet",
        has_nft_support=False,
    )
    CARDANO = _c(
        coin=Coin.ADA,
        chain_id="cardano_mainnet",
        simplehash_id="cardano",
        alchemy_id="cardano-mainnet",
        has_nft_support=False,
    )
    ZCASH = _c(
        coin=Coin.ZEC,
        chain_id="zcash_mainnet",
        simplehash_id="zcash",
        alchemy_id="zcash-mainnet",
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
            "has_nft_support",
        ]:
            return getattr(self.value, name)

        return super().__getattr__(name)

    @staticmethod
    def get(coin: str, chain_id: str):
        for chain in Chain:
            if chain.coin.value == coin.upper() and chain.chain_id == chain_id.lower():
                return chain

        return None

    def __repr__(self):
        return f"<{self.__class__.__name__}.{self.name}: coin={self.coin.value} chain_id={self.chain_id}>"
