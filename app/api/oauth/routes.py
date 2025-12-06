from fastapi import APIRouter

from app.api.oauth import bitflyer, gemini, uphold, zebpay

router = APIRouter(prefix="/api/oauth")

# Include provider-specific routers
router.include_router(gemini.router)
router.include_router(bitflyer.router)
router.include_router(uphold.router)
router.include_router(zebpay.router)
