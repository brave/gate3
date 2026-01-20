import asyncio
import logging

from app.api.tokens.manager import TokenManager

from .constants import DEFAULT_SLIPPAGE_PERCENTAGE
from .models import (
    RoutePriority,
    SwapProviderEnum,
    SwapQuoteRequest,
    SwapRoute,
    SwapSupportRequest,
    SwapType,
)
from .providers.base import BaseSwapProvider
from .providers.jupiter.client import JupiterClient
from .providers.near_intents.client import NearIntentsClient
from .providers.squid.client import SquidClient

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
        return JupiterClient(token_manager=token_manager)
    if provider == SwapProviderEnum.LIFI:
        raise NotImplementedError("LiFi provider not yet implemented")
    if provider == SwapProviderEnum.SQUID:
        return SquidClient(token_manager=token_manager)
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


def apply_default_slippage(
    provider: BaseSwapProvider,
    request: SwapQuoteRequest,
) -> None:
    """Apply default slippage to request if provider doesn't support auto slippage.

    Modifies the request in-place if slippage_percentage is None and the provider
    doesn't support automatic slippage computation.

    Args:
        provider: The swap provider client
        request: The swap quote request to potentially modify
    """
    if not provider.has_auto_slippage_support and request.slippage_percentage is None:
        request.slippage_percentage = DEFAULT_SLIPPAGE_PERCENTAGE


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

    If at least one client returns routes, returns them successfully. If no routes are
    returned but there were exceptions, raises the first exception. If no routes and
    no exceptions, raises a ValueError.

    Args:
        request: The swap quote request
        token_manager: Token manager instance

    Returns:
        List of SwapRoute from all providers, sorted by destination_amount descending

    Raises:
        Exception: The first exception encountered if no routes are returned
        ValueError: If no provider supports the swap and no exceptions occurred

    """
    clients = await get_supported_provider_clients(request, token_manager)

    if not clients:
        raise ValueError(
            "No provider supports this swap. Please check your token pair and chains.",
        )

    # Track exceptions from each client
    exceptions: list[Exception] = []

    async def fetch_routes(client: BaseSwapProvider) -> list[SwapRoute]:
        """Fetch routes from a client, returning empty list and tracking exceptions."""
        try:
            # Default slippage for providers that don't support auto slippage
            apply_default_slippage(client, request)

            return await client.get_indicative_routes(request)
        except Exception as e:
            logger.warning(
                f"Error fetching routes from {client.provider_id.value}: {e}"
            )
            exceptions.append(e)
            return []

    # Fetch routes from all clients in parallel
    results = await asyncio.gather(*[fetch_routes(c) for c in clients])

    # Flatten all routes into a single list
    all_routes: list[SwapRoute] = []
    for routes in results:
        all_routes.extend(routes)

    # If we got routes, return them (ignore any exceptions from other clients)
    if all_routes:
        return sort_routes(all_routes, request.route_priority, request.swap_type)

    # No routes - if there were exceptions, raise the first one
    if exceptions:
        raise exceptions[0]

    # No routes, no exceptions - shouldn't happen but handle gracefully
    raise ValueError(
        "No provider supports this swap. Please check your token pair and chains.",
    )


def sort_routes(
    routes: list[SwapRoute],
    priority: RoutePriority,
    swap_type: SwapType = SwapType.EXACT_INPUT,
) -> list[SwapRoute]:
    """Sort routes based on the given priority, with tie-breaking by the other priority.

    For CHEAPEST priority:
    - EXACT_INPUT: Prefer highest destination_amount, then lowest network_fee
    - EXACT_OUTPUT: Prefer lowest source_amount, then lowest network_fee

    For FASTEST priority:
    - Primary sort by estimated_time, then cheapest as tiebreaker

    Args:
        routes: List of routes to sort
        priority: Primary sort - CHEAPEST or FASTEST
        swap_type: EXACT_INPUT (cheapest = highest output) or EXACT_OUTPUT (cheapest = lowest input)

    Returns:
        Sorted list of routes
    """

    def network_fee_key(r: SwapRoute) -> tuple[bool, float]:
        """Returns (is_none, fee) - None values sort last, lower fee is better.

        Gasless routes with None network_fee are treated as zero fee (fee already
        included in output/input amounts).
        """
        if r.network_fee is None:
            # If gasless, treat as zero fee (fee already included in amounts)
            if r.gasless:
                return (False, 0.0)
            # Otherwise, couldn't compute fee - sort last
            return (True, 0.0)
        return (False, float(r.network_fee.amount))

    def cheapest_key(r: SwapRoute) -> tuple[int, tuple[bool, int]]:
        """Returns (amount_key, network_fee_key) for sorting.

        For EXACT_INPUT: Prefer highest destination_amount (negated for ascending sort)
        For EXACT_OUTPUT: Prefer lowest source_amount
        In both cases, lower network fee is better as a tiebreaker.
        """
        if swap_type == SwapType.EXACT_OUTPUT:
            # Lower input is better, then lower network fee
            return (int(r.source_amount), network_fee_key(r))
        # Higher output is better (negated), then lower network fee
        return (-int(r.destination_amount), network_fee_key(r))

    def fastest_key(r: SwapRoute) -> tuple[bool, int]:
        """Returns (is_none, time) - None values sort last."""
        return (r.estimated_time is None, r.estimated_time or 0)

    if priority == RoutePriority.FASTEST:
        # Primary: fastest, Secondary: cheapest (including network fee)
        return sorted(routes, key=lambda r: (fastest_key(r), cheapest_key(r)))

    # CHEAPEST: Primary: cheapest (amount + network fee), Secondary: fastest
    return sorted(routes, key=lambda r: (cheapest_key(r), fastest_key(r)))
