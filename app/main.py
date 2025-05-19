from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_client import start_http_server
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import settings
from app.core.cache import Cache
from app.api.pricing.routes import router as pricing_router
from app.api.nft.routes import (
    router as nfts_router,
    simplehash_router as simplehash_nfts_router,
)
from app.api.common.routes import router as base_router


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
    # TODO(onyb): Add lifespan_cache(app) when we actually need Redis

    async with lifespan_metrics(app):
        yield


app = FastAPI(lifespan=lifespan)
Instrumentator().instrument(app)


# API routers
app.include_router(base_router)
app.include_router(pricing_router)
app.include_router(nfts_router)

# SimpleHash API adapter
app.include_router(simplehash_nfts_router)
