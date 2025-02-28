from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.cache import Cache
from app.api.v1.pricing.routes import router as pricing_router
from app.api.v1.routes import router as base_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    await Cache.init()
    if not await Cache.ping():
        raise RuntimeError("Redis connection failed")
    yield
    await Cache.close()

app = FastAPI(lifespan=lifespan)


app.include_router(base_router, prefix="/v1")
app.include_router(pricing_router, prefix="/v1")
