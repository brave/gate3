from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import ORJSONResponse as JSONResponse

from app.api.common.annotations import (
    ADDRESS_DESCRIPTION,
    CHAIN_ID_DESCRIPTION,
    COIN_DESCRIPTION,
)
from app.api.common.models import Coin, Tags
from app.api.tokens.manager import TokenManager
from app.api.tokens.models import (
    TokenInfo,
    TokenSearchResponse,
)

router = APIRouter(prefix="/api/tokens", tags=[Tags.TOKENS])


@router.get("/v1/get", response_model=TokenInfo)
async def get_token_info(
    coin: Coin = Query(..., description=COIN_DESCRIPTION),
    chain_id: str = Query(..., description=CHAIN_ID_DESCRIPTION),
    address: str | None = Query(None, description=ADDRESS_DESCRIPTION),
):
    try:
        # First try to get from Redis
        token_info = await TokenManager.get(
            coin=coin, chain_id=chain_id, address=address
        )

        if token_info:
            return token_info

        # If not found, try to fetch from blockchain (mock for now)
        blockchain_token = await TokenManager.mock_fetch_from_blockchain(
            coin, chain_id, address
        )

        if blockchain_token:
            # Store the token in Redis for future requests
            await TokenManager.add(blockchain_token)
            return blockchain_token

        # Token not found anywhere
        raise HTTPException(status_code=404, detail="Token not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/v1/list", response_model=list[TokenInfo])
async def list_tokens(
    coin: Coin = Query(..., description=COIN_DESCRIPTION),
    chain_id: str | None = Query(None, description=CHAIN_ID_DESCRIPTION),
):
    """
    List all tokens for a specific coin and optionally chain_id.
    If chain_id is not provided, returns all tokens for the given coin across all chains.
    """
    try:
        list_results = await TokenManager.list_tokens(coin, chain_id)
        return list_results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/v1/search", response_model=TokenSearchResponse)
async def search_tokens(
    q: str = Query(
        ..., description="Search query for token name, symbol, or contract address"
    ),
    offset: int = Query(0, description="Offset for pagination"),
    limit: int = Query(100, description="Limit for pagination"),
):
    """
    Search tokens by name, symbol, contract address, or CoinGecko ID.

    Supports full-text search with case-insensitive matching.
    """
    try:
        search_results = await TokenManager.search(q.strip(), offset, limit)
        return search_results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/v1/_admin/refresh")
async def admin_refresh_all_tokens():
    try:
        await TokenManager.refresh()
        return JSONResponse(
            content={
                "status": "success",
                "message": "All tokens refreshed successfully",
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to refresh tokens: {str(e)}"
        )
