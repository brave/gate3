from app.api.tokens.manager import TokenManager

from .models import SwapProviderEnum, SwapQuoteRequest
from .providers.base import BaseSwapProvider
from .providers.near_intents.client import NearIntentsClient


async def get_provider_client(
    provider: SwapProviderEnum,
    token_manager: TokenManager,
) -> BaseSwapProvider:
    """
    Get a provider client instance.

    Args:
        provider: The SwapProviderEnum
        token_manager: Token manager instance

    Returns:
        BaseSwapProvider instance

    Raises:
        ValueError: If provider is AUTO or is not supported
    """
    if provider == SwapProviderEnum.AUTO:
        raise ValueError(
            "AUTO cannot be used with get_provider_client. Use get_or_select_provider_client instead with allow_auto=True."
        )
    elif provider == SwapProviderEnum.NEAR_INTENTS:
        return NearIntentsClient(token_manager=token_manager)
    elif provider == SwapProviderEnum.ZERO_EX:
        raise NotImplementedError("0x provider not yet implemented")
    elif provider == SwapProviderEnum.JUPITER:
        raise NotImplementedError("Jupiter provider not yet implemented")
    elif provider == SwapProviderEnum.LIFI:
        raise NotImplementedError("LiFi provider not yet implemented")
    else:
        raise ValueError(f"Unsupported provider: {provider}")


async def get_or_select_provider_client(
    request: SwapQuoteRequest, token_manager: TokenManager, allow_auto: bool = True
) -> BaseSwapProvider:
    """
    Get or select a provider client for a swap request.

    If a specific provider is specified in the request, it will be used.
    If AUTO is specified or no provider is specified, automatic selection is performed.

    Args:
        request: The swap quote request
        token_manager: Token manager instance
        allow_auto: If False, raises ValueError when AUTO is specified or no provider is specified

    Returns:
        BaseSwapProvider instance

    Raises:
        ValueError: If the specified provider doesn't support the swap, no provider supports it,
                    or if allow_auto=False and AUTO/no provider is specified
    """
    # If user specified a provider (and it's not AUTO), use it
    if request.provider and request.provider != SwapProviderEnum.AUTO:
        client = await get_provider_client(request.provider, token_manager)
        if not await client.has_support(request):
            raise ValueError(
                f"Provider {request.provider.value} does not support this swap"
            )
        return client

    # Check if auto-selection is allowed
    if not allow_auto:
        if request.provider == SwapProviderEnum.AUTO:
            raise ValueError("AUTO provider is not allowed. Please specify a provider.")
        if request.provider is None:
            raise ValueError(
                "No provider specified and auto-selection is not allowed. Please specify a provider."
            )

    # Auto-select (either AUTO was specified or no provider was specified)
    #
    # Try NEAR Intents (currently the only option)
    # Future implementations will check multiple providers and select based on:
    # - Best rates
    # - Lowest fees
    # - Fastest execution
    # - User preferences
    near_intents = NearIntentsClient(token_manager=token_manager)
    if await near_intents.has_support(request):
        return near_intents

    raise ValueError(
        "No provider supports this swap. Please check your token pair and chains."
    )
