from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.api.common.models import Chain, Coin, TokenInfo, TokenSource, TokenType
from app.config import settings

from ..cache import SupportedTokensCache
from ..models import (
    SubmitDepositRequest,
    SwapDetails,
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


# ============================================================================
# Blockchain Mapping
# ============================================================================

# Map our Chain enum to NEAR Intents blockchain strings
CHAIN_TO_NEAR_INTENTS_BLOCKCHAIN = {
    Chain.ETHEREUM: "eth",
    Chain.ARBITRUM: "arb",
    Chain.AVALANCHE: "avax",
    Chain.BASE: "base",
    Chain.BNB_CHAIN: "bsc",
    Chain.OPTIMISM: "op",
    Chain.POLYGON: "pol",
    Chain.BITCOIN: "btc",
    Chain.SOLANA: "sol",
    Chain.CARDANO: "cardano",
}

# Reverse mapping
NEAR_INTENTS_BLOCKCHAIN_TO_CHAIN = {
    v: k for k, v in CHAIN_TO_NEAR_INTENTS_BLOCKCHAIN.items()
}

# Add additional blockchains that NEAR Intents supports but we might not have yet
NEAR_INTENTS_BLOCKCHAIN_TO_CHAIN.update(
    {
        "near": None,  # We don't have NEAR chain yet
        "ton": None,
        "doge": None,
        "xrp": None,
        "zec": Chain.ZCASH if hasattr(Chain, "ZCASH") else None,
        "gnosis": None,
        "bera": None,
        "tron": None,
        "sui": None,
    }
)


# ============================================================================
# Transformation Functions
# ============================================================================


def token_to_asset_id(token_info: TokenInfo) -> str | None:
    """Convert our TokenInfo to NEAR Intents asset ID format"""
    chain = token_info.chain
    if not chain:
        return None

    blockchain = CHAIN_TO_NEAR_INTENTS_BLOCKCHAIN.get(chain)
    if not blockchain:
        return None

    # Native tokens don't have contract address
    if token_info.address is None:
        # For native tokens, asset ID is typically the token symbol or blockchain
        # This might need adjustment based on actual NEAR Intents format
        return f"native:{blockchain}"

    # For contract tokens, use the contract address
    return token_info.address


def asset_id_to_token_parts(
    asset_id: str, blockchain: str
) -> tuple[Coin, str, str | None]:
    """
    Convert NEAR Intents asset ID and blockchain to our token format.

    Returns:
        Tuple of (coin, chain_id, address)
    """
    chain = NEAR_INTENTS_BLOCKCHAIN_TO_CHAIN.get(blockchain)
    if not chain:
        raise ValueError(f"Unsupported blockchain: {blockchain}")

    # Handle different asset ID formats
    if ":" in asset_id:
        prefix, value = asset_id.split(":", 1)
        if prefix in ["native", "nep141"]:
            # Native token
            return chain.coin, chain.chain_id, None
        else:
            # Token with prefix
            return chain.coin, chain.chain_id, value
    else:
        # Plain contract address
        return chain.coin, chain.chain_id, asset_id


def from_near_intents_token(token: NearIntentsTokenResponse) -> TokenInfo | None:
    """Transform NEAR Intents token to our TokenInfo format"""
    chain = Chain.get_by_near_intents_id(token.blockchain)
    if not chain:
        return None

    try:
        return TokenInfo(
            coin=chain.coin,
            chain_id=chain.chain_id,
            address=token.contract_address,
            near_intents_asset_id=token.asset_id,
            name=token.symbol,  # Use symbol as name since NEAR doesn't provide name
            symbol=token.symbol,
            decimals=token.decimals,
            logo=None,  # NEAR Intents doesn't provide logo URLs
            sources=[TokenSource.UNKNOWN],  # Mark as unknown source
            token_type=TokenType.UNKNOWN,  # We don't know the token type from NEAR
        )
    except (ValueError, KeyError):
        # Skip tokens for unsupported chains
        return None


def to_near_intents_request(
    request: SwapQuoteRequest, dry: bool = False
) -> NearIntentsQuoteRequestBody:
    """Transform our SwapQuoteRequest to NEAR Intents format"""
    # Get asset IDs
    source_chain = request.source_chain
    dest_chain = request.dest_chain

    if not source_chain or not dest_chain:
        raise ValueError("Invalid source or destination chain")

    source_blockchain = CHAIN_TO_NEAR_INTENTS_BLOCKCHAIN.get(source_chain)
    dest_blockchain = CHAIN_TO_NEAR_INTENTS_BLOCKCHAIN.get(dest_chain)

    if not source_blockchain or not dest_blockchain:
        raise ValueError("Source or destination chain not supported by NEAR Intents")

    # Format asset IDs
    if request.source_address:
        origin_asset = f"{request.source_address}"
    else:
        origin_asset = f"native:{source_blockchain}"

    if request.dest_address:
        destination_asset = f"{request.dest_address}"
    else:
        destination_asset = f"native:{dest_blockchain}"

    # Determine amount based on swap type
    if request.swap_type == SwapType.EXACT_INPUT:
        if not request.source_amount:
            raise ValueError("source_amount required for EXACT_INPUT swap")
        amount = request.source_amount
    elif request.swap_type == SwapType.EXACT_OUTPUT:
        if not request.dest_amount:
            raise ValueError("dest_amount required for EXACT_OUTPUT swap")
        amount = request.dest_amount
    else:
        # For FLEX_INPUT and ANY_INPUT, use source_amount
        amount = request.source_amount or request.dest_amount
        if not amount:
            raise ValueError("Either source_amount or dest_amount required")

    return NearIntentsQuoteRequestBody(
        dry=dry,
        swap_type=request.swap_type.value,
        origin_asset=origin_asset,
        destination_asset=destination_asset,
        amount=amount,
        slippage=request.slippage,
        recipient=request.recipient,
        refund_to=request.refund_address or request.recipient,
        deposit_mode="SIMPLE",  # TODO: Support MEMO mode when needed
    )


def from_near_intents_quote(
    response: NearIntentsQuoteResponse, request: SwapQuoteRequest
) -> SwapQuoteResponse:
    """Transform NEAR Intents quote response to our format"""
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

    async def supports_swap(self, request: SwapQuoteRequest) -> bool:
        """Check if NEAR Intents supports this swap"""
        # Check if chains are supported
        if not request.source_chain or not request.dest_chain:
            return False

        if (
            request.source_chain not in CHAIN_TO_NEAR_INTENTS_BLOCKCHAIN
            or request.dest_chain not in CHAIN_TO_NEAR_INTENTS_BLOCKCHAIN
        ):
            return False

        # Get supported tokens
        supported_tokens = await self.get_supported_tokens()

        # Check if source token is supported
        source_supported = any(
            t.coin == request.source_coin
            and t.chain_id == request.source_chain_id
            and t.address == request.source_address
            for t in supported_tokens
        )

        # Check if destination token is supported
        dest_supported = any(
            t.coin == request.dest_coin
            and t.chain_id == request.dest_chain_id
            and t.address == request.dest_address
            for t in supported_tokens
        )

        return source_supported and dest_supported

    async def get_indicative_quote(
        self, request: SwapQuoteRequest
    ) -> SwapQuoteResponse:
        """Get indicative quote (dry run)"""
        near_request = to_near_intents_request(request, dry=True)

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
        near_request = to_near_intents_request(request, dry=False)

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
