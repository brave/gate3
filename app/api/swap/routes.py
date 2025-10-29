from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.common.models import Coin
from app.api.tokens.manager import TokenManager

from .models import (
    SubmitDepositRequest,
    SwapProvider,
    SwapQuoteRequest,
    SwapQuoteResponse,
    SwapStatusResponse,
    SwapSupportRequest,
)
from .utils import get_provider_client, select_optimal_provider

router = APIRouter(prefix="/api/swap")


@router.get("/v1/providers", response_model=list[SwapProvider])
async def get_supported_providers(
    source_coin: str = Query(..., description="Source coin (e.g., ETH, SOL, BTC)"),
    source_chain_id: str = Query(..., description="Source chain ID"),
    source_address: str | None = Query(
        None, description="Source token address (None for native)"
    ),
    destination_coin: str = Query(
        ..., description="Destination coin (e.g., ETH, SOL, BTC)"
    ),
    destination_chain_id: str = Query(..., description="Destination chain ID"),
    destination_token_address: str | None = Query(
        None, description="Destination token address (None for native)"
    ),
    token_manager: TokenManager = Depends(TokenManager),
) -> list[SwapProvider]:
    """
    Get list of providers that support a specific token pair swap.

    Returns providers that can handle the specified source and destination tokens.
    """
    try:
        request = SwapSupportRequest(
            source_coin=Coin(source_coin.upper()),
            source_chain_id=source_chain_id,
            source_token_address=source_address,
            destination_coin=Coin(destination_coin.upper()),
            destination_chain_id=destination_chain_id,
            destination_token_address=destination_token_address,
        )

        print(request)

        supported_providers = []

        # Check each available provider
        for provider in SwapProvider:
            try:
                client = get_provider_client(provider, token_manager)
                if await client.has_support(request):
                    supported_providers.append(provider)
            except NotImplementedError:
                # Provider not implemented yet, skip
                continue
            except Exception as e:
                # Provider error, skip but log
                print(f"Warning: Error checking {provider.value}: {e}")
                continue

        return supported_providers

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check provider support: {str(e)}",
        )


@router.post("/v1/quote/indicative", response_model=SwapQuoteResponse)
async def get_indicative_quote(
    request: SwapQuoteRequest, token_manager: TokenManager = Depends(TokenManager)
) -> SwapQuoteResponse:
    """
    Request an indicative quote without creating a deposit address.

    This is a dry run to preview swap parameters, pricing, and estimated time.
    No funds should be sent based on an indicative quote.

    The quote will not include a deposit address or expiration time.
    """
    try:
        provider = await select_optimal_provider(request, token_manager)
        return await provider.get_indicative_quote(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get indicative quote: {str(e)}",
        )


@router.post("/v1/quote/firm", response_model=SwapQuoteResponse)
async def get_firm_quote(
    request: SwapQuoteRequest, token_manager: TokenManager = Depends(TokenManager)
) -> SwapQuoteResponse:
    """
    Request a firm quote with a deposit address.

    This creates a real swap intent with a unique deposit address.
    Funds sent to this address will initiate the swap.

    The quote includes:
    - Deposit address where funds should be sent
    - Deposit memo (if required for the chain, e.g., Stellar)
    - Expiration time/deadline
    - Guaranteed output amount (accounting for slippage)

    Important: Save the entire response, including provider metadata,
    as it may contain signatures or other data needed for dispute resolution.
    """
    try:
        provider = await select_optimal_provider(request, token_manager)
        return await provider.get_firm_quote(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get firm quote: {str(e)}",
        )


@router.get("/v1/status", response_model=SwapStatusResponse)
async def get_swap_status(
    deposit_address: str = Query(..., description="Deposit address from firm quote"),
    deposit_memo: str | None = Query(
        default=None,
        description="Deposit memo (required if the quote included one)",
    ),
    provider: SwapProvider = Query(
        default=SwapProvider.NEAR_INTENTS,
        description="Provider that generated the quote",
    ),
) -> SwapStatusResponse:
    """
    Check the status of a swap by deposit address.

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
        client = get_provider_client(provider)
        return await client.get_swap_status(deposit_address, deposit_memo)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get swap status: {str(e)}",
        )


@router.post("/v1/deposit/submit", response_model=SwapStatusResponse)
async def submit_deposit_transaction(
    request: SubmitDepositRequest,
    provider: SwapProvider = Query(
        default=SwapProvider.NEAR_INTENTS,
        description="Provider that generated the quote",
    ),
) -> SwapStatusResponse:
    """
    Optionally submit the deposit transaction hash to speed up swap processing.

    This endpoint is optional but recommended. It allows the provider to:
    - Start processing the swap immediately
    - Verify the deposit without waiting for full confirmations
    - Provide faster updates to the status endpoint

    Without this call, the provider will still detect the deposit automatically,
    but it may take longer to start processing.

    Returns the current swap status after submission.
    """
    try:
        client = get_provider_client(provider)
        return await client.submit_deposit_tx(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit deposit transaction: {str(e)}",
        )
