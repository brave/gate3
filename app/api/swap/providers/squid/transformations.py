from app.api.common.amount import Amount
from app.api.common.models import Coin
from app.api.tokens.manager import TokenManager

from ...models import (
    EvmTransactionParams,
    NetworkFee,
    SwapProviderEnum,
    SwapQuoteRequest,
    SwapRoute,
    SwapRouteStep,
    SwapStatus,
    SwapStatusRequest,
    SwapStatusResponse,
    SwapStepToken,
    SwapTool,
    TransactionParams,
)
from .models import SquidAction, SquidRouteResponse, SquidStatusResponse, SquidToken
from .utils import (
    convert_squid_token_address,
    generate_route_id,
    get_chain_from_squid_chain_id,
)


def _squid_token_to_step_token(squid_token: SquidToken) -> SwapStepToken:
    """Convert SquidToken to SwapStepToken for route steps.

    Args:
        squid_token: Squid token object from action

    Returns:
        SwapStepToken for use in route steps
    """
    chain = get_chain_from_squid_chain_id(squid_token.chain_id)

    return SwapStepToken(
        coin=chain.coin,
        chain_id=chain.chain_id,
        contract_address=convert_squid_token_address(chain, squid_token.address),
        symbol=squid_token.symbol,
        decimals=squid_token.decimals,
        logo=squid_token.logo_uri,
    )


def _convert_actions_to_steps(actions: list[SquidAction]) -> list[SwapRouteStep]:
    """Convert Squid actions to SwapRouteStep objects.

    Args:
        actions: List of actions from Squid estimate

    Returns:
        List of SwapRouteStep objects
    """
    steps = []

    for action in actions:
        # Create tool info from action provider and logo
        tool = SwapTool(
            name=action.provider,
            logo=action.logo_uri,
        )

        step = SwapRouteStep(
            source_token=_squid_token_to_step_token(action.from_token),
            source_amount=action.from_amount,
            destination_token=_squid_token_to_step_token(action.to_token),
            destination_amount=action.to_amount,
            tool=tool,
            percent=100,
        )
        steps.append(step)

    return steps


def _build_transaction_params(
    squid_response: SquidRouteResponse,
    request: SwapQuoteRequest,
) -> TransactionParams | None:
    """Build transaction parameters from Squid route response.

    Args:
        squid_response: The Squid route response
        request: The original swap quote request

    Returns:
        TransactionParams if transaction is available, None otherwise
    """
    tx_request = squid_response.route.transaction_request
    if not tx_request:
        return None

    source_chain = request.source_chain
    if not source_chain:
        return None

    if source_chain.coin == Coin.ETH:
        return TransactionParams(
            evm=EvmTransactionParams(
                chain=source_chain.to_spec(),
                from_address=request.refund_to,
                to=tx_request.target,
                value=tx_request.value,
                data=tx_request.data,
                gas_limit=tx_request.gas_limit,
                gas_price=tx_request.gas_price,
            ),
        )

    return None


def _compute_network_fee(
    squid_response: SquidRouteResponse,
    request: SwapQuoteRequest,
) -> NetworkFee | None:
    """Compute network fee from Squid gas costs and transaction value.

    Includes:
    - Gas costs for the source chain
    - Transaction value fees:
      - For native asset source: excess value over source_amount (bridge fees)
      - For ERC20 source: entire transaction value (since token is via approval)

    Args:
        squid_response: The Squid route response
        request: The original swap quote request

    Returns:
        NetworkFee if fees are present, None otherwise
    """
    source_chain = request.source_chain
    if not source_chain:
        return None

    estimate = squid_response.route.estimate
    total_fee = Amount.zero()

    # Sum gas costs for source chain only
    if estimate.gas_costs:
        for gas_cost in estimate.gas_costs:
            # Check if this gas cost is for the source chain
            token = gas_cost.token
            if get_chain_from_squid_chain_id(token.chain_id) == source_chain:
                total_fee += Amount(gas_cost.amount)

    # Add transaction value as network fee
    # - For native asset source: only the excess over source_amount is fee
    #   (since source_amount is also sent in value)
    # - For ERC20 source: entire value is fee (token transferred via approval)
    tx_request = squid_response.route.transaction_request
    if tx_request and source_chain.coin == Coin.ETH:
        tx_value = Amount(tx_request.value)
        if tx_value.is_positive():
            if request.source_token_address is None:
                # Native asset: only excess is fee
                source_amount = Amount(estimate.from_amount)
                if tx_value > source_amount:
                    total_fee += tx_value - source_amount
            else:
                # ERC20: entire value is fee
                total_fee += tx_value

    if total_fee.is_undefined() or total_fee.is_zero():
        return None

    return NetworkFee(
        amount=str(total_fee),
        decimals=source_chain.decimals,
        symbol=source_chain.symbol,
    )


