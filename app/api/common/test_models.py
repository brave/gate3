import pytest

from app.api.common.models import Chain, Coin


@pytest.mark.parametrize(
    "comparison_chain",
    [Chain.BITCOIN, Chain.ETHEREUM, Chain.SOLANA, Chain.CARDANO],
)
def test_chain_get_returns_none_comparison(comparison_chain):
    chain = Chain.get("INVALID_COIN", "invalid_chain_id")
    assert chain is None
    assert (chain == comparison_chain) is False


@pytest.mark.parametrize(
    "chain,other_object",
    [
        (Chain.BITCOIN, "bitcoin"),
        (Chain.ETHEREUM, 1),
        (Chain.SOLANA, Coin.BTC),
        (Chain.BITCOIN, {"coin": "BTC"}),
        (Chain.ETHEREUM, []),
        (Chain.SOLANA, None),
    ],
)
def test_chain_equals_non_chain_object_returns_false(chain, other_object):
    assert (chain == other_object) is False


@pytest.mark.parametrize(
    "coin,chain_id,expected_chain,different_chain",
    [
        ("BTC", "bitcoin_mainnet", Chain.BITCOIN, Chain.ETHEREUM),
        ("ETH", "0x1", Chain.ETHEREUM, Chain.SOLANA),
        ("SOL", "0x65", Chain.SOLANA, Chain.BITCOIN),
        ("ADA", "cardano_mainnet", Chain.CARDANO, Chain.FILECOIN),
    ],
)
def test_chain_get_valid_chain_comparison(
    coin, chain_id, expected_chain, different_chain
):
    chain = Chain.get(coin, chain_id)
    assert chain is not None
    assert chain == expected_chain
    # Verify it's not equal to a different chain
    assert (chain == different_chain) is False
    assert chain != different_chain


def test_chain_equality_with_case_insensitive_chain_id():
    chain1 = Chain.get("BTC", "BITCOIN_MAINNET")
    chain2 = Chain.get("btc", "bitcoin_mainnet")
    assert chain1 == chain2
    assert chain1 == Chain.BITCOIN
    assert chain2 == Chain.BITCOIN


@pytest.mark.parametrize("chain", list(Chain))
def test_all_chains(chain):
    assert (chain is None) is False
    none = None
    assert (none == chain) is False

    assert chain == chain
    assert chain is chain
    assert chain is not None
