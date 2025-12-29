import asyncio
import logging

from app.api.tokens.manager import TokenManager

from .models import (
    RoutePriority,
    SwapProviderEnum,
    SwapQuoteRequest,
    SwapRoute,
    SwapSupportRequest,
    SwapType,
)
from .providers.base import BaseSwapProvider
from .providers.near_intents.client import NearIntentsClient

logger = logging.getLogger(__name__)


async def _get_provider_client(
    provider: SwapProviderEnum,
    token_manager: TokenManager,
) -> BaseSwapProvider:
    """Get a provider client instance.

    Internal helper - use get_provider_client_for_request for external usage.

    Args:
        provider: The SwapProviderEnum (must not be AUTO)
        token_manager: Token manager instance

    Returns:
        BaseSwapProvider instance

    Raises:
        ValueError: If provider is AUTO or unknown
        NotImplementedError: If provider is not yet implemented

    """
    if provider == SwapProviderEnum.AUTO:
        raise ValueError("AUTO is not a concrete provider")
    if provider == SwapProviderEnum.NEAR_INTENTS:
        return NearIntentsClient(token_manager=token_manager)
    if provider == SwapProviderEnum.ZERO_EX:
        raise NotImplementedError("0x provider not yet implemented")
    if provider == SwapProviderEnum.JUPITER:
        raise NotImplementedError("Jupiter provider not yet implemented")
    if provider == SwapProviderEnum.LIFI:
        raise NotImplementedError("LiFi provider not yet implemented")
    raise ValueError(f"Unknown provider: {provider}")


async def get_provider_client_for_request(
    request: SwapQuoteRequest,
    token_manager: TokenManager,
) -> BaseSwapProvider:
    """Get a provider client for a swap request.

    Requires an explicit provider to be specified in the request (not AUTO or None).
    For AUTO mode, use get_all_indicative_routes instead.

    Args:
        request: The swap quote request with explicit provider
        token_manager: Token manager instance

    Returns:
        BaseSwapProvider instance

    Raises:
        ValueError: If provider is AUTO, None, or doesn't support the swap

    """
    if request.provider == SwapProviderEnum.AUTO:
        raise ValueError("AUTO provider is not allowed. Please specify a provider.")
    if request.provider is None:
        raise ValueError("No provider specified. Please specify a provider.")

    client = await _get_provider_client(request.provider, token_manager)
    if not await client.has_support(request):
        raise ValueError(
            f"Provider {request.provider.value} does not support this swap",
        )
    return client


async def get_supported_provider_clients(
    request: SwapSupportRequest,
    token_manager: TokenManager,
) -> list[BaseSwapProvider]:
    """Get provider clients that support the specified swap.

    Returns instantiated clients for providers that support the swap,
    avoiding the need to re-instantiate them later.

    Args:
        request: The swap support request
        token_manager: Token manager instance

    Returns:
        List of BaseSwapProvider clients that support the swap

    """
    supported_clients: list[BaseSwapProvider] = []

    for provider in SwapProviderEnum:
        if provider == SwapProviderEnum.AUTO:
            continue
        try:
            client = await _get_provider_client(provider, token_manager)
            if await client.has_support(request):
                supported_clients.append(client)
        except NotImplementedError:
            continue
        except Exception as e:
            logger.warning(f"Error checking support for {provider.value}: {e}")
            continue

    return supported_clients


async def get_all_indicative_routes(
    request: SwapQuoteRequest,
    token_manager: TokenManager,
) -> list[SwapRoute]:
    """Fetch indicative routes from all eligible providers and return sorted by best rate.

    Uses get_supported_provider_clients to get eligible provider clients, then fetches
    routes from those in parallel. Routes are sorted by destination_amount (highest first).

    Args:
        request: The swap quote request
        token_manager: Token manager instance

    Returns:
        List of SwapRoute from all providers, sorted by destination_amount descending

    Raises:
        ValueError: If no provider supports the swap

    """
    clients = await get_supported_provider_clients(request, token_manager)

    if not clients:
        raise ValueError(
            "No provider supports this swap. Please check your token pair and chains.",
        )

    async def fetch_routes(client: BaseSwapProvider) -> list[SwapRoute]:
        """Fetch routes from a client, returning empty list on error."""
        try:
            return await client.get_indicative_routes(request)
        except Exception as e:
            logger.warning(
                f"Error fetching routes from {client.provider_id.value}: {e}"
            )
            return []

    # Fetch routes from all clients in parallel
    results = await asyncio.gather(*[fetch_routes(c) for c in clients])

    # Flatten all routes into a single list
    all_routes: list[SwapRoute] = []
    for routes in results:
        all_routes.extend(routes)

    if not all_routes:
        raise ValueError(
            "No provider supports this swap. Please check your token pair and chains.",
        )

    return sort_routes(all_routes, request.route_priority, request.swap_type)


def sort_routes(
    routes: list[SwapRoute],
    priority: RoutePriority,
    swap_type: SwapType = SwapType.EXACT_INPUT,
) -> list[SwapRoute]:
    """Sort routes based on the given priority, with tie-breaking by the other priority.

    Args:
        routes: List of routes to sort
        priority: Primary sort - CHEAPEST or FASTEST
        swap_type: EXACT_INPUT (cheapest = highest output) or EXACT_OUTPUT (cheapest = lowest input)

    Returns:
        Sorted list of routes
    """

    def cheapest_key(r: SwapRoute) -> int:
        """Lower is better for sorting (will negate for EXACT_INPUT)."""
        if swap_type == SwapType.EXACT_OUTPUT:
            return int(r.source_amount)  # Lower input is better
        return -int(r.destination_amount)  # Higher output is better (negated)

    def fastest_key(r: SwapRoute) -> tuple[bool, int]:
        """Returns (is_none, time) - None values sort last."""
        return (r.estimated_time is None, r.estimated_time or 0)

    if priority == RoutePriority.FASTEST:
        # Primary: fastest, Secondary: cheapest
        return sorted(routes, key=lambda r: (fastest_key(r), cheapest_key(r)))

    # CHEAPEST: Primary: cheapest, Secondary: fastest
    return sorted(routes, key=lambda r: (cheapest_key(r), fastest_key(r)))
