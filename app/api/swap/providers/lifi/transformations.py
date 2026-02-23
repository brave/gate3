from app.api.common.amount import Amount
from app.api.common.models import Coin

from ...models import (
    BitcoinTransactionParams,
    EvmTransactionParams,
    NetworkFee,
    SolanaTransactionParams,
    SwapError,
    SwapErrorKind,
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
from .models import LifiQuoteResponse, LifiStatusResponse, LifiStep, LifiToken
from .utils import (
    convert_lifi_token_address,
    generate_route_id,
    get_chain_from_lifi_chain_id,
)


def _lifi_token_to_step_token(token: LifiToken) -> SwapStepToken:
    chain = get_chain_from_lifi_chain_id(token.chain_id)
    if not chain:
        raise SwapError(
            message=f"Unsupported LI.FI chain ID: {token.chain_id}",
            kind=SwapErrorKind.UNSUPPORTED_NETWORK,
        )
    return SwapStepToken(
        coin=chain.coin,
        chain_id=chain.chain_id,
        contract_address=convert_lifi_token_address(chain, token.address),
        symbol=token.symbol,
        decimals=token.decimals,
        logo=token.logo_uri,
    )


def _convert_steps_to_route_steps(steps: list[LifiStep]) -> list[SwapRouteStep]:
    route_steps = []
    for step in steps:
        tool = SwapTool(
            name=step.tool_details.name,
            logo=step.tool_details.logo_uri,
        )
        route_step = SwapRouteStep(
            source_token=_lifi_token_to_step_token(step.action.from_token),
            source_amount=step.action.from_amount,
            destination_token=_lifi_token_to_step_token(step.action.to_token),
            destination_amount=step.estimate.to_amount,
            tool=tool,
            percent=100,
        )
        route_steps.append(route_step)
    return route_steps


def _build_transaction_params(
    response: LifiQuoteResponse,
    request: SwapQuoteRequest,
) -> TransactionParams | None:
    tx_request = response.transaction_request
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
                to=tx_request.to or "",
                value=tx_request.value or "0",
                data=tx_request.data,
                gas_limit=tx_request.gas_limit or "0",
                gas_price=tx_request.gas_price,
            ),
        )

    if source_chain.coin == Coin.SOL:
        return TransactionParams(
            solana=SolanaTransactionParams(
                chain=source_chain.to_spec(),
                from_address=request.refund_to,
                to="0",
                value="0",
                versioned_transaction=tx_request.data,
            ),
        )

    if source_chain.coin == Coin.BTC:
        return TransactionParams(
            bitcoin=BitcoinTransactionParams(
                chain=source_chain.to_spec(),
                to=tx_request.to or "",
                value=tx_request.value or "0",
                refund_to=request.refund_to,
            ),
        )

    return None


def _compute_network_fee(
    response: LifiQuoteResponse,
    request: SwapQuoteRequest,
) -> NetworkFee | None:
    source_chain = request.source_chain
    if not source_chain:
        return None

    estimate = response.estimate
    total_fee = Amount.zero()

    # Sum gas costs for source chain
    if estimate.gas_costs:
        for gas_cost in estimate.gas_costs:
            token = gas_cost.token
            if get_chain_from_lifi_chain_id(token.chain_id) == source_chain:
                total_fee += Amount(gas_cost.amount)

    # Add transaction value as network fee (same pattern as Squid)
    tx_request = response.transaction_request
    if tx_request and source_chain.coin == Coin.ETH:
        tx_value = Amount(tx_request.value)
        if tx_value.is_positive():
            if request.source_token_address is None:
                # Native asset: only excess over source amount is fee
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


def normalize_lifi_status(status: str, substatus: str | None) -> SwapStatus:
    """Map LI.FI status/substatus to SwapStatus."""
    status_upper = status.upper()

    if status_upper == "DONE":
        if substatus and substatus.upper() == "REFUNDED":
            return SwapStatus.REFUNDED
        return SwapStatus.SUCCESS

    if status_upper == "PENDING":
        return SwapStatus.PROCESSING

    if status_upper == "NOT_FOUND":
        return SwapStatus.PENDING

    if status_upper == "FAILED":
        return SwapStatus.FAILED

    return SwapStatus.PENDING


def from_lifi_status(
    response: LifiStatusResponse,
    request: SwapStatusRequest,
) -> SwapStatusResponse:
    return SwapStatusResponse(
        status=normalize_lifi_status(response.status, response.substatus),
        internal_status=response.substatus,
        explorer_url=response.lifi_explorer_link,
    )


async def from_lifi_quote_to_route(
    response: LifiQuoteResponse,
    request: SwapQuoteRequest,
) -> SwapRoute:
    # Build steps from includedSteps, fallback to top-level action
    if response.included_steps:
        steps = _convert_steps_to_route_steps(response.included_steps)
    else:
        # Single step from top-level action
        tool = SwapTool(
            name=response.tool_details.name,
            logo=response.tool_details.logo_uri,
        )
        step = SwapRouteStep(
            source_token=_lifi_token_to_step_token(response.action.from_token),
            source_amount=response.action.from_amount,
            destination_token=_lifi_token_to_step_token(response.action.to_token),
            destination_amount=response.estimate.to_amount,
            tool=tool,
            percent=100,
        )
        steps = [step]

    network_fee = _compute_network_fee(response, request)
    transaction_params = _build_transaction_params(response, request)

    # Deposit address is the approval address for ERC20 tokens
    deposit_address = response.estimate.approval_address
    if not deposit_address and response.transaction_request:
        deposit_address = response.transaction_request.to

    # Deposit memo for Bitcoin
    deposit_memo = None
    source_chain = request.source_chain
    if source_chain and source_chain.coin == Coin.BTC and response.transaction_request:
        deposit_memo = response.transaction_request.data

    route_id = response.id or generate_route_id()

    return SwapRoute(
        provider=SwapProviderEnum.LIFI,
        steps=steps,
        source_amount=response.estimate.from_amount,
        destination_amount=response.estimate.to_amount,
        destination_amount_min=response.estimate.to_amount_min,
        estimated_time=int(response.estimate.execution_duration),
        price_impact=None,
        network_fee=network_fee,
        deposit_address=deposit_address,
        deposit_memo=deposit_memo,
        transaction_params=transaction_params,
        requires_token_allowance=True,
        requires_firm_route=False,
        slippage_percentage=str(response.action.slippage * 100),
        id=route_id,
    )
