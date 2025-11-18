from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.api.common.models import Chain, Coin, TokenInfo, TokenSource, TokenType
from app.config import settings

from ..cache import SupportedTokensCache
from ..models import (
    SubmitDepositRequest,
    SwapDetails,
    SwapSupportRequest,
    SwapQuote,
    SwapQuoteRequest,
    SwapQuoteResponse,
    SwapStatus,
    SwapStatusResponse,
    SwapType,
    TransactionDetails,
)
from ..models import (
    SwapProvider as SwapProviderEnum,
)
from .base import SwapProvider

# ============================================================================
# Internal Models (NEAR Intents API Specific)
# ============================================================================


class NearIntentsTokenResponse(BaseModel):
    """Token response from NEAR Intents /v0/tokens endpoint"""

    asset_id: str = Field(alias="assetId")
    decimals: int
    blockchain: str
    symbol: str
    price: str
    price_updated_at: datetime = Field(alias="priceUpdatedAt")
    contract_address: str | None = Field(default=None, alias="contractAddress")


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

# ============================================================================
# Transformation Functions
# ============================================================================

def from_near_intents_quote(
    response: NearIntentsQuoteResponse, request: SwapQuoteRequest
) -> SwapQuoteResponse:
    quote_data = response.quote

    quote = SwapQuote(
        amount_in=quote_data.amount_in,
        amount_in_formatted=quote_data.amount_in_formatted,
        amount_in_usd=quote_data.amount_in_usd,
        amount_out=quote_data.amount_out,
        amount_out_formatted=quote_data.amount_out_formatted,
        amount_out_usd=quote_data.amount_out_usd,
        min_amount_out=quote_data.min_amount_out,
        estimated_time=quote_data.time_estimate,
        deposit_address=quote_data.deposit_address,
        deposit_memo=quote_data.deposit_memo,
        expires_at=quote_data.deadline,
    )

    return SwapQuoteResponse(
        provider=SwapProviderEnum.NEAR_INTENTS,
        quote=quote,
        provider_metadata={
            "timestamp": response.timestamp.isoformat(),
            "signature": response.signature,
            "quote_request": response.quote_request,
        },
    )


def normalize_near_intents_status(status: str) -> SwapStatus:
    """Normalize NEAR Intents status to our SwapStatus enum"""
    status_mapping = {
        "KNOWN_DEPOSIT_TX": SwapStatus.PENDING,
        "PENDING_DEPOSIT": SwapStatus.PENDING,
        "INCOMPLETE_DEPOSIT": SwapStatus.PENDING,
        "PROCESSING": SwapStatus.PROCESSING,
        "SUCCESS": SwapStatus.SUCCESS,
        "REFUNDED": SwapStatus.REFUNDED,
        "FAILED": SwapStatus.FAILED,
    }
    return status_mapping.get(status, SwapStatus.PENDING)


def from_near_intents_status(
    response: NearIntentsStatusResponse,
    request_source_chain: str,
    request_dest_chain: str,
) -> SwapStatusResponse:
    """Transform NEAR Intents status response to our format"""
    swap_details_data = response.swap_details

    # Collect all transactions
    transactions = []

    # Add origin chain transactions
    for tx in swap_details_data.origin_chain_tx_hashes:
        transactions.append(
            TransactionDetails(
                chain=request_source_chain,
                hash=tx.hash,
                explorer_url=tx.explorer_url,
                status=None,
            )
        )

    # Add destination chain transactions
    for tx in swap_details_data.destination_chain_tx_hashes:
        transactions.append(
            TransactionDetails(
                chain=request_dest_chain,
                hash=tx.hash,
                explorer_url=tx.explorer_url,
                status=None,
            )
        )

    swap_details = SwapDetails(
        amount_in=swap_details_data.amount_in,
        amount_in_formatted=swap_details_data.amount_in_formatted,
        amount_in_usd=swap_details_data.amount_in_usd,
        amount_out=swap_details_data.amount_out,
        amount_out_formatted=swap_details_data.amount_out_formatted,
        amount_out_usd=swap_details_data.amount_out_usd,
        refunded_amount=swap_details_data.refunded_amount,
        refunded_amount_formatted=swap_details_data.refunded_amount_formatted,
        fees=None,  # NEAR Intents doesn't provide separate fee info
        transactions=transactions,
    )

    return SwapStatusResponse(
        status=normalize_near_intents_status(response.status),
        source_chain=request_source_chain,
        dest_chain=request_dest_chain,
        swap_details=swap_details,
        updated_at=response.updated_at,
        provider=SwapProviderEnum.NEAR_INTENTS,
        provider_metadata={
            "original_status": response.status,
            "intent_hashes": swap_details_data.intent_hashes,
            "near_tx_hashes": swap_details_data.near_tx_hashes,
        },
    )


# ============================================================================
# NEAR Intents Client
# ============================================================================


