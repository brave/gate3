import asyncio

from fastapi import APIRouter, Depends, Query

from app.api.common.annotations import (
    VS_CURRENCY_DESCRIPTION,
)

from .coingecko import CoinGeckoClient
from .jupiter import JupiterClient
from .models import (
    BatchTokenPriceRequests,
    TokenPriceRequest,
    TokenPriceResponse,
    VsCurrency,
)
from .utils import deduplicate_batch

router = APIRouter(prefix="/api/pricing")


def get_coingecko_client() -> CoinGeckoClient:
    return CoinGeckoClient()


def get_jupiter_client() -> JupiterClient:
    return JupiterClient()


@router.post("/v1/getPrices", response_model=list[TokenPriceResponse])
async def get_prices(
    tokens: list[TokenPriceRequest],
    vs_currency: VsCurrency = Query(
        default=VsCurrency.USD,
        description=VS_CURRENCY_DESCRIPTION,
        examples=[VsCurrency.USD, VsCurrency.EUR],
    ),
    coingecko_client: CoinGeckoClient = Depends(get_coingecko_client),
    jupiter_client: JupiterClient = Depends(get_jupiter_client),
) -> list[TokenPriceResponse]:
    """
    Batch retrieve prices for multiple tokens. Each token can be specified
    using a different chain and/or currency.
    """
    batch = BatchTokenPriceRequests(requests=tokens, vs_currency=vs_currency)

    # Deduplicate requests
    batch = deduplicate_batch(batch)

    # Filter tokens for CoinGecko
    coingecko_available, coingecko_unavailable = await coingecko_client.filter(batch)
    # For tokens that are not available on CoinGecko, try Jupiter
    jupiter_available, _ = await jupiter_client.filter(coingecko_unavailable)

    # Prepare tasks for parallel execution
    tasks = [
        coingecko_client.get_prices(coingecko_available),
        jupiter_client.get_prices(
            batch=jupiter_available, coingecko_client=coingecko_client
        ),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle exceptions and collect valid results
    return [
        item
        for result in results
        if not isinstance(result, Exception) and result
        for item in result
    ]
