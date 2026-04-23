import asyncio

from app.api.common.amount import Amount
from app.api.common.models import Chain
from app.api.tokens.manager import TokenManager

from ...models import (
    EvmTransactionParams,
    NetworkFee,
    SwapProviderEnum,
    SwapQuoteRequest,
    SwapRoute,
    SwapRouteStep,
    SwapStepToken,
    SwapTool,
    TransactionParams,
)
from .models import ZeroExQuoteResponse
from .utils import (
    from_zero_ex_token_address,
    generate_route_id,
    is_zero_ex_native_address,
)


async def _resolve_step_token(
    token_manager: TokenManager,
    chain: Chain,
    zero_ex_token_address: str,
) -> SwapStepToken:
    contract_address = (
        None
        if is_zero_ex_native_address(zero_ex_token_address)
        else zero_ex_token_address
    )

    if contract_address is None:
        return SwapStepToken(
            coin=chain.coin,
            chain_id=chain.chain_id,
            contract_address=None,
            symbol=chain.symbol,
            decimals=chain.decimals,
            logo=None,
        )

    token = await token_manager.get(chain.coin, chain.chain_id, contract_address)
    if token:
        return SwapStepToken(
            coin=chain.coin,
            chain_id=chain.chain_id,
            contract_address=token.address,
            symbol=token.symbol,
            decimals=token.decimals,
            logo=token.logo,
        )

    return SwapStepToken(
        coin=chain.coin,
        chain_id=chain.chain_id,
        contract_address=contract_address,
        symbol="",
        decimals=0,
        logo=None,
    )


def _compute_network_fee(
    response: ZeroExQuoteResponse, chain: Chain
) -> NetworkFee | None:
    total = Amount(response.total_network_fee)
    if total.is_undefined() or not total.is_positive():
        total = Amount(response.transaction.gas) * Amount(
            response.transaction.gas_price
        )

    if total.is_undefined() or not total.is_positive():
        return None

    return NetworkFee(
        amount=str(total),
        decimals=chain.decimals,
        symbol=chain.symbol,
    )


def _build_steps(
    response: ZeroExQuoteResponse,
    source_step_token: SwapStepToken,
    destination_step_token: SwapStepToken,
) -> list[SwapRouteStep]:
    fills = response.route.fills
    sell_amount = Amount(response.sell_amount)
    buy_amount = Amount(response.buy_amount)

    if not fills:
        return [
            SwapRouteStep(
                source_token=source_step_token,
                source_amount=response.sell_amount,
                destination_token=destination_step_token,
                destination_amount=response.buy_amount,
                tool=SwapTool(name="0x", logo=None),
                percent=100.0,
            )
        ]

    steps: list[SwapRouteStep] = []
    for fill in fills:
        proportion_bps = fill.proportion_bps or 0
        step_sell = (sell_amount * proportion_bps) // 10000
        step_buy = (buy_amount * proportion_bps) // 10000
        steps.append(
            SwapRouteStep(
                source_token=source_step_token,
                source_amount=str(step_sell)
                if not step_sell.is_undefined()
                else response.sell_amount,
                destination_token=destination_step_token,
                destination_amount=str(step_buy)
                if not step_buy.is_undefined()
                else response.buy_amount,
                tool=SwapTool(name=fill.source, logo=None),
                percent=proportion_bps / 100.0,
            )
        )
    return steps


async def from_zero_ex_quote_to_route(
    response: ZeroExQuoteResponse,
    request: SwapQuoteRequest,
    token_manager: TokenManager,
) -> SwapRoute:
    source_chain = request.source_chain
    if source_chain is None:
        raise ValueError("Source chain is required to build a 0x route")

    source_step_token, destination_step_token = await asyncio.gather(
        _resolve_step_token(token_manager, source_chain, response.sell_token),
        _resolve_step_token(token_manager, source_chain, response.buy_token),
    )

    steps = _build_steps(response, source_step_token, destination_step_token)
    network_fee = _compute_network_fee(response, source_chain)

    requires_token_allowance = (
        from_zero_ex_token_address(request.source_token_address) is not None
    )
    deposit_address: str | None = None
    if requires_token_allowance and response.issues and response.issues.allowance:
        deposit_address = response.issues.allowance.spender
    if not deposit_address:
        deposit_address = response.transaction.to

    transaction_params = TransactionParams(
        evm=EvmTransactionParams(
            chain=source_chain.to_spec(),
            from_address=request.refund_to,
            to=response.transaction.to,
            value=response.transaction.value,
            data=response.transaction.data,
            gas_limit=response.transaction.gas or "0",
            gas_price=response.transaction.gas_price,
        ),
    )

    return SwapRoute(
        id=generate_route_id(),
        provider=SwapProviderEnum.ZERO_EX,
        steps=steps,
        source_amount=response.sell_amount,
        destination_amount=response.buy_amount,
        destination_amount_min=response.min_buy_amount,
        estimated_time=None,
        price_impact=None,
        network_fee=network_fee,
        deposit_address=deposit_address,
        deposit_memo=None,
        expires_at=None,
        transaction_params=transaction_params,
        requires_token_allowance=requires_token_allowance,
        requires_firm_route=False,
        slippage_percentage=(request.slippage_percentage or "").strip(),
    )
