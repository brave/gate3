from ...models import SwapErrorKind
from .models import NearIntentsQuoteData


def encode_erc20_transfer(to_address: str, amount: str) -> str:
    """Encode ERC20 transfer function call data.

    The ERC20 transfer function signature is: transfer(address,uint256)
    Function selector: 0xa9059cbb (first 4 bytes of keccak256("transfer(address,uint256)"))

    Args:
        to_address: The recipient address (20 bytes, hex string with 0x prefix)
        amount: The amount to transfer (uint256, as decimal string)

    Returns:
        Hex string with 0x prefix containing the encoded function call

    """
    # Function selector for transfer(address,uint256)
    # This is the first 4 bytes of keccak256("transfer(address,uint256)")
    function_selector = "0xa9059cbb"

    # Address must start with 0x prefix
    to_address_lower = to_address.lower()
    if not to_address_lower.startswith("0x"):
        return "0x"

    # Remove 0x prefix and normalize address
    to_address_clean = to_address_lower[2:]

    # Validate address is exactly 20 bytes (40 hex characters)
    if len(to_address_clean) != 40:
        return "0x"

    # Pad address to 32 bytes (64 hex chars) for ABI encoding
    address_padded = to_address_clean.zfill(64)

    # Convert amount to hex and pad to 32 bytes (64 hex chars)
    try:
        amount_int = int(amount)
        amount_hex = hex(amount_int)[2:]  # Remove 0x prefix
        amount_padded = amount_hex.zfill(64)
    except (ValueError, TypeError):
        # If amount conversion fails, return empty data
        return "0x"

    # Combine: function selector + padded address + padded amount
    data = function_selector + address_padded + amount_padded

    return data


def calculate_price_impact(quote_data: NearIntentsQuoteData) -> float | None:
    """Calculate price impact percentage from quote data.

    Price impact is calculated as: (amount_out_usd / amount_in_usd - 1) * 100
    Negative values indicate loss due to fees/slippage.

    Args:
        quote_data: The quote data containing USD amounts

    Returns:
        Price impact percentage as float, or None if calculation is not possible

    """
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


def categorize_error(error_message: str) -> SwapErrorKind:
    """Categorize a NEAR Intents error message into a provider-agnostic error kind.

    This function analyzes error messages from NEAR Intents API and maps them
    to standardized error kinds.

    Returns:
        SwapErrorKind enum value

    """
    error_lower = error_message.lower()

    # Insufficient liquidity errors
    # Examples:
    # - "Amount is too low for bridge, try at least 1264000"
    # - "Insufficient liquidity"
    # - "Not enough liquidity"
    # - "Amount too small"
    if any(
        phrase in error_lower
        for phrase in [
            "too low",
            "too small",
            "insufficient liquidity",
            "not enough liquidity",
            "liquidity",
            "try at least",
        ]
    ):
        return SwapErrorKind.INSUFFICIENT_LIQUIDITY

    # Default to unknown if no pattern matches
    return SwapErrorKind.UNKNOWN
