from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from ...models import SwapType


class NearIntentsToken(BaseModel):
    asset_id: str = Field(alias="assetId")
    decimals: int
    blockchain: str
    symbol: str
    contract_address: str | None = Field(default=None)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class NearIntentsDepositMode(str, Enum):
    SIMPLE = "SIMPLE"
    MEMO = "MEMO"


class NearIntentsQuoteRequestBody(BaseModel):
    dry: bool = Field(default=False, description="Dry run flag")
    deposit_mode: NearIntentsDepositMode
    swap_type: SwapType
    slippage_tolerance: int
    origin_asset_id: str = Field(alias="originAsset")  # Exception: not originAssetId
    deposit_type: str = Field(default="ORIGIN_CHAIN")
    destination_asset_id: str = Field(
        alias="destinationAsset"
    )  # Exception: not destinationAssetId
    amount: str
    refund_to: str
    refund_type: str = Field(default="ORIGIN_CHAIN")
    recipient: str
    recipient_type: str = Field(default="DESTINATION_CHAIN")
    deadline: str
    referral: str = Field(default="brave")
    quote_waiting_time_ms: int = Field(default=0)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class NearIntentsQuoteData(BaseModel):
    amount_in: str
    amount_in_formatted: str
    amount_in_usd: str | None = Field(default=None)

    # EXACT_OUTPUT fields: min/max input amounts
    min_amount_in: str | None = Field(default=None)
    max_amount_in: str | None = Field(default=None)

    amount_out: str
    amount_out_formatted: str
    amount_out_usd: str | None = Field(default=None)
    min_amount_out: str

    deadline: datetime | None = None
    time_when_inactive: datetime | None = Field(default=None)
    time_estimate: int

    deposit_address: str | None = Field(default=None)
    deposit_memo: str | None = Field(default=None)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class NearIntentsQuoteResponse(BaseModel):
    quote_request: NearIntentsQuoteRequestBody
    quote: NearIntentsQuoteData

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class NearIntentsStatusResponse(BaseModel):
    status: str

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class NearIntentsError(BaseModel):
    message: str
