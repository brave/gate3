from fastapi import APIRouter

from app.api.common.models import HealthStatus, PingResponse, Tags
from app.core.cache import Cache

router = APIRouter(prefix="/api", tags=[Tags.HEALTH])


@router.get("/ping", response_model=PingResponse)
async def ping():
    ok = await Cache.ping()
    return PingResponse(redis=HealthStatus.OK if ok else HealthStatus.KO)
