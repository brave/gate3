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
from app.api.pricing.routes import router as pricing_router
from app.api.swap.routes import router as swap_router
from app.api.swap.routes import setup_swap_error_handler
from app.api.tokens.routes import router as tokens_router
from app.config import settings
from app.core.cache import Cache

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with lifespan_cache(app), lifespan_metrics(app):
        yield


app = FastAPI(lifespan=lifespan)
Instrumentator().instrument(app)

# API routers
app.include_router(base_router)
app.include_router(pricing_router)
app.include_router(nfts_router)
app.include_router(tokens_router)
app.include_router(oauth_router)
app.include_router(swap_router)

# SimpleHash API adapter
app.include_router(simplehash_nfts_router)

# Register error handlers
setup_swap_error_handler(app)
