from fastapi import APIRouter, Query

from app.api.pricing.models import (
    TokenRequest,
    TokenResponse,
    CoinType,
    VsCurrency,
    CacheStatus,
)
from app.api.common.models import ChainId
from app.api.common.annotations import (
    CHAIN_ID_DESCRIPTION,
    ADDRESS_DESCRIPTION,
    VS_CURRENCY_DESCRIPTION,
    COIN_TYPE_DESCRIPTION,
)


router = APIRouter(prefix="/pricing")


@router.get("/v1/getPrice", response_model=TokenResponse)
async def get_price(
    coin_type: CoinType = Query(
        description=COIN_TYPE_DESCRIPTION, examples=[CoinType.ETH, CoinType.BTC]
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
) -> TokenResponse:
    """
    Get token price of a token on a given chain against a specific base currency.
    Chain ID and address are required only for Ethereum and Solana tokens.
    """
    # Create request object to trigger validation
    request = TokenRequest(
        coin_type=coin_type, chain_id=chain_id, address=address, vs_currency=vs_currency
    )

    return TokenResponse(
        **request.model_dump(),
        price=100,
        cache_status=CacheStatus.MISS,
    )


@router.post("/v1/getPrices", response_model=list[TokenResponse])
async def get_prices(tokens: list[TokenRequest]) -> list[TokenResponse]:
    """
    Batch retrieve prices for multiple tokens. Each token can be specified
    using a different chain and/or currency.
    """
    return [
        TokenResponse(
            coin_type=token.coin_type,
            chain_id=token.chain_id,
            address=token.address,
            vs_currency=token.vs_currency,
            price=100,
            cache_status=CacheStatus.MISS,
        )
        for token in tokens
    ]
