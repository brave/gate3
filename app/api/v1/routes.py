from fastapi import APIRouter

from app.core.cache import Cache
from app.api.v1.models import PingResponse, HealthStatus

router = APIRouter()

@router.get("/ping", response_model=PingResponse)
async def ping():
    ok = await Cache.ping()
    return PingResponse(redis=HealthStatus.OK if ok else HealthStatus.KO)
