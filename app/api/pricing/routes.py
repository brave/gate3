from fastapi import APIRouter, Query, Depends, HTTPException

from app.api.common.models import ChainId
from app.api.common.annotations import (
    CHAIN_ID_DESCRIPTION,
    ADDRESS_DESCRIPTION,
    VS_CURRENCY_DESCRIPTION,
    COIN_TYPE_DESCRIPTION,
)

from .coingecko import CoinGeckoClient
from .models import (
    BatchTokenPriceRequests,
    TokenPriceRequest,
    TokenPriceResponse,
    CoinType,
    VsCurrency,
)


router = APIRouter(prefix="/api/pricing")


def get_coingecko_client() -> CoinGeckoClient:
    return CoinGeckoClient()


@router.get("/v1/getPrice", response_model=TokenPriceResponse)
async def get_price(
    coin_type: CoinType = Query(
        description=COIN_TYPE_DESCRIPTION,
        examples=[CoinType.ETH, CoinType.BTC, CoinType.SOL],
    ),
    chain_id: ChainId | None = Query(
        default=None,
        description=CHAIN_ID_DESCRIPTION,
        examples=[ChainId.ETHEREUM, ChainId.BASE],
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
) -> TokenPriceResponse:
    """
    Get token price of a token on a given chain against a specific base currency.
    Chain ID and address are required only for Ethereum and Solana tokens.
    """
    request = TokenPriceRequest(coin_type=coin_type, chain_id=chain_id, address=address)

    batch = BatchTokenPriceRequests(requests=[request], vs_currency=vs_currency)

    results = await coingecko_client.get_prices(batch)

    if not results:
        raise HTTPException(status_code=404, detail="Token price not found")

    return results[0]


@router.post("/v1/getPrices", response_model=list[TokenPriceResponse])
async def get_prices(
    tokens: list[TokenPriceRequest],
    vs_currency: VsCurrency = Query(
        default=VsCurrency.USD,
        description=VS_CURRENCY_DESCRIPTION,
        examples=[VsCurrency.USD, VsCurrency.EUR],
    ),
    coingecko_client: CoinGeckoClient = Depends(get_coingecko_client),
) -> list[TokenPriceResponse]:
    """
    Batch retrieve prices for multiple tokens. Each token can be specified
    using a different chain and/or currency.
    """
    batch = BatchTokenPriceRequests(requests=tokens, vs_currency=vs_currency)

    results = await coingecko_client.get_prices(batch)
    return results
