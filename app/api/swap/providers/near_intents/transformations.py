from datetime import datetime, timedelta, timezone

from app.api.common.models import Chain, TokenInfo, TokenSource, TokenType

from ...models import (
    SwapDetails,
    SwapProviderEnum,
    SwapQuote,
    SwapQuoteRequest,
    SwapStatus,
    SwapStatusResponse,
    SwapTransactionDetails,
)
from .models import (
    NearIntentsDepositMode,
    NearIntentsQuoteData,
    NearIntentsQuoteRequestBody,
    NearIntentsQuoteResponse,
    NearIntentsStatusResponse,
    NearIntentsToken,
)


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

    # Convert percentage string to basis points (bps) for near intents
    # e.g., "0.5" -> 50 bps, "1.0" -> 100 bps
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
        refund_to=request.sender,
        recipient=request.recipient,
        deadline=(datetime.now(timezone.utc) + timedelta(minutes=10)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),  # ISO 8601 format with Z suffix (UTC)
    )


def _calculate_price_impact(quote_data: NearIntentsQuoteData) -> float | None:
    if not quote_data.amount_in_usd or not quote_data.amount_out_usd:
        return None

    try:
        amount_in = float(quote_data.amount_in_usd)
        amount_out = float(quote_data.amount_out_usd)
        if amount_in > 0:
            # Price impact: (amount_out_usd / amount_in_usd - 1) * 100
            # Negative values indicate loss due to fees/slippage
            return ((amount_out / amount_in) - 1) * 100
    except (ValueError, TypeError):
        # If conversion fails, return None
        pass

    return None


def from_near_intents_quote(response: NearIntentsQuoteResponse) -> SwapQuote:
    quote_data = response.quote

    price_impact = _calculate_price_impact(quote_data)

    return SwapQuote(
        provider=SwapProviderEnum.NEAR_INTENTS,
        source_amount=quote_data.amount_in,
        destination_amount=quote_data.amount_out,
        destination_amount_min=quote_data.min_amount_out,
        estimated_time=quote_data.time_estimate,
        deposit_address=quote_data.deposit_address,
        deposit_memo=quote_data.deposit_memo,
        expires_at=quote_data.deadline,
        price_impact=price_impact,
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
    asset_id: str, supported_tokens: list[TokenInfo]
) -> TokenInfo | None:
    """Find a token by its NEAR Intents asset ID."""
    return next(
        (t for t in supported_tokens if t.near_intents_asset_id == asset_id), None
    )


def from_near_intents_status(
    response: NearIntentsStatusResponse,
    supported_tokens: list[TokenInfo],
) -> SwapStatusResponse:
    origin_asset = _find_token_by_asset_id(
        response.quote_response.quote_request.origin_asset_id, supported_tokens
    )
    destination_asset = _find_token_by_asset_id(
        response.quote_response.quote_request.destination_asset_id, supported_tokens
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
            )
        )

    # Add destination chain transactions
    for tx in swap_details_data.destination_chain_tx_hashes:
        transactions.append(
            SwapTransactionDetails(
                coin=destination_asset.coin,
                chain_id=destination_asset.chain_id,
                hash=tx.hash,
                explorer_url=tx.explorer_url,
            )
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
