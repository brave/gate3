from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from ...models import SwapType


class NearIntentsToken(BaseModel):
    asset_id: str = Field(alias="assetId")
    decimals: int
    blockchain: str
    symbol: str
    contract_address: str | None = Field(default=None, alias="contractAddress")


class NearIntentsDepositMode(str, Enum):
    SIMPLE = "SIMPLE"
    MEMO = "MEMO"


class NearIntentsQuoteRequestBody(BaseModel):
    dry: bool = Field(default=False, description="Dry run flag")
    deposit_mode: NearIntentsDepositMode = Field(alias="depositMode")
    swap_type: SwapType = Field(alias="swapType")
    slippage_tolerance: int = Field(alias="slippageTolerance")
    origin_asset_id: str = Field(alias="originAsset")
    deposit_type: str = Field(default="ORIGIN_CHAIN", alias="depositType")
    destination_asset_id: str = Field(alias="destinationAsset")
    amount: str
    refund_to: str = Field(alias="refundTo")
    refund_type: str = Field(default="ORIGIN_CHAIN", alias="refundType")
    recipient: str
    recipient_type: str = Field(default="DESTINATION_CHAIN", alias="recipientType")
    deadline: str
    referral: str = Field(default="brave")
    quote_waiting_time_ms: int = Field(default=0, alias="quoteWaitingTimeMs")

    model_config = ConfigDict(populate_by_name=True)


class NearIntentsQuoteData(BaseModel):
    amount_in: str = Field(alias="amountIn")
    amount_in_formatted: str = Field(alias="amountInFormatted")
    amount_in_usd: str | None = Field(default=None, alias="amountInUsd")
    min_amount_in: str | None = Field(default=None, alias="minAmountIn")

    amount_out: str = Field(alias="amountOut")
    amount_out_formatted: str = Field(alias="amountOutFormatted")
    amount_out_usd: str | None = Field(default=None, alias="amountOutUsd")
    min_amount_out: str = Field(alias="minAmountOut")

    deadline: datetime | None = None
    time_when_inactive: datetime | None = Field(default=None, alias="timeWhenInactive")
    time_estimate: int = Field(alias="timeEstimate")

    deposit_address: str | None = Field(default=None, alias="depositAddress")
    deposit_memo: str | None = Field(default=None, alias="depositMemo")


class NearIntentsQuoteResponse(BaseModel):
    quote_request: NearIntentsQuoteRequestBody = Field(alias="quoteRequest")
    quote: NearIntentsQuoteData


class NearIntentsTransactionDetails(BaseModel):
    hash: str
    explorer_url: str | None = Field(default=None, alias="explorerUrl")


class NearIntentsSwapDetails(BaseModel):
    """Swap details from NEAR Intents status response"""

    intent_hashes: list[str] = Field(default_factory=list, alias="intentHashes")
    near_tx_hashes: list[str] = Field(default_factory=list, alias="nearTxHashes")

    amount_in: str | None = Field(default=None, alias="amountIn")
    amount_in_formatted: str | None = Field(default=None, alias="amountInFormatted")
    amount_in_usd: str | None = Field(default=None, alias="amountInUsd")

    amount_out: str | None = Field(default=None, alias="amountOut")
    amount_out_formatted: str | None = Field(default=None, alias="amountOutFormatted")
    amount_out_usd: str | None = Field(default=None, alias="amountOutUsd")

    refunded_amount: str | None = Field(default=None, alias="refundedAmount")
    refunded_amount_formatted: str | None = Field(
        default=None, alias="refundedAmountFormatted"
    )

    origin_chain_tx_hashes: list[NearIntentsTransactionDetails] = Field(
        default_factory=list, alias="originChainTxHashes"
    )
    destination_chain_tx_hashes: list[NearIntentsTransactionDetails] = Field(
        default_factory=list, alias="destinationChainTxHashes"
    )


class NearIntentsStatusResponse(BaseModel):
    quote_response: NearIntentsQuoteResponse = Field(alias="quoteResponse")
    status: str
    updated_at: datetime = Field(alias="updatedAt")
    swap_details: NearIntentsSwapDetails = Field(alias="swapDetails")


class NearIntentsError(BaseModel):
    message: str
