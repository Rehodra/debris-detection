"""API v1 Router Registration."""

from fastapi import APIRouter
from .health import router as health_router
from .detections import router as detections_router
from .models import router as models_router
from .preprocessing import router as preprocessing_router
from .shadows import router as shadows_router
from .physics import router as physics_router
from .confidence import router as confidence_router
from .geolocation import router as geolocation_router
from .risk import router as risk_router
from .analyses import router as analyses_router
from .exports import router as exports_router
from .sonar import router as sonar_router

api_v1_router = APIRouter()

# Register sub-routers
api_v1_router.include_router(health_router, tags=["Health"])
api_v1_router.include_router(detections_router, prefix="/detections", tags=["Detections"])
api_v1_router.include_router(models_router, prefix="/models", tags=["Models"])
api_v1_router.include_router(preprocessing_router, prefix="/preprocessing", tags=["Preprocessing"])
api_v1_router.include_router(shadows_router, prefix="/shadows", tags=["Acoustic Shadows"])
api_v1_router.include_router(physics_router, prefix="/physics", tags=["Physics & Hydrography"])
api_v1_router.include_router(confidence_router, prefix="/confidence", tags=["Confidence Calibration"])
api_v1_router.include_router(geolocation_router, prefix="/geolocation", tags=["Geolocation & Navigation"])
api_v1_router.include_router(risk_router, prefix="/risk", tags=["Maritime Risk Assessment"])
api_v1_router.include_router(analyses_router, prefix="/analyses", tags=["Master Survey Analysis Pipeline"])
api_v1_router.include_router(exports_router, prefix="/exports", tags=["Report Exports"])
api_v1_router.include_router(sonar_router, prefix="/sonar", tags=["Raw Sonar Ingestion"])

__all__ = ["api_v1_router"]
