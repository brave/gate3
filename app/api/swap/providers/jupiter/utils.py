import uuid

from ...models import SwapErrorKind


def categorize_error(error_message: str | None) -> SwapErrorKind:
    """Categorize a Jupiter error message into a provider-agnostic error kind.

    Args:
        error_message: The error message from Jupiter API

    Returns:
        SwapErrorKind enum value
    """
    if not error_message:
        return SwapErrorKind.UNKNOWN

    error_lower = error_message.lower()

    # Insufficient liquidity errors
    if any(
        phrase in error_lower
        for phrase in [
            "insufficient liquidity",
            "not enough liquidity",
            "liquidity",
            "amount too small",
            "amount too low",
        ]
    ):
        return SwapErrorKind.INSUFFICIENT_LIQUIDITY

    # Default to unknown if no pattern matches
    return SwapErrorKind.UNKNOWN


def generate_route_id() -> str:
    """Generate a unique route ID for Jupiter routes."""
    return f"jup_{uuid.uuid4().hex[:12]}"
