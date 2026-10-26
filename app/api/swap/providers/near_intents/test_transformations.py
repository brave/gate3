from datetime import UTC, datetime, timedelta

import pytest

from app.api.common.models import Chain

from ...models import SwapProviderEnum, SwapQuoteRequest, SwapStatusRequest, SwapType
from .mocks import BTC_TOKEN_INFO, ETH_TOKEN_INFO, SOL_TOKEN_INFO, ZEC_TOKEN_INFO
from .models import NearIntentsStatusResponse
from .transformations import from_near_intents_status, to_near_intents_request


@pytest.mark.parametrize(
    "swap_details, destination_chain_id, expected_url",
    [
        # Destination tx on a known chain links to that chain's explorer
        (
            {"destinationChainTxHashes": [{"hash": "dest_hash", "explorerUrl": ""}]},
            Chain.BITCOIN.chain_id,
            "https://www.blockchain.com/explorer/transactions/btc/dest_hash",
        ),
        # No destination tx yet (pending/processing) -> no URL
        ({"destinationChainTxHashes": []}, Chain.BITCOIN.chain_id, None),
        ({}, Chain.BITCOIN.chain_id, None),
        # Unknown chain falls back to the explorer URL reported by NEAR Intents
        (
            {
                "destinationChainTxHashes": [
                    {
                        "hash": "dest_hash",
                        "explorerUrl": "https://example.com/dest_hash",
                    }
                ]
            },
            "0x999",
            "https://example.com/dest_hash",
        ),
    ],
)
def test_from_near_intents_status_explorer_url(
    swap_details, destination_chain_id, expected_url
):
    response = NearIntentsStatusResponse.model_validate(
        {"status": "SUCCESS", "swapDetails": swap_details}
    )
    request = SwapStatusRequest(
        route_id="test-route-id",
        tx_hash="test_hash",
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=destination_chain_id,
        deposit_address="4Rqnz7SPU4EqSUravxbKTSBti4RNf1XGaqvBmnLfvH83",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )

    assert from_near_intents_status(response, request).explorer_url == expected_url


@pytest.mark.parametrize(
    "source_token, refund_to, expected_minutes",
    [
        (ETH_TOKEN_INFO, "0x000000000000000000000000000000000000dEaD", 10),
        (BTC_TOKEN_INFO, "bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn", 60),
        (ZEC_TOKEN_INFO, "t1Ku2KLyndDPsR32jwnrTMd3yvi9tfFP8ML", 30),
    ],
)
def test_to_near_intents_request_deadline_by_source_chain(
    source_token, refund_to, expected_minutes
):
    supported_tokens = [source_token, SOL_TOKEN_INFO]
    request = SwapQuoteRequest(
        source_coin=source_token.coin,
        source_chain_id=source_token.chain_id,
        destination_coin=SOL_TOKEN_INFO.coin,
        destination_chain_id=SOL_TOKEN_INFO.chain_id,
        recipient="4Rqnz7SPU4EqSUravxbKTSBti4RNf1XGaqvBmnLfvH83",
        amount="100000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to=refund_to,
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    body = to_near_intents_request(request, dry=True, supported_tokens=supported_tokens)

    deadline = datetime.strptime(body.deadline, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=UTC
    )
    remaining = deadline - datetime.now(UTC)
    assert (
        timedelta(minutes=expected_minutes - 1)
        < remaining
        <= timedelta(minutes=expected_minutes)
    )
