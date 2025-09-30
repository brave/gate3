import pytest

from app.api.common.utils import is_evm_address, is_solana_address


@pytest.mark.parametrize(
    "address,expected",
    [
        # Valid EVM addresses
        ("0x1234567890123456789012345678901234567890", True),
        ("0xabcdef1234567890abcdef1234567890abcdef12", True),
        ("0x0000000000000000000000000000000000000000", True),
        ("0xffffffffffffffffffffffffffffffffffffffff", True),
        ("0x1234567890abcdef1234567890abcdef12345678", True),
        ("0xe6da21BDc8a1Ab7c8F2F9A1D3004DB241E657167", True),
        ("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", True),
        # Invalid EVM addresses
        ("", False),  # Empty string
        ("0x", False),  # Just prefix
        ("0x123", False),  # Too short
        ("0x123456789012345678901234567890123456789", False),  # 39 chars (too short)
        ("0x12345678901234567890123456789012345678901", False),  # 41 chars (too long)
        ("0x123456789012345678901234567890123456789g", False),  # Invalid character 'g'
        ("0x123456789012345678901234567890123456789G", False),  # Invalid character 'G'
        ("0x123456789012345678901234567890123456789 ", False),  # Space at end
        (" 0x1234567890123456789012345678901234567890", False),  # Space at start
        ("1234567890123456789012345678901234567890", False),  # Missing 0x prefix
        ("0X1234567890123456789012345678901234567890", False),  # Wrong case prefix
        ("0x1234567890123456789012345678901234567890extra", False),  # Extra characters
        # Edge cases
        ("0x" + "a" * 40, True),  # Exactly 40 characters after 0x
        ("0x" + "0" * 40, True),  # All zeros
        ("0x" + "f" * 40, True),  # All F's
        ("0x" + "aBcDeF" * 6 + "aBcD", True),  # Mixed case
    ],
)
def test_evm_addresses(address, expected):
    assert is_evm_address(address) == expected, (
        f"Expected {expected} for {repr(address)}"
    )


@pytest.mark.parametrize(
    "address,expected",
    [
        # Valid Solana addresses
        ("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", True),
        ("So11111111111111111111111111111111111111112", True),
        ("9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM", True),
        ("1" * 32, True),  # Minimum length
        ("1" * 44, True),  # Maximum length
        # Invalid Solana addresses
        ("", False),  # Empty string
        ("1", False),  # Too short
        ("1111111111111111111111111111111", False),  # 31 chars (too short)
        (
            "1111111111111111111111111111111111111111111111111",
            False,
        ),  # 45 chars (too long)
        ("0", False),  # Contains '0' (not in base58 alphabet)
        ("O", False),  # Contains 'O' (not in base58 alphabet)
        ("I", False),  # Contains 'I' (not in base58 alphabet)
        ("l", False),  # Contains 'l' (not in base58 alphabet)
        ("1111111111111111111111111111111111111111111111110", False),  # Contains '0'
        ("111111111111111111111111111111111111111111111111O", False),  # Contains 'O'
        ("111111111111111111111111111111111111111111111111I", False),  # Contains 'I'
        ("111111111111111111111111111111111111111111111111l", False),  # Contains 'l'
        ("111111111111111111111111111111111111111111111111 ", False),  # Space at end
        (" 111111111111111111111111111111111111111111111111", False),  # Space at start
        ("0x1234567890123456789012345678901234567890", False),  # EVM address format
        # Edge cases
        ("1" * 32, True),  # Exactly 32 characters (minimum)
        ("9" * 32, True),  # 32 chars with different char
        ("z" * 32, True),  # 32 chars with different char
        ("1" * 44, True),  # Exactly 44 characters (maximum)
        ("9" * 44, True),  # 44 chars with different char
        ("z" * 44, True),  # 44 chars with different char
        (
            "1aBcDeFgHiJkLmNoPqRsTuVwXyZ" + "1" * 6,
            True,
        ),  # Mixed valid base58 characters
    ],
)
def test_solana_addresses(address, expected):
    assert is_solana_address(address) == expected, (
        f"Expected {expected} for {repr(address)}"
    )
