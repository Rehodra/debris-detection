"""Health and system readiness endpoints for MarineScan API."""

from typing import Dict, Any
from fastapi import APIRouter
from app.ml.model_loader import model_loader




router = APIRouter()


@router.get("/health", response_model=Dict[str, Any], summary="Health Check")
async def health_check() -> Dict[str, Any]:
    """
    Service health check endpoint.
    Returns service status, identification, and ML model readiness.
    """
    return {
        "status": "ok",
        "service": "marinescan",
        "model_loaded": model_loader.is_loaded,
        "model_device": model_loader.device,
    }
