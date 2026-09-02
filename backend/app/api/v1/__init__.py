from fastapi import APIRouter
from .health import router as health_router

api_v1_router = APIRouter()
api_v1_router.include_router(health_router, tags=["Health"])

__all__ = ["api_v1_router"]
