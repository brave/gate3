import pytest

from app.api.common.models import Chain

from ...models import SwapProviderEnum, SwapStatusRequest
from .models import NearIntentsStatusResponse
from .transformations import from_near_intents_status


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
