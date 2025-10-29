from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class NearIntentsToken(BaseModel):
    asset_id: str = Field(alias="assetId")
    decimals: int
    blockchain: str
    symbol: str
    contract_address: str | None = Field(default=None, alias="contractAddress")


class NearIntentsQuoteRequestBody(BaseModel):
    """Request body for NEAR Intents /v0/quote endpoint"""

    dry: bool = Field(default=False, description="Dry run flag")
    swap_type: str = Field(alias="swapType")
    origin_asset: str = Field(alias="originAsset")
    destination_asset: str = Field(alias="destinationAsset")
    amount: str
    slippage: int
    recipient: str
    refund_to: str = Field(alias="refundTo")
    deposit_mode: str = Field(default="SIMPLE", alias="depositMode")


class NearIntentsQuoteData(BaseModel):
    """Quote data from NEAR Intents response"""

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
    """Response from NEAR Intents /v0/quote endpoint"""

    timestamp: datetime
    signature: str | None = None
    quote_request: dict[str, Any] = Field(alias="quoteRequest")
    quote: NearIntentsQuoteData


class NearIntentsTransactionDetails(BaseModel):
    """Transaction details from NEAR Intents"""

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
    """Response from NEAR Intents /v0/status endpoint"""

    quote_response: NearIntentsQuoteResponse = Field(alias="quoteResponse")
    status: str
    updated_at: datetime = Field(alias="updatedAt")
    swap_details: NearIntentsSwapDetails = Field(alias="swapDetails")
