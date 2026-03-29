"""Stats API - aggregates sub-routers."""
from fastapi import APIRouter

from yoink_stats.api.routers.analytics import router as analytics_router
from yoink_stats.api.routers.members import router as members_router
from yoink_stats.api.routers.import_ import router as import_router

router = APIRouter()
router.include_router(analytics_router)
router.include_router(members_router)
router.include_router(import_router)
