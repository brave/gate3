import uuid
from datetime import UTC, datetime, timedelta

from app.api.common.models import Chain, Coin, TokenInfo, TokenSource, TokenType

from ...models import (
    BitcoinTransactionParams,
    CardanoTransactionParams,
    EvmTransactionParams,
    SolanaTransactionParams,
    SwapDetails,
    SwapProviderEnum,
    SwapQuoteRequest,
    SwapRoute,
    SwapRouteStep,
    SwapStatus,
    SwapStatusResponse,
    SwapStepToken,
    SwapTransactionDetails,
    SwapType,
    TransactionParams,
    ZcashTransactionParams,
)
from .constants import NEAR_INTENTS_TOOL
from .models import (
    NearIntentsDepositMode,
    NearIntentsQuoteData,
    NearIntentsQuoteRequestBody,
    NearIntentsQuoteResponse,
    NearIntentsStatusResponse,
    NearIntentsToken,
)
from .utils import calculate_price_impact, compute_network_fee, encode_erc20_transfer


def from_near_intents_token(token: NearIntentsToken) -> TokenInfo | None:
    chain = Chain.get_by_near_intents_id(token.blockchain)
    if not chain:
        return None

    # TODO: Determine token type based on chain and address
    token_type = TokenType.UNKNOWN

    return TokenInfo(
        coin=chain.coin,
        chain_id=chain.chain_id,
        address=token.contract_address,
        name=token.symbol,
        symbol=token.symbol,
        decimals=token.decimals,
        logo=None,
        sources=[TokenSource.NEAR_INTENTS],
        token_type=token_type,
        near_intents_asset_id=token.asset_id,
    )


def to_near_intents_request(
    request: SwapQuoteRequest,
    dry: bool,
    supported_tokens: list[TokenInfo],
) -> NearIntentsQuoteRequestBody:
    if not request.source_chain or not request.destination_chain:
        raise ValueError("Invalid source or destination chain")

    if (
        not request.source_chain.near_intents_id
        or not request.destination_chain.near_intents_id
    ):
        raise ValueError("Invalid source or destination chain")

    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    # Convert percentage string to basis points (bps) for Near Intents
    # e.g., "0.5" -> 50 bps, "1.0" -> 100 bps
    # Near Intents requires a slippage tolerance to be specified, so None is not allowed.
    if request.slippage_percentage is None:
        raise ValueError("Slippage percentage is required")

    slippage_percentage = float(request.slippage_percentage)
    slippage_bps = int(slippage_percentage * 100)

    return NearIntentsQuoteRequestBody(
        dry=dry,
        deposit_mode=NearIntentsDepositMode.SIMPLE,
        swap_type=request.swap_type,
        slippage_tolerance=slippage_bps,
        origin_asset_id=request.source_token.near_intents_asset_id,
        destination_asset_id=request.destination_token.near_intents_asset_id,
        amount=request.amount,
        refund_to=request.refund_to,
        recipient=request.recipient,
        deadline=(datetime.now(UTC) + timedelta(minutes=10)).strftime(
            "%Y-%m-%dT%H:%M:%SZ",
        ),  # ISO 8601 format with Z suffix (UTC)
    )


