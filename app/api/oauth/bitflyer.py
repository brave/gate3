import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.datastructures import URL

from app.api.oauth.models import Environment
from app.api.oauth.utils import set_query_params
from app.config import settings

router = APIRouter(prefix="/bitflyer")


@router.get("/{environment}/auth")
async def auth(environment: Environment, request: Request) -> RedirectResponse:
    """
    Redirect to Bitflyer OAuth authorization page.
    Sets client_id query param.

    Example: GET /api/oauth/bitflyer/sandbox/auth
    """
    config = settings.oauth.bitflyer
    env_config = config.get_env_config(environment.value)

    # Construct redirect URL with query parameters
    query_params = dict(request.query_params)
    query_params["client_id"] = env_config.client_id
    query_params["redirect_uri"] = "rewards://bitflyer/authorization"

    redirect_url = str(
        set_query_params(
            URL(f"{str(env_config.oauth_url).rstrip('/')}/ex/OAuth/authorize"),
            **query_params,
        )
    )

    return RedirectResponse(url=redirect_url, status_code=302)


@router.post("/{environment}/token")
async def token(environment: Environment, request: Request) -> JSONResponse:
    """
    Forward OAuth token exchange request to Bitflyer.
    Sets Basic Authorization header and client_id/client_secret in JSON payload.

    Example: POST /api/oauth/bitflyer/sandbox/token
    """
    config = settings.oauth.bitflyer
    env_config = config.get_env_config(environment.value)

    url = f"{str(env_config.oauth_url).rstrip('/')}/api/link/v1/token"

    body = await request.json()
    body["client_id"] = env_config.client_id
    body["client_secret"] = env_config.client_secret

    async with httpx.AsyncClient() as client:
        try:
            response = await client.request(
                method=request.method,
                url=url,
                json=body,
                auth=(env_config.client_id, env_config.client_secret),
                timeout=30.0,
            )

            return JSONResponse(
                content=response.json() if response.content else {},
                status_code=response.status_code,
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=502, detail="Bitflyer request failed"
            ) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail="Bitflyer proxy error") from e
