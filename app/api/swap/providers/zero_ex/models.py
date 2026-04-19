from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _ZeroExBaseModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )


class ZeroExFill(_ZeroExBaseModel):
    """A single DEX venue used to fill the swap (parallel, not hops)."""

    source: str = Field(description="Liquidity source name (e.g., 'Uniswap_V3')")
    proportion_bps: int = Field(
        default=10000,
        description="Proportion of the swap filled via this source, in basis points",
    )


class ZeroExRoute(_ZeroExBaseModel):
    """Routing information for the swap."""

    fills: list[ZeroExFill] = Field(default_factory=list)


class ZeroExAllowanceIssue(_ZeroExBaseModel):
    spender: str = Field(description="Address that needs to be approved")


class ZeroExIssues(_ZeroExBaseModel):
    allowance: ZeroExAllowanceIssue | None = Field(default=None)


class ZeroExTransaction(_ZeroExBaseModel):
    to: str = Field(description="Contract to send the swap transaction to")
    data: str = Field(description="Hex-encoded calldata")
    value: str = Field(default="0", description="Native value to send (wei, decimal)")
    gas: str | None = Field(default=None, description="Estimated gas limit (decimal)")
    gas_price: str | None = Field(
        default=None, description="Gas price in wei (decimal)"
    )


class ZeroExQuoteResponse(_ZeroExBaseModel):
    """Response from /swap/allowance-holder/quote."""

    sell_token: str = Field(description="Address of the sold token")
    buy_token: str = Field(description="Address of the bought token")
    sell_amount: str = Field(description="Amount of sellToken being sold (decimal)")
    buy_amount: str = Field(description="Amount of buyToken expected (decimal)")
    min_buy_amount: str = Field(
        description="Minimum buyToken after slippage (decimal)",
    )
    total_network_fee: str | None = Field(
        default=None,
        description="Total estimated network fee in wei (decimal)",
    )
    gas: str | None = Field(default=None, description="Estimated gas limit")
    gas_price: str | None = Field(default=None, description="Gas price in wei")
    route: ZeroExRoute = Field(default_factory=ZeroExRoute)
    issues: ZeroExIssues | None = Field(default=None)
    transaction: ZeroExTransaction = Field(description="Transaction data to submit")


class ZeroExError(_ZeroExBaseModel):
    """0x v2 API error payload."""

    name: str | None = Field(default=None, description="Error name")
    message: str = Field(description="Human-readable error message")
