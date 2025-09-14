from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.common.annotations import (
    ADDRESS_DESCRIPTION,
    CHAIN_ID_DESCRIPTION,
    COIN_TYPE_DESCRIPTION,
    VS_CURRENCY_DESCRIPTION,
)
from app.api.common.models import Chain

from .coingecko import CoinGeckoClient
from .jupiter import JupiterClient
from .models import (
    BatchTokenPriceRequests,
    CoinType,
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


@router.get("/v1/getPrice", response_model=TokenPriceResponse)
async def get_price(
    coin_type: CoinType = Query(
        description=COIN_TYPE_DESCRIPTION,
        examples=[Chain.ETHEREUM.coin, Chain.BITCOIN.coin, Chain.SOLANA.coin],
    ),
    chain_id: str = Query(
        description=CHAIN_ID_DESCRIPTION,
        examples=[
            Chain.ETHEREUM.chain_id,
            Chain.BITCOIN.chain_id,
            Chain.SOLANA.chain_id,
        ],
    ),
    address: str | None = Query(
        default=None,
        description=ADDRESS_DESCRIPTION,
        examples=["0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"],
    ),
    vs_currency: VsCurrency = Query(
        default=VsCurrency.USD,
        description=VS_CURRENCY_DESCRIPTION,
        examples=[VsCurrency.USD, VsCurrency.EUR],
    ),
    coingecko_client: CoinGeckoClient = Depends(get_coingecko_client),
    jupiter_client: JupiterClient = Depends(get_jupiter_client),
) -> TokenPriceResponse:
    """
    Get token price of a token on a given chain against a specific base currency.
    Chain ID and address are required only for Ethereum and Solana tokens.
    """
    request = TokenPriceRequest(coin_type=coin_type, chain_id=chain_id, address=address)
    batch = BatchTokenPriceRequests(requests=[request], vs_currency=vs_currency)

    # Try CoinGecko first
    coingecko_available, coingecko_unavailable = await coingecko_client.filter(batch)

    if not coingecko_available.is_empty():
        results = await coingecko_client.get_prices(coingecko_available)
        if results:
            return results[0]

    # For tokens that are not available in CoinGecko, try Jupiter Price API
    jupiter_available, _ = await jupiter_client.filter(coingecko_unavailable)
    if not jupiter_available.is_empty():
        results = await jupiter_client.get_prices(
            batch=jupiter_available, coingecko_client=coingecko_client
        )
        if results:
            return results[0]

    raise HTTPException(status_code=404, detail="Token price not found")


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

    # Try CoinGecko first
    coingecko_available, coingecko_unavailable = await coingecko_client.filter(batch)
    coingecko_results = await coingecko_client.get_prices(coingecko_available)

    # For tokens that are not available in CoinGecko, try Jupiter Price API
    jupiter_available, _ = await jupiter_client.filter(coingecko_unavailable)
    jupiter_results = await jupiter_client.get_prices(
        batch=jupiter_available, coingecko_client=coingecko_client
    )

    # Combine results
    return coingecko_results + jupiter_results
