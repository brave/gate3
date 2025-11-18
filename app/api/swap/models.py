from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.api.common.models import Chain, Coin, TokenInfo

# ============================================================================
# Public Enums (Provider-Agnostic)
# ============================================================================


class SwapProvider(str, Enum):
    """Supported swap providers"""

    NEAR_INTENTS = "near_intents"
    ZERO_EX = "0x"
    JUPITER = "jupiter"
    LIFI = "lifi"


class SwapType(str, Enum):
    EXACT_INPUT = "EXACT_INPUT"
    EXACT_OUTPUT = "EXACT_OUTPUT"


class SwapStatus(str, Enum):
    """Normalized swap status across all providers"""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


# ============================================================================
# Public Models (Provider-Agnostic Common Format)
# ============================================================================


# TokenInfo is now imported from app.api.common.models
class SwapSupportRequest(BaseModel):
    source_coin: Coin = Field(description="Source coin type")
    source_chain_id: str = Field(description="Source chain ID")
    source_token_address: str | None = Field(
        default=None, description="Source token address (None for native)"
    )
    destination_coin: Coin = Field(description="Destination coin type")
    destination_chain_id: str = Field(description="Destination chain ID")
    destination_token_address: str | None = Field(
        default=None, description="Destination token address (None for native)"
    )
    recipient: str | None = Field(
        default=None, description="Recipient address on destination chain"
    )

    _source_token: TokenInfo | None = None
    _destination_token: TokenInfo | None = None

    @property
    def source_chain(self) -> Chain | None:
        return Chain.get(self.source_coin.value, self.source_chain_id)

    @property
    def destination_chain(self) -> Chain | None:
        return Chain.get(self.destination_coin.value, self.destination_chain_id)

    def set_source_token(self, tokens: list[TokenInfo]) -> None:
        for token in tokens:
            if (
                token.coin == self.source_coin
                and token.chain_id == self.source_chain_id
                and token.address == self.source_token_address
            ):
                self._source_token = token
                break

    def set_destination_token(self, tokens: list[TokenInfo]) -> None:
        for token in tokens:
            if (
                token.coin == self.destination_coin
                and token.chain_id == self.destination_chain_id
                and token.address == self.destination_token_address
            ):
                self._destination_token = token
                break

    @property
    def source_token(self) -> TokenInfo | None:
        return self._source_token

    @property
    def destination_token(self) -> TokenInfo | None:
        return self._destination_token


class SwapQuoteRequest(SwapSupportRequest):
    amount: str = Field(
        default=None,
        description="Amount to swap (in smallest unit)",
    )

    # Swap parameters
    slippage_tolerance: int = Field(
        default=50,
        description="Slippage tolerance in basis points (e.g., 50 = 0.5%)",
    )
    swap_type: SwapType = Field(
        default=SwapType.EXACT_INPUT,
        description="Type of swap - how to interpret amounts",
    )

    # Sender address
    sender: str = Field(description="Sender address on source chain")

    # Optional provider selection
    provider: SwapProvider | None = Field(
        default=None,
        description="Specific provider to use (None for automatic selection)",
    )


class SwapQuote(BaseModel):
    """Normalized swap quote response"""

    amount_in: str = Field(description="Input amount in smallest unit")
    amount_in_formatted: str = Field(description="Input amount in readable format")
    amount_in_usd: str | None = Field(default=None, description="Input amount in USD")

    amount_out: str = Field(description="Expected output amount in smallest unit")
    amount_out_formatted: str = Field(
        description="Expected output amount in readable format"
    )
    amount_out_usd: str | None = Field(
        default=None, description="Expected output amount in USD"
    )

    min_amount_out: str = Field(
        description="Minimum output amount after slippage in smallest unit"
    )

    estimated_time: int = Field(
        description="Estimated time for swap completion in seconds"
    )

    deposit_address: str | None = Field(
        default=None,
        description="Address to deposit funds (only provided for firm quotes)",
    )
    deposit_memo: str | None = Field(
        default=None,
        description="Memo required for deposit (if applicable, e.g., for Stellar)",
    )

    expires_at: datetime | None = Field(
        default=None,
        description="Expiration time for the quote/deposit address",
    )


class SwapQuoteResponse(BaseModel):
    """Provider-agnostic swap quote response"""

    provider: SwapProvider = Field(description="Provider that generated this quote")
    quote: SwapQuote = Field(description="The swap quote details")
    provider_metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional provider-specific metadata (signature, etc.)",
    )


class TransactionDetails(BaseModel):
    """Details of a blockchain transaction"""

    chain: str = Field(description="Chain identifier (coin.chain_id format)")
    hash: str = Field(description="Transaction hash")
    explorer_url: str | None = Field(
        default=None, description="Block explorer URL for this transaction"
    )
    status: str | None = Field(default=None, description="Transaction status")


class SwapDetails(BaseModel):
    """Detailed information about completed/in-progress swap"""

    amount_in: str | None = Field(
        default=None, description="Actual input amount in smallest unit"
    )
    amount_in_formatted: str | None = Field(
        default=None, description="Actual input amount in readable format"
    )
    amount_in_usd: str | None = Field(
        default=None, description="Actual input amount in USD"
    )

    amount_out: str | None = Field(
        default=None, description="Actual output amount in smallest unit"
    )
    amount_out_formatted: str | None = Field(
        default=None, description="Actual output amount in readable format"
    )
    amount_out_usd: str | None = Field(
        default=None, description="Actual output amount in USD"
    )

    refunded_amount: str | None = Field(
        default=None, description="Refunded amount in smallest unit (if any)"
    )
    refunded_amount_formatted: str | None = Field(
        default=None, description="Refunded amount in readable format"
    )

    fees: dict[str, str] | None = Field(
        default=None, description="Fees charged (if applicable)"
    )

    transactions: list[TransactionDetails] = Field(
        default_factory=list, description="All transactions involved in the swap"
    )


class SwapStatusResponse(BaseModel):
    """Provider-agnostic swap status response"""

    status: SwapStatus = Field(description="Current status of the swap")
    source_chain: str = Field(description="Source chain (coin.chain_id format)")
    dest_chain: str = Field(description="Destination chain (coin.chain_id format)")
    swap_details: SwapDetails | None = Field(
        default=None, description="Detailed swap information"
    )
    updated_at: datetime = Field(description="Last update timestamp")
    provider: SwapProvider = Field(description="Provider handling this swap")
    provider_metadata: dict[str, Any] | None = Field(
        default=None, description="Provider-specific metadata"
    )


class SubmitDepositRequest(BaseModel):
    """Request to submit deposit transaction hash"""

    tx_hash: str = Field(description="Transaction hash of the deposit")
    deposit_address: str = Field(description="Deposit address from the quote")
    deposit_memo: str | None = Field(
        default=None, description="Deposit memo (if applicable)"
    )
    sender_account: str | None = Field(
        default=None,
        description="Sender account identifier (provider-specific, e.g., NEAR account)",
    )
