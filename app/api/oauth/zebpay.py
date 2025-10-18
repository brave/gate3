import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.datastructures import URL

from app.api.oauth.models import Environment
from app.config import settings

router = APIRouter(prefix="/zebpay")


@router.get("/{environment}/auth")
async def auth(environment: Environment, request: Request) -> RedirectResponse:
    """
    Redirect to Zebpay OAuth authorization page.
    Sets client_id query param inside the returnUrl query parameter

    Example: GET /api/oauth/zebpay/sandbox/auth
    """
    config = settings.oauth.zebpay
    env_config = config.get_env_config(environment.value)

    # Parse incoming query parameters
    query_params = dict(request.query_params)

    # Extract the returnUrl parameter which contains another URL
    req_return_url = query_params.get("returnUrl")
    if not req_return_url:
        raise HTTPException(status_code=400, detail="Missing returnUrl parameter")

    # Parse the returnUrl as a URL object
    return_url = URL(req_return_url).include_query_params(
        client_id=env_config.client_id
    )

    # Build the upstream auth redirect URL with modified returnUrl
    redirect_url = URL(f"{env_config.oauth_url}/account/login").include_query_params(
        returnUrl=str(return_url)
    )

    return RedirectResponse(url=str(redirect_url), status_code=302)


@router.post("/{environment}/token")
async def token(environment: Environment, request: Request) -> JSONResponse:
    """
    Forward OAuth token exchange request to Zebpay.
    Sets auth header with credentials.

    Example: POST /api/oauth/zebpay/production/token
    """
    config = settings.oauth.zebpay
    env_config = config.get_env_config(environment.value)

    url = f"{env_config.api_url}/connect/token"
    body = await request.body()
    query_params = dict(request.query_params)

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.request(
                method=request.method,
                url=url,
                auth=(env_config.client_id, env_config.client_secret),
                headers=headers,
                params=query_params,
                content=body,
                timeout=30.0,
            )

            return JSONResponse(
                content=response.json() if response.content else {},
                status_code=response.status_code,
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=502, detail=f"Zebpay request failed: {e}"
            ) from e
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Zebpay proxy error: {e}"
            ) from e
