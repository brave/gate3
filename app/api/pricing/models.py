from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.api.common.annotations import (
    ADDRESS_DESCRIPTION,
    CHAIN_ID_DESCRIPTION,
    COIN_TYPE_DESCRIPTION,
    VS_CURRENCY_DESCRIPTION,
)
from app.api.common.models import ChainId, CoinType


class VsCurrency(str, Enum):
    USD = "usd"
    EUR = "eur"


class CacheStatus(str, Enum):
    HIT = "HIT"
    MISS = "MISS"


class TokenPriceRequest(BaseModel):
    coin_type: CoinType = Field(description=COIN_TYPE_DESCRIPTION)
    chain_id: ChainId | None = Field(default=None, description=CHAIN_ID_DESCRIPTION)
    address: str | None = Field(default=None, description=ADDRESS_DESCRIPTION)

    @model_validator(mode="after")
    def validate_chain_specific_fields(self) -> "TokenPriceRequest":
        if self.coin_type in (CoinType.ETH, CoinType.SOL):
            if not self.chain_id:
                raise ValueError(
                    f"chain_id is required for CoinType.{self.coin_type.name}"
                )

        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "coin_type": CoinType.ETH,
                    "chain_id": ChainId.ETHEREUM,
                    "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                },
                {"coin_type": CoinType.BTC},
                {
                    "coin_type": CoinType.SOL,
                    "chain_id": ChainId.SOLANA,
                    "address": "",
                },
                {
                    "coin_type": CoinType.SOL,
                    "chain_id": ChainId.SOLANA,
                    "address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                },
            ]
        }
    }


class TokenPriceResponse(TokenPriceRequest):
    price: float
    vs_currency: VsCurrency = Field(
        default=VsCurrency.USD, description=VS_CURRENCY_DESCRIPTION
    )
    cache_status: CacheStatus

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "coin_type": CoinType.ETH,
                    "chain_id": ChainId.ETHEREUM,
                    "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                    "vs_currency": VsCurrency.USD,
                    "price": 1.01,
                    "cache_status": CacheStatus.MISS,
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
                            "coin_type": CoinType.ETH,
                            "chain_id": ChainId.ETHEREUM,
                            "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                        },
                        {"coin_type": CoinType.BTC},
                        {
                            "coin_type": CoinType.SOL,
                            "chain_id": ChainId.SOLANA,
                            "address": "",
                        },
                        {
                            "coin_type": CoinType.SOL,
                            "chain_id": ChainId.SOLANA,
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
