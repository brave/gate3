import time

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from app.api.common.models import Coin, Tags
from app.api.tokens.manager import TokenManager

from .metrics import (
    record_auto_best_provider,
    record_provider_error,
    record_quote_metrics,
    record_status_request,
)
from .models import (
    SwapError,
    SwapErrorKind,
    SwapProviderEnum,
    SwapProviderInfo,
    SwapQuote,
    SwapQuoteRequest,
    SwapStatusRequest,
    SwapStatusResponse,
    SwapSupportRequest,
)
from .utils import (
    apply_default_slippage,
    get_all_indicative_routes,
    get_provider_client,
    get_provider_client_for_request,
    get_supported_provider_clients,
)

router = APIRouter(prefix="/api/swap", tags=[Tags.SWAP])


def setup_swap_error_handler(app: FastAPI):
    async def handler(request: Request, exc: SwapError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.as_dict(),
        )

    app.add_exception_handler(SwapError, handler)


@router.get("/v1/providers", response_model=list[SwapProviderInfo])
async def get_providers() -> list[SwapProviderInfo]:
    return [provider.to_info() for provider in SwapProviderEnum]


@router.get("/v1/providers/supported", response_model=list[SwapProviderEnum])
async def get_supported_providers(
    source_coin: str = Query(..., description="Source coin (e.g., ETH, SOL, BTC)"),
    source_chain_id: str = Query(..., description="Source chain ID"),
    source_token_address: str | None = Query(
        None,
        description="Source token address (None for native)",
    ),
    destination_coin: str = Query(
        ...,
        description="Destination coin (e.g., ETH, SOL, BTC)",
    ),
    destination_chain_id: str = Query(..., description="Destination chain ID"),
    destination_token_address: str | None = Query(
        None,
        description="Destination token address (None for native)",
    ),
    recipient: str | None = Query(
        None,
        description="Recipient address on destination chain",
    ),
    token_manager: TokenManager = Depends(TokenManager),
) -> list[SwapProviderEnum]:
    """Returns a list of providers that support the specified token pair swap.

    If at least one provider supports the swap, AUTO is also included in the list.
    """
    try:
        request = SwapSupportRequest(
            source_coin=Coin(source_coin.upper()),
            source_chain_id=source_chain_id,
            source_token_address=source_token_address,
            destination_coin=Coin(destination_coin.upper()),
            destination_chain_id=destination_chain_id,
            destination_token_address=destination_token_address,
            recipient=recipient,
        )

        clients = await get_supported_provider_clients(request, token_manager)
        supported_providers = [c.provider_id for c in clients]

        return (
            ([SwapProviderEnum.AUTO] + supported_providers)
            if supported_providers
            else []
        )
    except SwapError:
        # Re-raise SwapError as-is
        raise
    except ValueError as e:
        raise SwapError(message=str(e), kind=SwapErrorKind.UNKNOWN, status_code=400)
    except Exception as e:
        raise SwapError(
            message=f"Failed to check provider support: {e!s}",
            kind=SwapErrorKind.UNKNOWN,
            status_code=500,
        )


@router.post("/v1/quote/indicative", response_model=SwapQuote)
async def get_indicative_quote(
    request: SwapQuoteRequest,
    token_manager: TokenManager = Depends(TokenManager),
) -> SwapQuote:
    """Request indicative quotes without creating a deposit address.

    This is a dry run to preview swap parameters, pricing, and estimated time.
    No funds should be sent based on an indicative quote.

    Returns multiple route options for comparison. Each route may have multiple
    steps (hops) if it's a multi-hop swap. Routes are sorted by best rate
    (highest destination amount first).

    When using AUTO mode (or no provider specified), routes from all eligible
    providers are fetched and combined.

    The quotes may not include deposit addresses or expiration times.
    """
    start_time = time.perf_counter()
    success = False

    try:
        # For AUTO mode, fetch routes from all eligible providers
        if request.provider is None or request.provider == SwapProviderEnum.AUTO:
            routes = await get_all_indicative_routes(request, token_manager)

            # Record which provider won (first route is best)
            if routes:
                record_auto_best_provider(request, routes[0].provider)

            success = True
            return SwapQuote(routes=routes)

        # For specific provider, get routes from that provider only
        provider = await get_provider_client_for_request(request, token_manager)
        apply_default_slippage(provider, request)

        routes = await provider.get_indicative_routes(request)
        success = True
        return SwapQuote(routes=routes)
    except SwapError as e:
        record_provider_error(request, e.kind.value, "indicative_quote")
        raise
    except ValueError as e:
        record_provider_error(request, SwapErrorKind.UNKNOWN.value, "indicative_quote")
        raise SwapError(message=str(e), kind=SwapErrorKind.UNKNOWN, status_code=400)
    except Exception as e:
        record_provider_error(request, SwapErrorKind.UNKNOWN.value, "indicative_quote")
        raise SwapError(
            message=f"Failed to get indicative quote: {e!s}",
            kind=SwapErrorKind.UNKNOWN,
            status_code=500,
        )
    finally:
        duration = time.perf_counter() - start_time
        record_quote_metrics(request, "indicative", duration, success)


