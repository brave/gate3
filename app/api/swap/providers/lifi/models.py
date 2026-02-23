from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class LifiQuoteRequest(BaseModel):
    """Request parameters for LI.FI /v1/quote GET endpoint."""

    from_chain: int = Field(description="Source chain ID (decimal)")
    to_chain: int = Field(description="Destination chain ID (decimal)")
    from_token: str = Field(description="Source token address")
    to_token: str = Field(description="Destination token address")
    from_amount: str = Field(description="Amount in smallest unit")
    from_address: str = Field(description="Sender address")
    to_address: str | None = Field(
        default=None, description="Recipient address on destination chain"
    )
    slippage: float | None = Field(
        default=None, description="Slippage as decimal (0.005 = 0.5%)"
    )
    order: str | None = Field(
        default=None, description="Route preference: FASTEST or CHEAPEST"
    )
    integrator: str | None = Field(default=None, description="Integrator identifier")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LifiToken(BaseModel):
    address: str = Field(description="Token address")
    chain_id: int = Field(description="Chain ID (decimal)")
    symbol: str = Field(description="Token symbol")
    decimals: int = Field(description="Token decimals")
    name: str = Field(default="", description="Token name")
    logo_uri: str | None = Field(
        default=None, description="Token logo URL", alias="logoURI"
    )

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )


class LifiTokensResponse(BaseModel):
    tokens: dict[str, list[LifiToken]]


class LifiGasCost(BaseModel):
    amount: str = Field(description="Gas amount in smallest unit")
    token: LifiToken = Field(description="Token used for gas")

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )


class LifiToolDetails(BaseModel):
    name: str = Field(description="Tool display name")
    logo_uri: str | None = Field(
        default=None, description="Tool logo URL", alias="logoURI"
    )

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )


class LifiAction(BaseModel):
    from_token: LifiToken = Field(description="Source token")
    to_token: LifiToken = Field(description="Destination token")
    from_amount: str = Field(description="Source amount in smallest unit")
    slippage: float = Field(description="Slippage as decimal")

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )


class LifiEstimate(BaseModel):
    approval_address: str | None = Field(
        default=None, description="Spender address for ERC20 approval"
    )
    to_amount: str = Field(description="Destination amount in smallest unit")
    to_amount_min: str = Field(description="Minimum destination amount after slippage")
    from_amount: str = Field(description="Source amount in smallest unit")
    gas_costs: list[LifiGasCost] = Field(default_factory=list, description="Gas costs")
    execution_duration: float = Field(
        description="Estimated execution duration in seconds"
    )

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )


class LifiStep(BaseModel):
    tool_details: LifiToolDetails = Field(description="Tool display info")
    action: LifiAction = Field(description="Action details")
    estimate: LifiEstimate = Field(description="Estimate for this step")

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )


class LifiTransactionRequest(BaseModel):
    from_address: str | None = Field(
        default=None, description="Sender address", alias="from"
    )
    to: str | None = Field(default=None, description="Contract/vault address")
    data: str = Field(
        description="EVM: hex calldata, Solana: base64 versioned tx, Bitcoin: memo"
    )
    value: str | None = Field(
        default=None, description="EVM: wei hex, Bitcoin: satoshis"
    )
    gas_price: str | None = Field(default=None, description="Gas price (hex)")
    gas_limit: str | None = Field(default=None, description="Gas limit (hex)")

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )


class LifiQuoteResponse(BaseModel):
    id: str = Field(description="Quote identifier")
    tool_details: LifiToolDetails = Field(description="Tool display info")
    action: LifiAction = Field(description="Top-level action")
    estimate: LifiEstimate = Field(description="Top-level estimate")
    included_steps: list[LifiStep] = Field(
        default_factory=list, description="Detailed sub-steps"
    )
    transaction_request: LifiTransactionRequest | None = Field(
        default=None, description="Transaction data for execution"
    )

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )


class LifiStatusRequest(BaseModel):
    tx_hash: str = Field(description="Transaction hash")
    from_chain: int | None = Field(
        default=None, description="Source chain ID (decimal)"
    )
    to_chain: int | None = Field(
        default=None, description="Destination chain ID (decimal)"
    )

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LifiStatusResponse(BaseModel):
    status: str = Field(description="Status: DONE, PENDING, NOT_FOUND, FAILED")
    substatus: str | None = Field(
        default=None,
        description="Substatus: COMPLETED, PARTIAL, REFUNDED, etc.",
    )
    lifi_explorer_link: str | None = Field(
        default=None, description="LI.FI explorer link"
    )

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )


class LifiError(BaseModel):
    message: str = Field(description="Error message")
    errors: list[dict] | None = Field(default=None, description="Detailed errors")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
