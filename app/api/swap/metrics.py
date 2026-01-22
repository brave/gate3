"""Prometheus metrics for swap API endpoints.

This module defines custom metrics for tracking swap API performance,
provider behavior, and usage patterns.
"""

from prometheus_client import Counter, Histogram

from .models import (
    SwapProviderEnum,
    SwapQuoteRequest,
    SwapStatus,
    SwapStatusRequest,
    SwapStatusResponse,
)

# Histogram buckets for response times (in seconds)
DURATION_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)

# Quote duration histogram - tracks response times for quote requests
swap_quote_duration_seconds = Histogram(
    "swap_quote_duration_seconds",
    "Response time for swap quote requests",
    labelnames=[
        "provider",
        "quote_type",
        "source_coin",
        "dest_coin",
        "source_chain_id",
        "dest_chain_id",
        "status",
    ],
    buckets=DURATION_BUCKETS,
)

# Quote requests counter - tracks total quote requests
swap_quote_requests_total = Counter(
    "swap_quote_requests_total",
    "Total number of swap quote requests",
    labelnames=[
        "provider",
        "quote_type",
        "source_coin",
        "dest_coin",
        "source_chain_id",
        "dest_chain_id",
        "status",
    ],
)

# Auto best provider counter - tracks which provider wins in AUTO mode
swap_auto_best_provider_total = Counter(
    "swap_auto_best_provider_total",
    "Count of times each provider was selected as best in AUTO mode",
    labelnames=[
        "provider",
        "source_coin",
        "dest_coin",
        "route_priority",
    ],
)

# Provider errors counter - tracks errors by provider and error type
swap_provider_errors_total = Counter(
    "swap_provider_errors_total",
    "Total number of provider errors",
    labelnames=[
        "provider",
        "error_kind",
        "operation",
    ],
)

# Swap outcomes counter - tracks only terminal states (SUCCESS, FAILED, REFUNDED)
swap_outcomes_total = Counter(
    "swap_outcomes_total",
    "Total number of completed swaps by outcome",
    labelnames=[
        "provider",
        "outcome",
    ],
)

# Terminal states that indicate a swap has completed
TERMINAL_STATES = frozenset(
    {SwapStatus.SUCCESS, SwapStatus.FAILED, SwapStatus.REFUNDED}
)


def record_quote_metrics(
    request: SwapQuoteRequest,
    quote_type: str,
    duration: float,
    success: bool,
    provider: str | None = None,
) -> None:
    """Record metrics for a quote request.

    Args:
        request: The swap quote request
        quote_type: Type of quote (indicative, firm)
        duration: Request duration in seconds
        success: Whether the request succeeded
        provider: Provider name override. If None, extracted from request
                  (defaults to AUTO if request.provider is None)
    """
    if provider is None:
        provider = (
            request.provider.value if request.provider else SwapProviderEnum.AUTO.value
        )

    status = "success" if success else "error"
    labels = {
        "provider": provider,
        "quote_type": quote_type,
        "source_coin": request.source_coin.value,
        "dest_coin": request.destination_coin.value,
        "source_chain_id": request.source_chain_id,
        "dest_chain_id": request.destination_chain_id,
        "status": status,
    }

    swap_quote_duration_seconds.labels(**labels).observe(duration)
    swap_quote_requests_total.labels(**labels).inc()


def record_auto_best_provider(
    request: SwapQuoteRequest,
    provider: SwapProviderEnum,
) -> None:
    """Record which provider was selected as best in AUTO mode.

    Args:
        request: The swap quote request
        provider: The winning provider
    """
    swap_auto_best_provider_total.labels(
        provider=provider.value,
        source_coin=request.source_coin.value,
        dest_coin=request.destination_coin.value,
        route_priority=request.route_priority.value,
    ).inc()


def record_provider_error(
    request: SwapQuoteRequest,
    error_kind: str,
    operation: str,
    provider: str | None = None,
) -> None:
    """Record a provider error.

    Args:
        request: The swap quote request
        error_kind: Type of error (INSUFFICIENT_LIQUIDITY, UNKNOWN, etc.)
        operation: Operation that failed (indicative_quote, firm_quote, status)
        provider: Provider name override. If None, extracted from request
                  (defaults to AUTO if request.provider is None)
    """
    if provider is None:
        provider = (
            request.provider.value if request.provider else SwapProviderEnum.AUTO.value
        )

    swap_provider_errors_total.labels(
        provider=provider,
        error_kind=error_kind,
        operation=operation,
    ).inc()


def record_status_request(
    request: SwapStatusRequest,
    response: SwapStatusResponse,
) -> None:
    """Record a swap outcome when a terminal state is reached.

    Only records when the swap reaches a terminal state (SUCCESS, FAILED, REFUNDED).
    Non-terminal states (PENDING, PROCESSING) are not recorded.

    Args:
        request: The swap status request
        response: The swap status response
    """
    if response.status in TERMINAL_STATES:
        swap_outcomes_total.labels(
            provider=request.provider.value,
            outcome=response.status.value,
        ).inc()
