import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.datastructures import URL

from app.api.oauth.models import Environment
from app.config import settings

router = APIRouter(prefix="/uphold")


@router.get("/{environment}/auth")
async def auth(environment: Environment, request: Request) -> RedirectResponse:
    """
    Redirect to Uphold OAuth authorization page.
    Sets client_id query param.

    Example: GET /api/oauth/uphold/sandbox/auth
    """
    config = settings.oauth.uphold
    env_config = config.get_env_config(environment.value)

    # Build query parameters with OAuth flow params
    query_params = dict(request.query_params)

    # Construct redirect URL with client_id in path
    redirect_url = str(
        URL(
            f"{str(env_config.oauth_url).rstrip('/')}/authorize/{env_config.client_id}"
        ).include_query_params(**query_params)
    )

    return RedirectResponse(url=redirect_url, status_code=302)


@router.post("/{environment}/token")
async def token(environment: Environment, request: Request) -> JSONResponse:
    """
    Forward OAuth token exchange request to Uphold.
    Sets Basic Authorization header and forwards the request.

    Example: POST /api/oauth/uphold/production/token
    """
    config = settings.oauth.uphold
    env_config = config.get_env_config(environment.value)

    url = f"{str(env_config.api_url).rstrip('/')}/oauth2/token"
    body = await request.body()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.request(
                method=request.method,
                url=url,
                content=body,
                auth=(env_config.client_id, env_config.client_secret),
                timeout=30.0,
            )

            return JSONResponse(
                content=response.json() if response.content else {},
                status_code=response.status_code,
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=502, detail=f"Uphold request failed: {e}"
            ) from e
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Uphold proxy error: {e}"
            ) from e
