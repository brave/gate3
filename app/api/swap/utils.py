from app.api.tokens.manager import TokenManager

from .models import SwapProvider as SwapProviderEnum
from .models import SwapQuoteRequest
from .providers.base import SwapProvider
from .providers.near_intents.client import NearIntentsClient


def get_provider_client(
    provider: SwapProviderEnum, token_manager: TokenManager
) -> SwapProvider:
    """
    Get a provider client instance.

    Args:
        provider: The swap provider enum
        token_manager: Token manager instance

    Returns:
        SwapProvider instance

    Raises:
        ValueError: If provider is not supported
    """
    if provider == SwapProviderEnum.NEAR_INTENTS:
        return NearIntentsClient(token_manager=token_manager)
    elif provider == SwapProviderEnum.ZERO_EX:
        raise NotImplementedError("0x provider not yet implemented")
    elif provider == SwapProviderEnum.JUPITER:
        raise NotImplementedError("Jupiter provider not yet implemented")
    elif provider == SwapProviderEnum.LIFI:
        raise NotImplementedError("LiFi provider not yet implemented")
    else:
        raise ValueError(f"Unsupported provider: {provider}")


async def select_optimal_provider(
    request: SwapQuoteRequest, token_manager: TokenManager
) -> SwapProvider:
    """
    Select the optimal provider for a swap request.

    In this first iteration, only NEAR Intents is supported.
    Future implementations will check multiple providers and select based on:
    - Best rates
    - Lowest fees
    - Fastest execution
    - User preferences

    Args:
        request: The swap quote request
        token_manager: Token manager instance

    Returns:
        SwapProvider instance

    Raises:
        ValueError: If no provider supports the requested swap
    """
    # If user specified a provider, use it
    if request.provider:
        client = get_provider_client(request.provider, token_manager)
        if not await client.has_support(request):
            raise ValueError(
                f"Provider {request.provider.value} does not support this swap"
            )
        return client

    # Auto-select: try NEAR Intents (currently the only option)
    near_intents = NearIntentsClient(token_manager=token_manager)
    if await near_intents.has_support(request):
        return near_intents

    # TODO: Add other providers here when implemented
    # - Try 0x for EVM-to-EVM swaps
    # - Try Jupiter for Solana swaps
    # - Try LiFi for cross-chain swaps

    raise ValueError(
        "No provider supports this swap. Please check your token pair and chains."
    )
