from app.api.common.models import Chain, Coin, TokenInfo, TokenSource, TokenType

from ...models import (
    SwapDetails,
    SwapQuote,
    SwapQuoteRequest,
    SwapQuoteResponse,
    SwapStatus,
    SwapStatusResponse,
    SwapType,
    TransactionDetails,
)
from ...models import (
    SwapProvider as SwapProviderEnum,
)
from ..base import SwapProvider
from .models import (
    NearIntentsQuoteResponse,
    NearIntentsStatusResponse,
    NearIntentsToken,
    NearIntentsQuoteRequestBody,
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


def to_near_intents_request(request: SwapQuoteRequest, dry: bool = False):
    # Get asset IDs
    source_chain = request.source_chain
    dest_chain = request.dest_chain

    if not source_chain or not dest_chain:
        raise ValueError("Invalid source or destination chain")

    source_blockchain = CHAIN_TO_NEAR_INTENTS_BLOCKCHAIN.get(source_chain)
    dest_blockchain = CHAIN_TO_NEAR_INTENTS_BLOCKCHAIN.get(dest_chain)

    if not source_blockchain or not dest_blockchain:
        raise ValueError("Source or destination chain not supported by NEAR Intents")

    # Format asset IDs
    if request.source_address:
        origin_asset = f"{request.source_address}"
    else:
        origin_asset = f"native:{source_blockchain}"

    if request.dest_address:
        destination_asset = f"{request.dest_address}"
    else:
        destination_asset = f"native:{dest_blockchain}"

    # Determine amount based on swap type
    if request.swap_type == SwapType.EXACT_INPUT:
        if not request.source_amount:
            raise ValueError("source_amount required for EXACT_INPUT swap")
        amount = request.source_amount
    elif request.swap_type == SwapType.EXACT_OUTPUT:
        if not request.dest_amount:
            raise ValueError("dest_amount required for EXACT_OUTPUT swap")
        amount = request.dest_amount
    else:
        # For FLEX_INPUT and ANY_INPUT, use source_amount
        amount = request.source_amount or request.dest_amount
        if not amount:
            raise ValueError("Either source_amount or dest_amount required")

    return NearIntentsQuoteRequestBody(
        dry=dry,
        swap_type=request.swap_type.value,
        origin_asset=origin_asset,
        destination_asset=destination_asset,
        amount=amount,
        slippage=request.slippage,
        recipient=request.recipient,
        refund_to=request.refund_address or request.recipient,
        deposit_mode="SIMPLE",  # TODO: Support MEMO mode when needed
    )


def from_near_intents_quote(
    response: NearIntentsQuoteResponse, request: SwapQuoteRequest
) -> SwapQuoteResponse:
    quote_data = response.quote

    quote = SwapQuote(
        amount_in=quote_data.amount_in,
        amount_in_formatted=quote_data.amount_in_formatted,
        amount_in_usd=quote_data.amount_in_usd,
        amount_out=quote_data.amount_out,
        amount_out_formatted=quote_data.amount_out_formatted,
        amount_out_usd=quote_data.amount_out_usd,
        min_amount_out=quote_data.min_amount_out,
        estimated_time=quote_data.time_estimate,
        deposit_address=quote_data.deposit_address,
        deposit_memo=quote_data.deposit_memo,
        expires_at=quote_data.deadline,
    )

    return SwapQuoteResponse(
        provider=SwapProviderEnum.NEAR_INTENTS,
        quote=quote,
        provider_metadata={
            "timestamp": response.timestamp.isoformat(),
            "signature": response.signature,
            "quote_request": response.quote_request,
        },
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


def from_near_intents_status(
    response: NearIntentsStatusResponse,
    request_source_chain: str,
    request_dest_chain: str,
) -> SwapStatusResponse:
    swap_details_data = response.swap_details

    # Collect all transactions
    transactions = []

    # Add origin chain transactions
    for tx in swap_details_data.origin_chain_tx_hashes:
        transactions.append(
            TransactionDetails(
                chain=request_source_chain,
                hash=tx.hash,
                explorer_url=tx.explorer_url,
                status=None,
            )
        )

    # Add destination chain transactions
    for tx in swap_details_data.destination_chain_tx_hashes:
        transactions.append(
            TransactionDetails(
                chain=request_dest_chain,
                hash=tx.hash,
                explorer_url=tx.explorer_url,
                status=None,
            )
        )

    swap_details = SwapDetails(
        amount_in=swap_details_data.amount_in,
        amount_in_formatted=swap_details_data.amount_in_formatted,
        amount_in_usd=swap_details_data.amount_in_usd,
        amount_out=swap_details_data.amount_out,
        amount_out_formatted=swap_details_data.amount_out_formatted,
        amount_out_usd=swap_details_data.amount_out_usd,
        refunded_amount=swap_details_data.refunded_amount,
        refunded_amount_formatted=swap_details_data.refunded_amount_formatted,
        fees=None,  # NEAR Intents doesn't provide separate fee info
        transactions=transactions,
    )

    return SwapStatusResponse(
        status=normalize_near_intents_status(response.status),
        source_chain=request_source_chain,
        dest_chain=request_dest_chain,
        swap_details=swap_details,
        updated_at=response.updated_at,
        provider=SwapProviderEnum.NEAR_INTENTS,
        provider_metadata={
            "original_status": response.status,
            "intent_hashes": swap_details_data.intent_hashes,
            "near_tx_hashes": swap_details_data.near_tx_hashes,
        },
    )
