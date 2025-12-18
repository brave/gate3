from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from app.api.common.models import Chain, Coin, TokenInfo

# ============================================================================
# Public Enums (Provider-Agnostic)
# ============================================================================


class SwapProviderEnum(str, Enum):
    AUTO = "AUTO"
    NEAR_INTENTS = "NEAR_INTENTS"
    ZERO_EX = "ZERO_EX"
    JUPITER = "JUPITER"
    LIFI = "LIFI"

    def to_info(self) -> "SwapProviderInfo":
        mapping = {
            SwapProviderEnum.AUTO: SwapProviderInfo(
                id=SwapProviderEnum.AUTO, name="Auto", logo=None
            ),
            SwapProviderEnum.NEAR_INTENTS: SwapProviderInfo(
                id=SwapProviderEnum.NEAR_INTENTS,
                name="NEAR Intents",
                logo="https://static1.tokenterminal.com//near/products/nearintents/logo.png",
            ),
            SwapProviderEnum.ZERO_EX: SwapProviderInfo(
                id=SwapProviderEnum.ZERO_EX,
                name="0x",
                logo="https://static1.tokenterminal.com//0x/logo.png",
            ),
            SwapProviderEnum.JUPITER: SwapProviderInfo(
                id=SwapProviderEnum.JUPITER,
                name="Jupiter",
                logo="https://static1.tokenterminal.com/jupiter/logo.png",
            ),
            SwapProviderEnum.LIFI: SwapProviderInfo(
                id=SwapProviderEnum.LIFI,
                name="LI.FI",
                logo="https://static1.tokenterminal.com/lifi/logo.png",
            ),
        }

        if self not in mapping:
            raise ValueError(f"Unknown provider: {self}")

        return mapping[self]


class SwapProviderInfo(BaseModel):
    id: SwapProviderEnum = Field(description="Provider identifier")
    name: str = Field(description="Provider display name")
    logo: str | None = Field(None, description="Provider logo URL")


class SwapType(str, Enum):
    EXACT_INPUT = "EXACT_INPUT"
    EXACT_OUTPUT = "EXACT_OUTPUT"


class SwapStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


# ============================================================================
# Public Models (Provider-Agnostic Common Format)
# ============================================================================


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

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    _source_token: TokenInfo | None = None
    _destination_token: TokenInfo | None = None

    @field_validator(
        "source_token_address", "destination_token_address", "recipient", mode="before"
    )
    @classmethod
    def empty_string_to_none(cls, v: str | None) -> str | None:
        return None if v == "" else v

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
    slippage_percentage: str = Field(
        default="0.5",
        description="Slippage tolerance as a percentage string (e.g., '0.5' = 0.5%)",
    )
    swap_type: SwapType = Field(
        default=SwapType.EXACT_INPUT,
        description="Type of swap - how to interpret amounts",
    )

    # Sender address
    sender: str = Field(description="Sender address on source chain")

    # Optional provider selection
    provider: SwapProviderEnum | None = Field(
        default=None,
        description="Specific provider to use (None for automatic selection)",
    )


class SwapQuote(BaseModel):
    provider: SwapProviderEnum = Field(description="Provider that generated this quote")

    source_amount: str = Field(description="Source amount in smallest unit")

    destination_amount: str = Field(description="Destination amount in smallest unit")

    destination_amount_min: str = Field(
        description="Minimum destination amount after slippage in smallest unit"
    )

    estimated_time: int | None = Field(
        default=None, description="Estimated time for swap completion in seconds"
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

    price_impact: float | None = Field(
        default=None,
        description="Price impact percentage (negative value indicates loss due to slippage/fees)",
    )


class SwapTransactionDetails(BaseModel):
    coin: Coin = Field(description="Coin identifier")
    chain_id: str = Field(description="Chain identifier")
    hash: str = Field(description="Transaction hash")
    explorer_url: str | None = Field(
        default=None, description="Block explorer URL for this transaction"
    )

    @property
    def chain(self) -> Chain | None:
        return Chain.get(self.coin, self.chain_id)


class SwapDetails(BaseModel):
    amount_in: str | None = Field(
        default=None, description="Actual input amount in smallest unit"
    )
    amount_in_formatted: str | None = Field(
        default=None, description="Actual input amount in readable format"
    )

    amount_out: str | None = Field(
        default=None, description="Actual output amount in smallest unit"
    )
    amount_out_formatted: str | None = Field(
        default=None, description="Actual output amount in readable format"
    )

    refunded_amount: str | None = Field(
        default=None, description="Refunded amount in smallest unit (if any)"
    )
    refunded_amount_formatted: str | None = Field(
        default=None, description="Refunded amount in readable format"
    )

    transactions: list[SwapTransactionDetails] = Field(
        default_factory=list, description="All transactions involved in the swap"
    )


class SwapStatusResponse(SwapSupportRequest):
    status: SwapStatus = Field(description="Current status of the swap")
    swap_details: SwapDetails | None = Field(
        default=None, description="Detailed swap information"
    )
    provider: SwapProviderEnum = Field(description="Provider handling this swap")
    explorer_url: str | None = Field(
        default=None,
        description="Block explorer URL for the swap transaction",
    )


class SwapStatusRequest(BaseModel):
    tx_hash: str = Field(description="Transaction hash of the swap")
    deposit_address: str = Field(description="Deposit address of the swap")
    deposit_memo: str | None = Field(
        default=None, description="Deposit memo of the swap (if applicable)"
    )
    provider: SwapProviderEnum = Field(description="Provider that generated the quote")
