from enum import Enum

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class JupiterSwapMode(str, Enum):
    EXACT_IN = "ExactIn"
    EXACT_OUT = "ExactOut"


class JupiterOrderRequest(BaseModel):
    """Request parameters for Jupiter Ultra V3 /ultra/v1/order endpoint."""

    input_mint: str
    output_mint: str
    amount: str
    taker: str
    receiver: str | None = None
    swap_mode: JupiterSwapMode

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class JupiterSwapInfo(BaseModel):
    """Swap information for a single hop in the route."""

    label: str
    input_mint: str
    output_mint: str
    in_amount: str
    out_amount: str

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class JupiterRoutePlan(BaseModel):
    """A single hop in the Jupiter route."""

    percent: int
    swap_info: JupiterSwapInfo

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class JupiterOrderResponse(BaseModel):
    """Response from Jupiter Ultra V3 /ultra/v1/order endpoint."""

    in_amount: str
    out_amount: str
    other_amount_threshold: str
    swap_mode: JupiterSwapMode
    slippage_bps: int
    price_impact: str
    route_plan: list[JupiterRoutePlan]
    fee_mint: str
    fee_bps: int
    taker: str
    gasless: bool
    signature_fee_lamports: int
    signature_fee_payer: str | None = None
    prioritization_fee_lamports: int
    prioritization_fee_payer: str | None = None
    transaction: str  # Base64-encoded versioned transaction
    error_code: int | None = None
    error_message: str | None = None
    input_mint: str
    output_mint: str
    router: str
    request_id: str
    mode: str  # For example: "ultra"
    error: str | None = None
    total_time: int | None = None
    expire_at: str  # Unix timestamp
    request_id: str  # Required for Jupiter Ultra V3 POST /execute endpoint

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class JupiterError(BaseModel):
    error: str | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