@router.post("/v1/quote/firm", response_model=SwapQuote)
async def get_firm_quote(
    request: SwapQuoteRequest,
    token_manager: TokenManager = Depends(TokenManager),
) -> SwapQuote:
    """Request a firm quote with a deposit address.

    This creates a real swap intent with a unique deposit address.
    Funds sent to this address will initiate the swap.

    The quote includes:
    - Deposit address where funds should be sent
    - Deposit memo (if required for the chain, e.g., Stellar)
    - Expiration time/deadline
    - Guaranteed output amount (accounting for slippage)
    - Transaction parameters for the deposit

    Important: Save the entire response, including provider metadata,
    as it may contain signatures or other data needed for dispute resolution.
    """
    start_time = time.perf_counter()
    success = False

    try:
        provider = await get_provider_client_for_request(request, token_manager)
        apply_default_slippage(provider, request)

        route = await provider.get_firm_route(request)
        success = True
        return SwapQuote(routes=[route])
    except SwapError as e:
        record_provider_error(request, e.kind.value, "firm_quote")
        raise
    except ValueError as e:
        record_provider_error(request, SwapErrorKind.UNKNOWN.value, "firm_quote")
        raise SwapError(message=str(e), kind=SwapErrorKind.UNKNOWN, status_code=400)
    except Exception as e:
        record_provider_error(request, SwapErrorKind.UNKNOWN.value, "firm_quote")
        raise SwapError(
            message=f"Failed to get firm quote: {e!s}",
            kind=SwapErrorKind.UNKNOWN,
            status_code=500,
        )
    finally:
        duration = time.perf_counter() - start_time
        record_quote_metrics(request, "firm", duration, success)


@router.post("/v1/post-submit-hook")
async def post_submit_hook(
    request: SwapStatusRequest,
    token_manager: TokenManager = Depends(TokenManager),
) -> dict:
    """Post-submit hook called after a deposit transaction is submitted.

    This endpoint allows providers to perform provider-specific actions after
    a deposit transaction has been submitted. The exact behavior depends on
    the swap provider implementation.

    Returns:
        Empty dict on success

    """
    try:
        client = await get_provider_client(request.provider, token_manager)
        await client.post_submit_hook(request)
        return {}
    except SwapError:
        # Re-raise SwapError as-is (from provider)
        raise
    except ValueError as e:
        raise SwapError(message=str(e), kind=SwapErrorKind.UNKNOWN, status_code=400)
    except Exception as e:
        raise SwapError(
            message=f"Failed to execute post-submit hook: {e!s}",
            kind=SwapErrorKind.UNKNOWN,
            status_code=500,
        )


@router.post("/v1/status", response_model=SwapStatusResponse)
async def get_swap_status(
    request: SwapStatusRequest,
    token_manager: TokenManager = Depends(TokenManager),
) -> SwapStatusResponse:
    """Check the status of a swap by deposit address.

    Returns:
    - Current status (PENDING, PROCESSING, SUCCESS, FAILED, REFUNDED)
    - Transaction hashes for all chains involved
    - Actual amounts transferred
    - Detailed swap information

    The status is updated in real-time as the swap progresses through:
    1. PENDING - Waiting for deposit confirmation
    2. PROCESSING - Swap is being executed
    3. SUCCESS - Swap completed successfully
    4. FAILED - Swap failed (funds will be refunded)
    5. REFUNDED - Funds have been refunded to the refund address

    """
    try:
        client = await get_provider_client(request.provider, token_manager)
        response = await client.get_status(request)
        record_status_request(request, response)
        return response
    except SwapError:
        # Re-raise SwapError as-is (from provider)
        raise
    except ValueError as e:
        raise SwapError(message=str(e), kind=SwapErrorKind.UNKNOWN, status_code=404)
    except Exception as e:
        raise SwapError(
            message=f"Failed to get swap status: {e!s}",
            kind=SwapErrorKind.UNKNOWN,
            status_code=500,
        )
