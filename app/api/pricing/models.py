from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.api.common.annotations import (
    CHAIN_ID_DESCRIPTION,
    ADDRESS_DESCRIPTION,
    VS_CURRENCY_DESCRIPTION,
    COIN_TYPE_DESCRIPTION,
)
from app.api.common.models import CoinType, ChainId


class VsCurrency(str, Enum):
    USD = "usd"
    EUR = "eur"


class CacheStatus(str, Enum):
    HIT = "HIT"
    MISS = "MISS"


class TokenRequest(BaseModel):
    coin_type: CoinType = Field(description=COIN_TYPE_DESCRIPTION)
    chain_id: ChainId | None = Field(default=None, description=CHAIN_ID_DESCRIPTION)
    address: str | None = Field(default=None, description=ADDRESS_DESCRIPTION)
    vs_currency: VsCurrency = Field(
        default=VsCurrency.USD, description=VS_CURRENCY_DESCRIPTION
    )

    @model_validator(mode="after")
    def validate_chain_specific_fields(self) -> "TokenRequest":
        if self.coin_type in (CoinType.ETH, CoinType.SOL):
            if not self.chain_id:
                raise ValueError(
                    f"chain_id is required for CoinType.{self.coin_type.name}"
                )
            if not self.address:
                raise ValueError(
                    f"address is required for CoinType.{self.coin_type.name}"
                )
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "coin_type": CoinType.ETH,
                    "chain_id": ChainId.ETHEREUM,
                    "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                    "vs_currency": VsCurrency.USD,
                },
                {"coin_type": CoinType.BTC, "vs_currency": VsCurrency.USD},
            ]
        }
    }


class TokenResponse(TokenRequest):
    price: float
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
