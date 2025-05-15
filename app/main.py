from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_client import make_asgi_app

from app.core.cache import Cache
from app.api.pricing.routes import router as pricing_router
from app.api.nft.routes import (
    router as nfts_router,
    simplehash_router as simplehash_nfts_router,
)
from app.api.common.routes import router as base_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await Cache.init()
    if not await Cache.ping():
        raise RuntimeError("Redis connection failed")
    yield
    await Cache.close()


# TODO(onyb): Add lifespan to FastAPI when we actually need Redis
app = FastAPI(lifespan=None)


# API routers
app.include_router(base_router)
app.include_router(pricing_router)
app.include_router(nfts_router)

# SimpleHash API adapter
app.include_router(simplehash_nfts_router)

# Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
