import asyncio
import logging
import subprocess
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from prometheus_client import start_http_server
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.common.routes import router as base_router
from app.api.nft.routes import (
    router as nfts_router,
)
from app.api.nft.routes import (
    simplehash_router as simplehash_nfts_router,
)
from app.api.oauth.routes import router as oauth_router
from app.api.phishing.manager import PhishingManager
from app.api.phishing.routes import router as phishing_router
from app.api.pricing.routes import router as pricing_router
from app.api.swap.routes import router as swap_router
from app.api.swap.routes import setup_swap_error_handler
from app.api.tokens.manager import TokenManager
from app.api.tokens.routes import router as tokens_router
from app.config import settings
from app.core.cache import Cache
from app.core.logging import install_access_log_sanitizer

logger = logging.getLogger(__name__)

# Keep full wallet addresses and other PII out of uvicorn access logs.
install_access_log_sanitizer()

version = subprocess.run(
    ["poetry", "version", "--short"], capture_output=True, text=True, check=True
).stdout.strip()

sentry_sdk.init(
    dsn=settings.SENTRY_DSN,
    environment=settings.ENVIRONMENT,
    release=f"gate3@{version}",
)


@asynccontextmanager
async def lifespan_cache(app: FastAPI):
    await Cache.init()
    if not await Cache.ping():
        raise RuntimeError("Redis connection failed")
    yield
    await Cache.close()


@asynccontextmanager
async def lifespan_metrics(app: FastAPI):
    start_http_server(port=settings.PROMETHEUS_PORT)
    yield


async def _reseed_tokens_if_stale():
    try:
        if await TokenManager.refresh_if_stale():
            logger.info("Token registry was stale; reseeded on startup")
    except Exception:
        logger.exception("Failed to reseed token registry on startup")


async def _reseed_phishing_if_stale():
    try:
        if await PhishingManager.refresh_if_stale():
            logger.info("Phishing hash index was stale; reseeded on startup")
    except Exception:
        logger.exception("Failed to reseed phishing hash index on startup")


@asynccontextmanager
async def lifespan_tokens(app: FastAPI):
    # Reseed in the background so a cold/stale Redis neither blocks startup nor
    # crashes the app when an upstream token source is briefly unavailable.
    app.state.token_seed_task = asyncio.create_task(_reseed_tokens_if_stale())
    yield


@asynccontextmanager
async def lifespan_phishing(app: FastAPI):
    app.state.phishing_seed_task = asyncio.create_task(_reseed_phishing_if_stale())
    yield


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with (
        lifespan_cache(app),
        lifespan_tokens(app),
        lifespan_phishing(app),
        lifespan_metrics(app),
    ):
        yield


app = FastAPI(lifespan=lifespan)
Instrumentator().instrument(app)

# API routers
app.include_router(base_router)
app.include_router(pricing_router)
app.include_router(nfts_router)
app.include_router(tokens_router)
app.include_router(phishing_router)
app.include_router(oauth_router)
app.include_router(swap_router)

# SimpleHash API adapter
app.include_router(simplehash_nfts_router)

# Register error handlers
setup_swap_error_handler(app)
