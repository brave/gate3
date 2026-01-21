from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class SquidRouteRequest(BaseModel):
    """Request body for Squid /v2/route endpoint."""

    from_chain: str = Field(description="Source chain ID (decimal)")
    from_token: str = Field(description="Source token address")
    from_amount: str = Field(description="Amount to swap in smallest unit")
    to_chain: str = Field(description="Destination chain ID (decimal)")
    to_token: str = Field(description="Destination token address")
    to_address: str = Field(description="Recipient address on destination chain")
    slippage: float | None = Field(
        description="Slippage percentage as float (e.g., 1.0 = 1%) or None for auto slippage"
    )
    from_address: str = Field(description="Sender address on source chain")
    quote_only: bool = Field(
        default=False, description="Whether to return only the quote or the route"
    )

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SquidToken(BaseModel):
    """Minimal token information from Squid responses - only fields used in transformation."""

    symbol: str = Field(description="Token symbol")
    address: str = Field(description="Token address")
    chain_id: str = Field(description="Chain ID")
    decimals: int = Field(description="Token decimals")
    logo_uri: str | None = Field(
        default=None, description="Token logo URL", alias="logoURI"
    )

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SquidGasCost(BaseModel):
    """Gas cost information for a transaction."""

    type: str = Field(description="Gas cost type")
    token: SquidToken = Field(description="Token used for gas")
    amount: str = Field(description="Gas amount in smallest unit")
    gas_limit: str = Field(description="Gas limit")
    amount_usd: str | None = Field(default=None, description="USD value of gas cost")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SquidAction(BaseModel):
    """Minimal action information from Squid route - only fields used to create steps."""

    from_token: SquidToken = Field(description="Source token")
    to_token: SquidToken = Field(description="Destination token")
    from_amount: str = Field(description="Source amount in smallest unit")
    to_amount: str = Field(description="Destination amount in smallest unit")
    provider: str = Field(description="Provider/DEX name for this action")
    logo_uri: str | None = Field(
        default=None, description="Provider logo URL", alias="logoURI"
    )

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SquidEstimate(BaseModel):
    """Estimate data from Squid route response."""

    actions: list[SquidAction] = Field(
        default_factory=list, description="Actions/steps in the route"
    )
    from_amount: str = Field(description="Source amount in smallest unit")
    to_amount: str = Field(description="Destination amount in smallest unit")
    to_amount_min: str = Field(description="Minimum destination amount after slippage")
    estimated_route_duration: int = Field(
        description="Estimated route duration in seconds"
    )
    gas_costs: list[SquidGasCost] = Field(
        default_factory=list, description="Gas costs for the route"
    )
    aggregate_slippage: float = Field(
        description="Aggregate slippage percentage for the route"
    )
    aggregate_price_impact: str = Field(
        description="Aggregate price impact percentage for the route"
    )

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SquidTransactionRequest(BaseModel):
    """Transaction data from Squid route response."""

    target: str = Field(description="Target contract address (Squid router)")
    data: str = Field(description="Transaction calldata")
    value: str = Field(description="Transaction value in wei")
    gas_limit: str = Field(description="Gas limit for the transaction")
    gas_price: str | None = Field(default=None, description="Gas price in wei")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SquidRoute(BaseModel):
    """Route information from Squid route response."""

    estimate: SquidEstimate = Field(description="Estimate data for the route")
    transaction_request: SquidTransactionRequest | None = Field(
        default=None, description="Transaction request for the route"
    )
    quote_id: str | None = Field(default=None, description="Quote ID for the route")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SquidRouteResponse(BaseModel):
    """Response from Squid /v2/route endpoint."""

    route: SquidRoute = Field(description="Full route object with estimate and params")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SquidStatusRequest(BaseModel):
    """Request parameters for Squid /v2/status endpoint."""

    transaction_id: str = Field(description="Transaction hash")
    from_chain_id: str = Field(description="Source chain ID (decimal)")
    to_chain_id: str = Field(description="Destination chain ID (decimal)")
    quote_id: str | None = Field(default=None, description="Quote ID for tracking")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SquidStatusResponse(BaseModel):
    """Response from Squid /v2/status endpoint."""

    id: str = Field(description="Transaction or quote ID")
    status: str = Field(
        description="Status: success, ongoing, partial_success, needs_gas, not_found, refund"
    )
    squid_transaction_status: str | None = Field(
        default=None, description="Detailed transaction status"
    )

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SquidError(BaseModel):
    """Error response from Squid API."""

    message: str | None = Field(default=None, description="Error message")
    error: str | None = Field(default=None, description="Error type")
    errors: list[dict] | None = Field(default=None, description="List of errors")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
