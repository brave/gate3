import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.datastructures import URL

from app.api.oauth.models import Environment
from app.config import settings

router = APIRouter(prefix="/gemini")


@router.get("/{environment}/auth")
async def auth(environment: Environment, request: Request) -> RedirectResponse:
    """
    Redirect to Gemini OAuth authorization page.
    Sets client_id query param.

    Example: GET /api/oauth/gemini/production/auth
    """
    config = settings.oauth.gemini
    env_config = config.get_env_config(environment.value)

    # Build query parameters with OAuth flow params
    query_params = dict(request.query_params)
    query_params["client_id"] = env_config.client_id

    # Construct redirect URL with query parameters
    redirect_url = str(
        URL(f"{str(env_config.oauth_url).rstrip('/')}/auth").include_query_params(
            **query_params
        )
    )

    return RedirectResponse(url=redirect_url, status_code=302)


@router.post("/{environment}/token")
async def token(environment: Environment, request: Request) -> JSONResponse:
    """
    Forward OAuth token exchange request to Gemini.
    Sets client_id and client_secret in the JSON body.

    Example: POST /api/oauth/gemini/production/token
    """
    config = settings.oauth.gemini
    env_config = config.get_env_config(environment.value)

    url = f"{str(env_config.oauth_url).rstrip('/')}/auth/token"

    # Get original request body and merge with credentials
    body_dict = await request.json()
    body_dict["client_id"] = env_config.client_id
    body_dict["client_secret"] = env_config.client_secret

    query_params = dict(request.query_params)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.request(
                method=request.method,
                url=url,
                params=query_params,
                json=body_dict,
                timeout=30.0,
            )

            return JSONResponse(
                content=response.json() if response.content else {},
                status_code=response.status_code,
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=502, detail=f"Gemini request failed: {e}"
            ) from e
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Gemini proxy error: {e}"
            ) from e
