from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from app.api.common.models import Chain, ChainSpec, Coin, TokenInfo
from app.api.common.utils import is_address_equal

# ============================================================================
# Base Models
# ============================================================================


class SwapBaseModel(BaseModel):
    """Base model with camelCase serialization for API responses and requests."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


# ============================================================================
# Error Handling
# ============================================================================
class SwapErrorKind(str, Enum):
    INSUFFICIENT_LIQUIDITY = "INSUFFICIENT_LIQUIDITY"
    CHAIN_NOT_SUPPORTED = "CHAIN_NOT_SUPPORTED"
    TOKEN_NOT_SUPPORTED = "TOKEN_NOT_SUPPORTED"
    INVALID_REQUEST = "INVALID_REQUEST"
    UNKNOWN = "UNKNOWN"


class SwapError(Exception):
    def __init__(
        self,
        message: str,
        kind: SwapErrorKind = SwapErrorKind.UNKNOWN,
        status_code: int = 400,
    ):
        self.message = message
        self.kind = kind
        self.status_code = status_code
        super().__init__(self.message)

    def as_dict(self) -> dict:
        return {"message": self.message, "kind": self.kind.value}


# ============================================================================
# Public Enums (Provider-Agnostic)
# ============================================================================


class SwapProviderEnum(str, Enum):
    AUTO = "AUTO"
    NEAR_INTENTS = "NEAR_INTENTS"
    ZERO_EX = "ZERO_EX"
    JUPITER = "JUPITER"
    LIFI = "LIFI"
    SQUID = "SQUID"

    def to_info(self) -> SwapProviderInfo:
        mapping = {
            SwapProviderEnum.AUTO: SwapProviderInfo(
                id=SwapProviderEnum.AUTO,
                name="Auto",
                logo=None,
            ),
            SwapProviderEnum.NEAR_INTENTS: SwapProviderInfo(
                id=SwapProviderEnum.NEAR_INTENTS,
                name="NEAR Intents",
                logo="https://static1.tokenterminal.com/near/products/nearintents/logo.png",
            ),
            SwapProviderEnum.ZERO_EX: SwapProviderInfo(
                id=SwapProviderEnum.ZERO_EX,
                name="0x",
                logo="https://static1.tokenterminal.com/0x/logo.png",
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
            SwapProviderEnum.SQUID: SwapProviderInfo(
                id=SwapProviderEnum.SQUID,
                name="Squid",
                logo="https://static1.tokenterminal.com/squid/logo.png",
            ),
        }

        if self not in mapping:
            raise ValueError(f"Unknown provider: {self}")

        return mapping[self]


class SwapProviderInfo(SwapBaseModel):
    id: SwapProviderEnum = Field(description="Provider identifier")
    name: str = Field(description="Provider display name")
    logo: str | None = Field(None, description="Provider logo URL")


class SwapType(str, Enum):
    EXACT_INPUT = "EXACT_INPUT"
    EXACT_OUTPUT = "EXACT_OUTPUT"


class RoutePriority(str, Enum):
    FASTEST = "FASTEST"
    CHEAPEST = "CHEAPEST"


class SwapStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


# ============================================================================
# Public Models (Provider-Agnostic Common Format)
# ============================================================================

# ============================================================================
# Request Models
# ============================================================================


class SwapSupportRequest(SwapBaseModel):
    source_coin: Coin = Field(description="Source coin type")
    source_chain_id: str = Field(description="Source chain ID")
    source_token_address: str | None = Field(
        default=None,
        description="Source token address (None for native)",
    )
    destination_coin: Coin = Field(description="Destination coin type")
    destination_chain_id: str = Field(description="Destination chain ID")
    destination_token_address: str | None = Field(
        default=None,
        description="Destination token address (None for native)",
    )
    recipient: str | None = Field(
        default=None,
        description="Recipient address on destination chain",
    )

    _source_token: TokenInfo | None = None
    _destination_token: TokenInfo | None = None

    @field_validator(
        "source_token_address",
        "destination_token_address",
        "recipient",
        mode="before",
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
                and is_address_equal(token.address, self.source_token_address)
            ):
                self._source_token = token
                break

    def set_destination_token(self, tokens: list[TokenInfo]) -> None:
        for token in tokens:
            if (
                token.coin == self.destination_coin
                and token.chain_id == self.destination_chain_id
                and is_address_equal(token.address, self.destination_token_address)
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
    slippage_percentage: str | None = Field(
        default=None,
        description="Slippage tolerance as a percentage string (e.g., '0.5' = 0.5%). If not specified, the provider will automatically determine the slippage tolerance.",
    )
    swap_type: SwapType = Field(
        default=SwapType.EXACT_INPUT,
        description="Type of swap - how to interpret amounts",
    )

    # Refund address
    refund_to: str = Field(description="Refund address on source chain if swap fails")

    # Optional provider selection
    provider: SwapProviderEnum | None = Field(
        default=None,
        description="Specific provider to use (None for automatic selection)",
    )

    # Route priority for sorting
    route_priority: RoutePriority = Field(
        default=RoutePriority.CHEAPEST,
        description=(
            "Priority for sorting routes. "
            "CHEAPEST: best rate first (highest output for EXACT_INPUT, lowest input for EXACT_OUTPUT). "
            "FASTEST: lowest estimated time first. Ties are broken by the other priority."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    # SwapSupportRequest params
                    "sourceCoin": Chain.ARBITRUM.coin,
                    "sourceChainId": Chain.ARBITRUM.chain_id,
                    "sourceTokenAddress": None,
                    "destinationCoin": Chain.SOLANA.coin,
                    "destinationChainId": Chain.SOLANA.chain_id,
                    "destinationTokenAddress": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC on SOLANA
                    "recipient": "8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
                    # SwapQuoteRequest params
                    "amount": "10000000000000000",  # 0.01 ETH on ARBITRUM
                    "swapType": SwapType.EXACT_INPUT,
                    "routePriority": RoutePriority.CHEAPEST,
                    "provider": SwapProviderEnum.AUTO,
                    "refundTo": "0xa92D461a9a988A7f11ec285d39783A637Fdd6ba4",
                }
            ]
        }
    )


class SwapStatusRequest(SwapBaseModel):
    route_id: str = Field(
        description="Unique route identifier",
    )
    tx_hash: str = Field(description="Transaction hash of the swap")
    source_coin: Coin = Field(description="Source coin of the swap")
    source_chain_id: str = Field(description="Source chain ID of the swap")
    destination_coin: Coin = Field(description="Destination coin of the swap")
    destination_chain_id: str = Field(description="Destination chain ID of the swap")

    deposit_address: str = Field(description="Deposit address of the swap")
    deposit_memo: str | None = Field(
        default=None,
        description="Deposit memo of the swap (if applicable)",
    )
    provider: SwapProviderEnum = Field(description="Provider that generated the quote")


# ============================================================================
# Response Models
# ============================================================================


class NetworkFee(SwapBaseModel):
    """Network fee information for a transaction."""

    amount: str = Field(description="Fee amount in smallest unit (wei, lamports, etc.)")
    decimals: int = Field(description="Decimals for the fee token")
    symbol: str = Field(description="Symbol of the fee token (e.g., 'ETH', 'SOL')")


class EvmTransactionParams(SwapBaseModel):
    chain: ChainSpec
    from_address: str = Field(alias="from")
    to: str
    value: str
    data: str

    # Gas fee parameters
    gas_limit: str = Field(
        description="Gas limit for the transaction",
    )
    gas_price: str | None = Field(
        default=None,
        description="Gas price in wei",
    )


class SolanaTransactionParams(SwapBaseModel):
    chain: ChainSpec
    from_address: str = Field(alias="from")
    to: str

    # Common field for both system and SPL transfers. It is recommended to use
    # lamports alias for system transfers, otherwise use value for SPL transfers
    value: str = Field(alias="lamports")

    # For SPL transfers only
    spl_token_mint: str | None = Field(default=None)
    spl_token_amount: str | None = Field(default=None)
    decimals: int | None = Field(default=None)  # Needed for TransferChecked instruction

    # Pre-built versioned transaction (base64-encoded)
    versioned_transaction: str | None = Field(
        default=None,
        description="Base64-encoded versioned transaction for signing",
    )

    # Priority fee parameters (optional)
    compute_unit_limit: str | None = Field(
        default=None,
        description="Compute unit limit for the transaction",
    )
    compute_unit_price: str | None = Field(
        default=None,
        description="Priority fee in micro-lamports per compute unit",
    )


class UtxoChainTransactionParams(SwapBaseModel):
    chain: ChainSpec
    to: str
    value: str
    refund_to: str


class BitcoinTransactionParams(UtxoChainTransactionParams):
    pass


class CardanoTransactionParams(UtxoChainTransactionParams):
    pass


class ZcashTransactionParams(UtxoChainTransactionParams):
    pass


class TransactionParams(SwapBaseModel):
    evm: EvmTransactionParams | None = Field(default=None)
    solana: SolanaTransactionParams | None = Field(default=None)
    bitcoin: BitcoinTransactionParams | None = Field(default=None)
    cardano: CardanoTransactionParams | None = Field(default=None)
    zcash: ZcashTransactionParams | None = Field(default=None)

    @model_validator(mode="after")
    def only_one_field_not_none(self):
        field_names = list(TransactionParams.model_fields.keys())
        not_none_fields = [
            name for name in field_names if getattr(self, name) is not None
        ]
        if len(not_none_fields) != 1:
            raise ValueError(f"Exactly one of {field_names!r} must be not None")
        return self


# ============================================================================
# Route / Step Models
# ============================================================================


class SwapStepToken(SwapBaseModel):
    """Token info for swap step source/destination."""

    coin: Coin = Field(description="Coin type (ETH, SOL, BTC, etc.)")
    chain_id: str = Field(description="Chain ID")
    contract_address: str | None = Field(
        default=None,
        description="Token contract address (None for native)",
    )
    symbol: str = Field(description="Token symbol (e.g., 'USDC', 'ETH')")
    decimals: int = Field(description="Token decimals")
    logo: str | None = Field(default=None, description="Token logo URL")


class SwapTool(SwapBaseModel):
    """DEX/protocol used for a swap step."""

    name: str = Field(description="Display name (e.g., 'Uniswap', 'Jupiter')")
    logo: str | None = Field(default=None, description="Logo URL")


class SwapRouteStep(SwapBaseModel):
    """A single hop in a multi-hop swap route."""

    source_token: SwapStepToken = Field(description="Source token info")
    source_amount: str = Field(description="Amount in smallest unit")

    destination_token: SwapStepToken = Field(description="Destination token info")
    destination_amount: str = Field(description="Amount in smallest unit")

    percent: float | None = Field(
        default=None, description="Percentage of the swap step"
    )
    tool: SwapTool = Field(description="DEX/protocol used for this step")


class SwapRoute(SwapBaseModel):
    """A complete swap route with one or more steps."""

    id: str = Field(description="Unique route identifier")
    provider: SwapProviderEnum = Field(description="Provider for this route")

    steps: list[SwapRouteStep] = Field(
        description="Ordered list of hops in this route",
    )

    source_amount: str = Field(
        description=(
            "Total source amount in smallest unit. For EXACT_OUTPUT, this is minimum amount required to proceed with the swap."
        )
    )
    destination_amount: str = Field(
        description="Total destination amount in smallest unit"
    )
    destination_amount_min: str = Field(
        description="Minimum destination amount after slippage in smallest unit",
    )

    estimated_time: int | None = Field(
        default=None,
        description="Total estimated time in seconds (0 indicates an atomic swap)",
    )
    price_impact: float | None = Field(
        default=None,
        description="Price impact percentage",
    )
    network_fee: NetworkFee | None = Field(
        default=None,
        description=(
            "Total estimated network fee for the swap route. "
            "None indicates that network fees could not be fetched or computed."
        ),
    )
    gasless: bool = Field(
        default=False,
        description="Whether this route operates in gasless mode (network fees are sponsored/waived)",
    )

    # Fields typically only provided for firm quotes (with few exceptions)
    deposit_address: str | None = Field(
        default=None,
        description="Address to deposit funds (only provided for firm quotes)",
    )
    deposit_memo: str | None = Field(
        default=None,
        description="Memo required for deposit (if applicable, e.g., for Stellar)",
    )
    expires_at: str | None = Field(
        default=None,
        description="Expiration time for the quote/deposit address as Unix timestamp",
    )
    transaction_params: TransactionParams | None = Field(
        default=None,
        description="Transaction parameters for the swap",
    )

    # Provider-specific requirements
    requires_token_allowance: bool = Field(
        description="Whether client must check/approve token allowance before swap (EVM only)",
    )
    requires_firm_route: bool = Field(
        description="Whether client must fetch a firm route before executing the swap",
    )
    slippage_percentage: str = Field(
        description="Slippage tolerance as a percentage string (e.g., '0.5' = 0.5%) used for this route",
    )


class SwapQuote(SwapBaseModel):
    """Response containing multiple route options."""

    routes: list[SwapRoute] = Field(description="Available swap routes")


class SwapStatusResponse(SwapBaseModel):
    status: SwapStatus = Field(description="Current status of the swap")
    internal_status: str | None = Field(
        default=None,
        description="Provider-specific status of the swap",
    )
    explorer_url: str | None = Field(
        default=None,
        description="Block explorer URL for the swap transaction",
    )
