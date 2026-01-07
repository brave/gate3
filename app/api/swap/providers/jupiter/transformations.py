from decimal import Decimal

from app.api.common.models import Chain, TokenInfo
from app.api.tokens.manager import TokenManager

from ...models import (
    NetworkFee,
    SolanaTransactionParams,
    SwapProviderEnum,
    SwapQuoteRequest,
    SwapRoute,
    SwapRouteStep,
    SwapStepToken,
    SwapType,
    TransactionParams,
)
from .constants import JUPITER_TOOL
from .models import JupiterOrderResponse
from .utils import (
    generate_route_id,
)


def _token_info_to_step_token(token_info: TokenInfo) -> SwapStepToken:
    """Convert TokenInfo to SwapStepToken for route steps."""
    return SwapStepToken(
        coin=token_info.coin,
        chain_id=token_info.chain_id,
        contract_address=token_info.address,
        symbol=token_info.symbol,
        decimals=token_info.decimals,
        logo=token_info.logo,
    )


def _build_transaction_params(
    jupiter_response: JupiterOrderResponse,
    request: SwapQuoteRequest,
) -> TransactionParams | None:
    """Build transaction parameters from Jupiter order response.

    Args:
        jupiter_response: The Jupiter order response
        request: The original swap quote request

    Returns:
        TransactionParams if transaction is available, None otherwise
    """
    if not jupiter_response.transaction:
        return None

    if request.source_chain != Chain.SOLANA:
        return None

    return TransactionParams(
        solana=SolanaTransactionParams(
            chain=Chain.SOLANA.to_spec(),
            from_address=request.refund_to,
            to=jupiter_response.taker,
            value="0",
            versioned_transaction=jupiter_response.transaction,
        ),
    )


async def from_jupiter_order_to_route(
    jupiter_response: JupiterOrderResponse,
    request: SwapQuoteRequest,
    token_manager: TokenManager,
) -> SwapRoute:
    """Convert Jupiter order response to SwapRoute.

    All Jupiter quotes are firm quotes (include transaction).

    Args:
        jupiter_response: The Jupiter order response
        request: The original swap quote request
        supported_tokens: List of supported tokens for lookup

    Returns:
        SwapRoute with all steps and details
    """
    # Get source and destination token info
    from .constants import SOL_MINT

    # Handle native SOL (SOL_MINT) - pass None to token_manager for native tokens
    input_address = (
        None if jupiter_response.input_mint == SOL_MINT else jupiter_response.input_mint
    )
    source_token = await token_manager.get(
        coin=Chain.SOLANA.coin,
        chain_id=Chain.SOLANA.chain_id,
        address=input_address,
    )
    if not source_token:
        raise ValueError(
            f"Could not find token info for input mint address: {jupiter_response.input_mint}",
        )

    output_address = (
        None
        if jupiter_response.output_mint == SOL_MINT
        else jupiter_response.output_mint
    )
    destination_token = await token_manager.get(
        coin=Chain.SOLANA.coin,
        chain_id=Chain.SOLANA.chain_id,
        address=output_address,
    )
    if not destination_token:
        raise ValueError(
            f"Could not find token info for output mint address: {jupiter_response.output_mint}",
        )

    # Build route steps from route plan
    steps: list[SwapRouteStep] = []
    for hop in jupiter_response.route_plan:
        swap_info = hop.swap_info

        # Check if input mint matches source or destination token
        # Handle None addresses (native SOL) by comparing with SOL_MINT
        from .constants import SOL_MINT

        if swap_info.input_mint == (source_token.address or SOL_MINT):
            hop_input_token = source_token
        elif swap_info.input_mint == (destination_token.address or SOL_MINT):
            hop_input_token = destination_token
        else:
            hop_input_token = await token_manager.get(
                coin=Chain.SOLANA.coin,
                chain_id=Chain.SOLANA.chain_id,
                address=swap_info.input_mint,
            )

        # Check if output mint matches source or destination token
        if swap_info.output_mint == (source_token.address or SOL_MINT):
            hop_output_token = source_token
        elif swap_info.output_mint == (destination_token.address or SOL_MINT):
            hop_output_token = destination_token
        else:
            hop_output_token = await token_manager.get(
                coin=Chain.SOLANA.coin,
                chain_id=Chain.SOLANA.chain_id,
                address=swap_info.output_mint,
            )

        if not hop_input_token or not hop_output_token:
            raise ValueError(
                f"Could not find token info for hop: "
                f"input={swap_info.input_mint}, output={swap_info.output_mint}",
            )

        # Create step
        step = SwapRouteStep(
            source_token=_token_info_to_step_token(hop_input_token),
            source_amount=swap_info.in_amount,
            destination_token=_token_info_to_step_token(hop_output_token),
            destination_amount=swap_info.out_amount,
            tool=JUPITER_TOOL,
        )
        steps.append(step)

    # Calculate price impact
    price_impact = Decimal(jupiter_response.price_impact) * 100

    # Calculate network fee
    total_fee_lamports = (
        jupiter_response.signature_fee_lamports
        + jupiter_response.prioritization_fee_lamports
    )

    network_fee = None
    if total_fee_lamports > 0:
        network_fee = NetworkFee(
            amount=str(total_fee_lamports),
            decimals=Chain.SOLANA.decimals,
            symbol=Chain.SOLANA.symbol,
        )

    # Determine source amount based on swap type
    # For EXACT_OUTPUT, Jupiter provides otherAmountThreshold as minimum input
    source_amount = (
        jupiter_response.other_amount_threshold
        if request.swap_type == SwapType.EXACT_OUTPUT
        else jupiter_response.in_amount
    )

    # Generate route ID
    route_id = generate_route_id()

    # The transaction field may be an empty string if the order is invalid
    transaction_params = None
    if jupiter_response.transaction:
        transaction_params = _build_transaction_params(jupiter_response, request)
    else:
        ...
        # raise SwapError

    return SwapRoute(
        id=route_id,
        provider=SwapProviderEnum.JUPITER,
        steps=steps,
        source_amount=source_amount,
        destination_amount=jupiter_response.out_amount,
        destination_amount_min=jupiter_response.other_amount_threshold,
        estimated_time=0,  # Jupiter swaps are atomic (0 seconds)
        price_impact=float(price_impact),
        network_fee=network_fee,
        expires_at=jupiter_response.expire_at,
        transaction_params=transaction_params,
        has_post_submit_hook=False,  # Jupiter doesn't require post-submit hook
        requires_token_allowance=False,  # Jupiter handles this internally
        requires_firm_route=False,  # Jupiter provides transaction in order response
        gasless=jupiter_response.gasless,
    )