def _build_transaction_params(
    quote_data: NearIntentsQuoteData,
    request: SwapQuoteRequest,
) -> TransactionParams | None:
    """Build transaction parameters for a firm quote.

    This function constructs the appropriate transaction params based on the
    source chain type (EVM, Solana, Bitcoin, Cardano, or Zcash) and whether
    it's a native or token transfer.

    For EXACT_OUTPUT swaps, uses max_amount_in as the deposit amount:
    - If input > max_amount_in: swap proceeds, excess refunded to refundTo
    - If input < min_amount_in: deposit refunded by deadline

    Args:
        quote_data: The quote data containing deposit address and amounts
        request: The original swap quote request containing chain and token info

    Returns:
        TransactionParams if this is a firm quote (has deposit_address), None otherwise

    """
    # Only populate transaction params for firm quotes
    if not quote_data.deposit_address:
        return None

    if not request.source_chain or not request.source_token:
        return None

    source_chain = request.source_chain
    source_token = request.source_token
    deposit_address = quote_data.deposit_address
    refund_to = request.refund_to

    # For EXACT_OUTPUT, use max_amount_in as the deposit amount
    # This ensures the swap will succeed; any excess is refunded
    if request.swap_type == SwapType.EXACT_OUTPUT and quote_data.max_amount_in:
        source_amount = quote_data.max_amount_in
    else:
        source_amount = quote_data.amount_in

    chain_spec = source_chain.to_spec()

    # Build transaction params based on chain
    if source_chain == Chain.BITCOIN:
        # Bitcoin transaction
        return TransactionParams(
            bitcoin=BitcoinTransactionParams(
                chain=chain_spec,
                to=deposit_address,
                value=source_amount,
                refund_to=refund_to,
            ),
        )
    if source_chain == Chain.CARDANO:
        # Cardano transaction
        return TransactionParams(
            cardano=CardanoTransactionParams(
                chain=chain_spec,
                to=deposit_address,
                value=source_amount,
                refund_to=refund_to,
            ),
        )
    if source_chain == Chain.ZCASH:
        # Zcash transaction
        return TransactionParams(
            zcash=ZcashTransactionParams(
                chain=chain_spec,
                to=deposit_address,
                value=source_amount,
                refund_to=refund_to,
            ),
        )
    if source_chain == Chain.SOLANA:
        # Solana transaction
        if source_token.is_native():
            # Native SOL transfer
            return TransactionParams(
                solana=SolanaTransactionParams(
                    chain=chain_spec,
                    from_address=refund_to,
                    to=deposit_address,
                    value=source_amount,  # Using lamports alias
                ),
            )
        # SPL token transfer
        return TransactionParams(
            solana=SolanaTransactionParams(
                chain=chain_spec,
                from_address=refund_to,
                to=deposit_address,
                value="0",  # No native SOL value for token transfers
                spl_token_mint=source_token.address,
                spl_token_amount=source_amount,
                decimals=source_token.decimals,
            ),
        )
    if source_chain.coin == Coin.ETH:
        # EVM transaction
        if source_token.is_native():
            # Native ETH/chain token transfer
            return TransactionParams(
                evm=EvmTransactionParams(
                    chain=chain_spec,
                    from_address=refund_to,
                    to=deposit_address,
                    value=source_amount,
                    data="0x",  # Empty data for native transfers
                ),
            )
        # ERC20 token transfer
        # Encode the transfer function call: transfer(deposit_address, amount)
        transfer_data = encode_erc20_transfer(deposit_address, source_amount)

        return TransactionParams(
            evm=EvmTransactionParams(
                chain=chain_spec,
                from_address=refund_to,
                to=source_token.address,  # Token contract address
                value="0",  # No native value for token transfers
                data=transfer_data,  # Encoded transfer() call
            ),
        )

    # Unsupported chain
    raise NotImplementedError(f"Unsupported chain: {source_chain}")


def _token_info_to_step_token(token: TokenInfo) -> SwapStepToken:
    """Convert TokenInfo to SwapStepToken for route steps."""
    return SwapStepToken(
        coin=token.coin,
        chain_id=token.chain_id,
        contract_address=token.address,
        symbol=token.symbol,
        decimals=token.decimals,
        logo=token.logo,
    )


async def from_near_intents_quote_to_route(
    response: NearIntentsQuoteResponse,
    request: SwapQuoteRequest,
    firm: bool,
    has_post_submit_hook: bool,
    requires_token_allowance: bool,
    requires_firm_route: bool,
) -> SwapRoute:
    """Convert NEAR Intents quote response to SwapRoute with steps."""
    quote_data = response.quote
    price_impact = calculate_price_impact(quote_data)

    # Build transaction params for firm quotes
    transaction_params = None
    if firm:
        transaction_params = _build_transaction_params(quote_data, request)

    # Compute estimated network fee based on source chain
    network_fee = await compute_network_fee(request)

    # Get source and destination tokens
    source_token = request.source_token
    destination_token = request.destination_token

    if not source_token or not destination_token:
        raise ValueError("Source and destination tokens must be set")

    # Ensure slippage_percentage is set (should be validated earlier, but double-check for type safety)
    if request.slippage_percentage is None:
        raise ValueError("Slippage percentage is required")

    # Create single step for NEAR Intents (it handles the route internally)
    step = SwapRouteStep(
        source_token=_token_info_to_step_token(source_token),
        source_amount=quote_data.amount_in,
        destination_token=_token_info_to_step_token(destination_token),
        destination_amount=quote_data.amount_out,
        tool=NEAR_INTENTS_TOOL,
    )

    # Generate route ID
    route_id = f"ni_{uuid.uuid4().hex[:12]}"

    # For EXACT_OUTPUT, set the minimum input amount
    source_amount_min = None
    if request.swap_type == SwapType.EXACT_OUTPUT:
        source_amount_min = quote_data.min_amount_in

    # Convert deadline datetime to Unix timestamp string
    expires_at = None
    if quote_data.deadline:
        # Convert datetime to Unix timestamp (seconds since epoch)
        expires_at = str(int(quote_data.deadline.timestamp()))

    return SwapRoute(
        id=route_id,
        provider=SwapProviderEnum.NEAR_INTENTS,
        steps=[step],
        source_amount=source_amount_min or quote_data.amount_in,
        destination_amount=quote_data.amount_out,
        destination_amount_min=quote_data.min_amount_out,
        estimated_time=quote_data.time_estimate,
        price_impact=price_impact,
        network_fee=network_fee,
        deposit_address=quote_data.deposit_address,
        deposit_memo=quote_data.deposit_memo,
        expires_at=expires_at,
        transaction_params=transaction_params,
        has_post_submit_hook=has_post_submit_hook,
        requires_token_allowance=requires_token_allowance,
        requires_firm_route=requires_firm_route,
        slippage_percentage=request.slippage_percentage,
    )


