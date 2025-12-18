from ...models import SwapErrorKind


def categorize_error(error_message: str) -> SwapErrorKind:
    """
    Categorize a NEAR Intents error message into a provider-agnostic error kind.

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
