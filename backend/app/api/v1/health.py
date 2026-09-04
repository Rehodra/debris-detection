from typing import Dict
from fastapi import APIRouter

router = APIRouter()


@router.get("/health", response_model=Dict[str, str], summary="Health Check")
async def health_check() -> Dict[str, str]:
    """
    Service health check endpoint.
    Returns the service status and identification.
    """
    return {
        "status": "ok",
        "service": "AquaTrace"
    }
