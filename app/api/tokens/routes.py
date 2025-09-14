from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import ORJSONResponse as JSONResponse

from app.api.common.annotations import (
    ADDRESS_DESCRIPTION,
    CHAIN_ID_DESCRIPTION,
    COIN_TYPE_DESCRIPTION,
)
from app.api.common.models import CoinType
from app.api.tokens.manager import TokenManager
from app.api.tokens.models import (
    TokenInfo,
    TokenSearchResponse,
)

router = APIRouter(prefix="/api/tokens")


@router.get("/v1/getTokenInfo", response_model=TokenInfo)
async def get_token_info(
    coin_type: CoinType = Query(..., description=COIN_TYPE_DESCRIPTION),
    chain_id: str = Query(..., description=CHAIN_ID_DESCRIPTION),
    address: str | None = Query(None, description=ADDRESS_DESCRIPTION),
):
    try:
        # First try to get from Redis
        token_info = await TokenManager.get(
            coin_type=coin_type, chain_id=chain_id, address=address
        )

        if token_info:
            return token_info

        # If not found, try to fetch from blockchain (mock for now)
        blockchain_token = await TokenManager.mock_fetch_from_blockchain(
            coin_type, chain_id, address
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
        if not q.strip():
            return TokenSearchResponse(results=[], total=0, query=q)

        # Perform search
        search_results = await TokenManager.search(q.strip(), offset, limit)
        return search_results

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/v1/_admin/ingest/clear")
async def admin_ingest_clear_tokens():
    await TokenManager.clear_tokens()
    return JSONResponse(content={"status": "success"})


@router.get("/v1/_admin/ingest/coingecko")
async def admin_ingest_coingecko_tokens():
    await TokenManager.ingest_coingecko_data()
    return JSONResponse(content={"status": "success"})


@router.get("/v1/_admin/ingest/jupiter")
async def admin_ingest_jupiter_tokens(
    tag: Literal["lst", "verified"] = Query(..., description="Tag to ingest"),
):
    await TokenManager.ingest_jupiter_tokens(tag=tag)
    return JSONResponse(content={"status": "success"})
