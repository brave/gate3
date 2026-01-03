import pytest

from .models import NearIntentsQuoteData
from .utils import calculate_price_impact, encode_erc20_transfer


@pytest.mark.parametrize(
    "to_address,amount",
    [
        ("0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0", "1000000"),
        ("0x742D35CC6634C0532925A3B844BC9E7595F0BEB0", "1000000"),
        ("0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0", "1"),
        ("0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0", "1000000000000000000000000"),
        ("0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0", "0"),
    ],
)
def test_encode_erc20_transfer_valid(to_address, amount):
    result = encode_erc20_transfer(to_address, amount)

    assert result.startswith("0xa9059cbb")
    # Length: 0x (2) + function selector (8) + padded address (64) + padded amount (64) = 138
    assert len(result) == 138
    assert result.startswith("0x")


@pytest.mark.parametrize(
    "to_address,amount",
    [
        ("0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0", "not_a_number"),
        ("0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0", ""),
    ],
)
def test_encode_erc20_transfer_invalid_amount(to_address, amount):
    result = encode_erc20_transfer(to_address, amount)
    assert result == "0x"


@pytest.mark.parametrize(
    "to_address",
    [
        "0x1234",  # Too short (2 bytes)
        "1234",  # Missing 0x prefix
        "742d35Cc6634C0532925a3b844Bc9e7595f0bEb0",  # Missing 0x prefix
        "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb00",  # Too long (21 bytes)
        "742d35Cc6634C0532925a3b844Bc9e7595f0bEb00",  # Missing 0x prefix and too long
        "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",  # Too short (39 chars)
        "",  # Empty
    ],
)
def test_encode_erc20_transfer_invalid_address(to_address):
    result = encode_erc20_transfer(to_address, "1000000")
    assert result == "0x"


def test_encode_erc20_transfer_case_insensitive():
    to_address_upper = "0x742D35CC6634C0532925A3B844BC9E7595F0BEB0"
    to_address_lower = "0x742d35cc6634c0532925a3b844bc9e7595f0beb0"
    amount = "1000000"

    result_upper = encode_erc20_transfer(to_address_upper, amount)
    result_lower = encode_erc20_transfer(to_address_lower, amount)

    assert result_upper == result_lower


@pytest.mark.parametrize(
    "amount_in_usd,amount_out_usd,expected",
    [
        ("100.0", "200.0", pytest.approx(100.0)),
        ("100.0", "95.0", pytest.approx(-5.0)),
        ("100.0", "100.0", pytest.approx(0.0)),
        ("100.0", "99.5", pytest.approx(-0.5)),
        ("100.0", "50.0", pytest.approx(-50.0)),
        ("2.0373", "0.6546", pytest.approx(-67.87, abs=0.1)),
    ],
)
def test_calculate_price_impact_valid(amount_in_usd, amount_out_usd, expected):
    quote_data = NearIntentsQuoteData(
        amount_in="1000000",
        amount_in_formatted="1.0",
        amount_in_usd=amount_in_usd,
        amount_out="2000000",
        amount_out_formatted="2.0",
        amount_out_usd=amount_out_usd,
        min_amount_out="1900000",
        time_estimate=60,
    )

    result = calculate_price_impact(quote_data)
    assert result == expected


@pytest.mark.parametrize(
    "amount_in_usd,amount_out_usd",
    [
        (None, "200.0"),
        ("100.0", None),
        (None, None),
        ("0.0", "200.0"),
        ("invalid", "200.0"),
        ("100.0", "invalid"),
    ],
)
def test_calculate_price_impact_none_cases(amount_in_usd, amount_out_usd):
    quote_data = NearIntentsQuoteData(
        amount_in="1000000",
        amount_in_formatted="1.0",
        amount_in_usd=amount_in_usd,
        amount_out="2000000",
        amount_out_formatted="2.0",
        amount_out_usd=amount_out_usd,
        min_amount_out="1900000",
        time_estimate=60,
    )

    result = calculate_price_impact(quote_data)
    assert result is None