class NearIntentsClient(SwapProvider):
    """NEAR Intents 1Click API client"""

    def __init__(self):
        self.base_url = settings.NEAR_INTENTS_BASE_URL
        self.jwt_token = settings.NEAR_INTENTS_JWT

    def _create_client(self) -> httpx.AsyncClient:
        headers = {}
        if self.jwt_token:
            headers["Authorization"] = f"Bearer {self.jwt_token}"

        return httpx.AsyncClient(
            timeout=30.0,
            headers=headers,
        )

    async def get_supported_tokens(self) -> list[TokenInfo]:
        """Get list of supported tokens from NEAR Intents"""
        # Check cache first
        cached_tokens = await SupportedTokensCache.get(SwapProviderEnum.NEAR_INTENTS)
        if cached_tokens:
            return cached_tokens

        # Fetch from API
        async with self._create_client() as client:
            response = await client.get(f"{self.base_url}/v0/tokens")
            response.raise_for_status()
            data = response.json()

            tokens = []
            for token_data in data:
                token = NearIntentsTokenResponse.model_validate(token_data)
                token_info = from_near_intents_token(token)
                if token_info:  # Only add tokens for supported chains
                    tokens.append(token_info)

            # Cache the results
            await SupportedTokensCache.set(SwapProviderEnum.NEAR_INTENTS, tokens)
            return tokens

    async def has_support(self, request: SwapSupportRequest | SwapQuoteRequest) -> bool:
        if not request.source_chain or not request.destination_chain:
            return False

        if (
            not request.source_chain.near_intents_id
            or not request.destination_chain.near_intents_id
        ):
            return False

        # Get supported tokens
        supported_tokens = await self.get_supported_tokens()

        # Check if source token is supported
        source_supported = any(
            t.coin == request.source_coin
            and t.chain_id == request.source_chain_id
            and t.address == request.source_token_address
            for t in supported_tokens
        )

        # Check if destination token is supported
        destination_supported = any(
            t.coin == request.destination_coin
            and t.chain_id == request.destination_chain_id
            and t.address == request.destination_token_address
            for t in supported_tokens
        )

        return source_supported and destination_supported

    async def get_indicative_quote(
        self, request: SwapQuoteRequest
    ) -> SwapQuoteResponse:
        supported_tokens = await self.get_supported_tokens()
        near_request = to_near_intents_request(
            request, dry=True, supported_tokens=supported_tokens
        )

        async with self._create_client() as client:
            response = await client.post(
                f"{self.base_url}/v0/quote",
                json=near_request.model_dump(by_alias=True),
            )
            response.raise_for_status()
            data = response.json()

            near_response = NearIntentsQuoteResponse.model_validate(data)
            return from_near_intents_quote(near_response, request)

    async def get_firm_quote(self, request: SwapQuoteRequest) -> SwapQuoteResponse:
        """Get firm quote with deposit address"""
        supported_tokens = await self.get_supported_tokens()
        near_request = to_near_intents_request(
            request, dry=False, supported_tokens=supported_tokens
        )

        async with self._create_client() as client:
            response = await client.post(
                f"{self.base_url}/v0/quote",
                json=near_request.model_dump(by_alias=True),
            )
            response.raise_for_status()
            data = response.json()

            near_response = NearIntentsQuoteResponse.model_validate(data)
            return from_near_intents_quote(near_response, request)

    async def get_swap_status(
        self, deposit_address: str, deposit_memo: str | None = None
    ) -> SwapStatusResponse:
        """Get swap status by deposit address"""
        params = {"depositAddress": deposit_address}
        if deposit_memo:
            params["depositMemo"] = deposit_memo

        async with self._create_client() as client:
            response = await client.get(f"{self.base_url}/v0/status", params=params)
            response.raise_for_status()
            data = response.json()

            near_response = NearIntentsStatusResponse.model_validate(data)

            # Extract chain info from the original quote request
            quote_req = near_response.quote_response.quote_request
            # For now, use placeholder values - ideally we'd parse from quote_request
            source_chain = "eth.0x1"  # Placeholder
            dest_chain = "sol.0x65"  # Placeholder

            return from_near_intents_status(near_response, source_chain, dest_chain)

    async def submit_deposit_tx(
        self, request: SubmitDepositRequest
    ) -> SwapStatusResponse:
        """Submit deposit transaction hash"""
        body = {
            "txHash": request.tx_hash,
            "depositAddress": request.deposit_address,
        }

        if request.deposit_memo:
            body["memo"] = request.deposit_memo

        if request.sender_account:
            body["nearSenderAccount"] = request.sender_account

        async with self._create_client() as client:
            response = await client.post(
                f"{self.base_url}/v0/deposit/submit",
                json=body,
            )
            response.raise_for_status()
            data = response.json()

            near_response = NearIntentsStatusResponse.model_validate(data)

            # Extract chain info from the original quote request
            quote_req = near_response.quote_response.quote_request
            # For now, use placeholder values
            source_chain = "eth.0x1"
            dest_chain = "sol.0x65"

            return from_near_intents_status(near_response, source_chain, dest_chain)
