from enum import Enum

from pydantic import BaseModel, Field

from app.api.common.annotations import (
    ADDRESS_DESCRIPTION,
    CHAIN_ID_DESCRIPTION,
    COIN_DESCRIPTION,
    VS_CURRENCY_DESCRIPTION,
)
from app.api.common.models import Chain, Coin


class VsCurrency(str, Enum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    JPY = "JPY"
    CNY = "CNY"
    AUD = "AUD"
    CAD = "CAD"
    CHF = "CHF"
    INR = "INR"
    MXN = "MXN"
    BRL = "BRL"

    AED = "AED"
    ARS = "ARS"
    DKK = "DKK"
    HKD = "HKD"
    ILS = "ILS"
    KRW = "KRW"
    NOK = "NOK"
    NZD = "NZD"
    PLN = "PLN"
    RUB = "RUB"
    SAR = "SAR"
    SEK = "SEK"
    SGD = "SGD"
    THB = "THB"
    TRY = "TRY"
    ZAR = "ZAR"


class CacheStatus(str, Enum):
    HIT = "HIT"
    MISS = "MISS"


class PriceSource(str, Enum):
    COINGECKO = "coingecko"
    JUPITER = "jupiter"


class TokenPriceRequest(BaseModel):
    coin: Coin = Field(description=COIN_DESCRIPTION)
    chain_id: str = Field(description=CHAIN_ID_DESCRIPTION)
    address: str | None = Field(default=None, description=ADDRESS_DESCRIPTION)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "coin": Chain.ETHEREUM.coin,
                    "chain_id": Chain.ETHEREUM.chain_id,
                    "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                },
                {
                    "coin": Chain.BITCOIN.coin,
                    "chain_id": Chain.BITCOIN.chain_id,
                    "address": None,
                },
                {
                    "coin": Chain.SOLANA.coin,
                    "chain_id": Chain.SOLANA.chain_id,
                    "address": None,
                },
                {
                    "coin": Chain.SOLANA.coin,
                    "chain_id": Chain.SOLANA.chain_id,
                    "address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                },
            ]
        }
    }


class TokenPriceResponse(TokenPriceRequest):
    price: float
    percentage_change_24h: float | None = Field(
        default=None,
        description="24-hour price change percentage in the specified vs_currency",
    )
    vs_currency: VsCurrency = Field(
        default=VsCurrency.USD, description=VS_CURRENCY_DESCRIPTION
    )
    cache_status: CacheStatus
    source: PriceSource = Field(description="Source of the price data")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "coin": Chain.ETHEREUM.coin,
                    "chain_id": Chain.ETHEREUM.chain_id,
                    "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                    "vs_currency": VsCurrency.USD,
                    "price": 1.01,
                    "cache_status": CacheStatus.MISS,
                    "source": PriceSource.COINGECKO,
                    "percentage_change_24h": 2.5,
                }
            ]
        }
    }


class BatchTokenPriceRequests(BaseModel):
    requests: list[TokenPriceRequest] = Field(description="List of token requests")
    vs_currency: VsCurrency = Field(
        default=VsCurrency.USD, description=VS_CURRENCY_DESCRIPTION
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "requests": [
                        {
                            "coin": Chain.ETHEREUM.coin,
                            "chain_id": Chain.ETHEREUM.chain_id,
                            "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                        },
                        {
                            "coin": Chain.BITCOIN.coin,
                            "chain_id": Chain.BITCOIN.chain_id,
                            "address": None,
                        },
                        {
                            "coin": Chain.SOLANA.coin,
                            "chain_id": Chain.SOLANA.chain_id,
                            "address": None,
                        },
                        {
                            "coin": Chain.SOLANA.coin,
                            "chain_id": Chain.SOLANA.chain_id,
                            "address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                        },
                    ],
                    "vs_currency": VsCurrency.USD,
                }
            ]
        }
    }

    def add(self, request: TokenPriceRequest) -> None:
        self.requests.append(request)

    def is_empty(self) -> bool:
        return not self.requests

    def size(self) -> int:
        return len(self.requests)

    @classmethod
    def from_vs_currency(cls, vs_currency: VsCurrency) -> "BatchTokenPriceRequests":
        return BatchTokenPriceRequests(requests=[], vs_currency=vs_currency)


class CoingeckoPlatform(BaseModel):
    id: str
    chain_id: str | None
    native_token_id: str