def normalize_near_intents_status(status: str) -> SwapStatus:
    status_mapping = {
        "KNOWN_DEPOSIT_TX": SwapStatus.PENDING,
        "PENDING_DEPOSIT": SwapStatus.PENDING,
        "INCOMPLETE_DEPOSIT": SwapStatus.PENDING,
        "PROCESSING": SwapStatus.PROCESSING,
        "SUCCESS": SwapStatus.SUCCESS,
        "REFUNDED": SwapStatus.REFUNDED,
        "FAILED": SwapStatus.FAILED,
    }
    return status_mapping.get(status, SwapStatus.PENDING)


def _find_token_by_asset_id(
    asset_id: str,
    supported_tokens: list[TokenInfo],
) -> TokenInfo | None:
    """Find a token by its NEAR Intents asset ID."""
    return next(
        (t for t in supported_tokens if t.near_intents_asset_id == asset_id),
        None,
    )


def from_near_intents_status(
    response: NearIntentsStatusResponse,
    supported_tokens: list[TokenInfo],
) -> SwapStatusResponse:
    origin_asset = _find_token_by_asset_id(
        response.quote_response.quote_request.origin_asset_id,
        supported_tokens,
    )
    destination_asset = _find_token_by_asset_id(
        response.quote_response.quote_request.destination_asset_id,
        supported_tokens,
    )

    if not origin_asset or not destination_asset:
        raise ValueError("Invalid origin or destination asset")

    swap_details_data = response.swap_details

    # Collect all transactions
    transactions = []

    # Add origin chain transactions
    for tx in swap_details_data.origin_chain_tx_hashes:
        transactions.append(
            SwapTransactionDetails(
                coin=origin_asset.coin,
                chain_id=origin_asset.chain_id,
                hash=tx.hash,
                explorer_url=tx.explorer_url,
            ),
        )

    # Add destination chain transactions
    for tx in swap_details_data.destination_chain_tx_hashes:
        transactions.append(
            SwapTransactionDetails(
                coin=destination_asset.coin,
                chain_id=destination_asset.chain_id,
                hash=tx.hash,
                explorer_url=tx.explorer_url,
            ),
        )

    swap_details = SwapDetails(
        amount_in=swap_details_data.amount_in,
        amount_in_formatted=swap_details_data.amount_in_formatted,
        amount_out=swap_details_data.amount_out,
        amount_out_formatted=swap_details_data.amount_out_formatted,
        refunded_amount=swap_details_data.refunded_amount,
        refunded_amount_formatted=swap_details_data.refunded_amount_formatted,
        transactions=transactions,
    )

    # Generate explorer URL for NEAR Intents using deposit address
    explorer_url = None
    deposit_address = response.quote_response.quote.deposit_address
    if deposit_address:
        explorer_url = (
            f"https://explorer.near-intents.org/transactions/{deposit_address}"
        )

    return SwapStatusResponse(
        # source
        source_coin=origin_asset.coin,
        source_chain_id=origin_asset.chain_id,
        source_token_address=origin_asset.address,
        # destination
        destination_coin=destination_asset.coin,
        destination_chain_id=destination_asset.chain_id,
        destination_token_address=destination_asset.address,
        recipient=response.quote_response.quote_request.recipient,
        # status fields
        status=normalize_near_intents_status(response.status),
        swap_details=swap_details,
        provider=SwapProviderEnum.NEAR_INTENTS,
        explorer_url=explorer_url,
    )
