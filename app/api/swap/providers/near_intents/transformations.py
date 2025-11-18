from datetime import datetime, timedelta
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
    NearIntentsDepositMode,
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

    return NearIntentsQuoteRequestBody(
        dry=dry,
        deposit_mode=NearIntentsDepositMode.SIMPLE,
        swap_type=request.swap_type,
        slippage_tolerance=request.slippage_tolerance,
        origin_asset=request.source_token.near_intents_asset_id,
        destination_asset=request.destination_token.near_intents_asset_id,
        amount=request.amount,
        refund_to=request.sender,
        recipient=request.recipient,
        deadline=(
            datetime.now() + timedelta(minutes=10)
        ).isoformat(),  # TODO: Make this configurable based on the blockchain
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
