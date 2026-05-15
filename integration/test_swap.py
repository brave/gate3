import pytest

USDC_MAINNET = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
VITALIK = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


@pytest.mark.asyncio
async def test_indicative_quote_eth_to_usdc_via_lifi(client):
    body = {
        "source_coin": "ETH",
        "source_chain_id": "0x1",
        "source_token_address": None,
        "destination_coin": "ETH",
        "destination_chain_id": "0x1",
        "destination_token_address": USDC_MAINNET,
        "recipient": VITALIK,
        "amount": "100000000000000000",
        "slippage_percentage": "0.5",
        "swap_type": "EXACT_INPUT",
        "refund_to": VITALIK,
        "provider": "LIFI",
    }

    response = await client.post("/api/swap/v1/quote/indicative", json=body)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert "routes" in payload
    assert len(payload["routes"]) >= 1

    route = payload["routes"][0]
    assert route["provider"] == "LIFI"
    assert int(route["sourceAmount"]) == 10**17
    assert int(route["destinationAmount"]) > 0