def normalize_squid_status(squid_status: str) -> SwapStatus:
    """Map Squid status values to SwapStatus.

    Args:
        squid_status: Status string from Squid API

    Returns:
        Normalized SwapStatus enum value
    """
    status_lower = squid_status.lower()

    if status_lower == "success":
        return SwapStatus.SUCCESS
    elif status_lower in ("ongoing", "partial_success"):
        return SwapStatus.PROCESSING
    elif status_lower in ("needs_gas", "not_found"):
        return SwapStatus.PENDING
    elif status_lower == "refund":
        return SwapStatus.REFUNDED

    return SwapStatus.PENDING


def from_squid_status(
    squid_response: SquidStatusResponse, request: SwapStatusRequest
) -> SwapStatusResponse:
    """Convert Squid status response to SwapStatusResponse.

    Args:
        squid_response: The Squid status response
        request: The original swap status request
    Returns:
        SwapStatusResponse with normalized status
    """
    return SwapStatusResponse(
        status=normalize_squid_status(squid_response.status),
        internal_status=squid_response.squid_transaction_status,
        explorer_url=f"https://axelarscan.io/gmp/{request.tx_hash}",
    )


async def from_squid_route_to_route(
    squid_response: SquidRouteResponse,
    request: SwapQuoteRequest,
    token_manager: TokenManager,
) -> SwapRoute:
    """Convert Squid route response to SwapRoute.

    Args:
        squid_response: The Squid route response
        request: The original swap quote request
        token_manager: TokenManager instance for token lookup (unused, kept for signature compatibility)

    Returns:
        SwapRoute with all steps and details

    Raises:
        ValueError: If actions are missing from the estimate
    """
    estimate = squid_response.route.estimate

    # Convert actions to steps
    if not estimate.actions:
        raise ValueError("Squid route response missing actions in estimate")

    steps = _convert_actions_to_steps(estimate.actions)

    # Compute network fee (gas costs + any native asset bridge fees)
    network_fee = _compute_network_fee(squid_response, request)

    # Build transaction params
    transaction_params = _build_transaction_params(squid_response, request)

    # Get deposit address (target contract for ERC20 approval)
    deposit_address = None
    tx_request = squid_response.route.transaction_request
    if tx_request:
        deposit_address = tx_request.target

    # Convert aggregate price impact from string to float
    try:
        price_impact = float(estimate.aggregate_price_impact)
    except (ValueError, TypeError):
        price_impact = None

    # Use provider's quote_id as id, or generate one if not available
    route_id = squid_response.route.quote_id or generate_route_id()

    return SwapRoute(
        provider=SwapProviderEnum.SQUID,
        steps=steps,
        source_amount=estimate.from_amount,
        destination_amount=estimate.to_amount,
        destination_amount_min=estimate.to_amount_min,
        estimated_time=estimate.estimated_route_duration,
        price_impact=price_impact,
        network_fee=network_fee,
        deposit_address=deposit_address,
        transaction_params=transaction_params,
        requires_token_allowance=True,  # ERC20 tokens need approval
        requires_firm_route=False,  # Squid returns transaction in route response
        slippage_percentage=str(estimate.aggregate_slippage),
        id=route_id,
    )
