"""
Model management API endpoints for MarineScan.
Provides endpoints for querying model status, supported debris classes,
and triggering model reload.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from app.ml.model_loader import model_loader
from app.ml.class_map import get_all_classes
from app.schemas.detection import ModelInfoResponse, ClassInfoResponse
from app.schemas.common import StatusResponse, ErrorResponse

# try:
#     from app.ml.model_loader import model_loader
#     from app.ml.class_map import get_all_classes
#     from app.schemas.detection import ModelInfoResponse, ClassInfoResponse
#     from app.schemas.common import StatusResponse, ErrorResponse
# except ImportError:
#     from backend.app.ml.model_loader import model_loader
#     from backend.app.ml.class_map import get_all_classes
#     from backend.app.schemas.detection import ModelInfoResponse, ClassInfoResponse
#     from backend.app.schemas.common import StatusResponse, ErrorResponse

logger = logging.getLogger("marinescan.api.models")

router = APIRouter()


@router.get(
    "/current",
    response_model=ModelInfoResponse,
    summary="Get Current Model Information",
    description="Retrieve details about the active YOLO model, loaded weights, compute device, and classes.",
)
async def get_current_model_info() -> ModelInfoResponse:
    if not model_loader.is_loaded:
        try:
            model_loader.load()
        except Exception as exc:
            logger.warning("Could not auto-load model: %s", exc)
    info = model_loader.get_info()
    return ModelInfoResponse(**info)


@router.get(
    "/classes",
    response_model=List[ClassInfoResponse],
    summary="List Supported Classes",
    description="Retrieve specifications, categories, risk levels, and UI colors for all detectable classes.",
)
async def get_supported_classes() -> List[ClassInfoResponse]:
    classes_data = get_all_classes()
    return [ClassInfoResponse(**item) for item in classes_data]


@router.post(
    "/reload",
    response_model=ModelInfoResponse,
    responses={500: {"model": ErrorResponse, "description": "Failed to reload model"}},
    summary="Reload Model Weights",
    description="Force reload the model from disk or specify a custom weights file path.",
)
async def reload_model(
    weights_path: Optional[str] = Query(
        None,
        description="Optional custom path to weights file (.pt). If omitted, default path is used.",
    )
) -> ModelInfoResponse:
    try:
        model_loader.load(model_path=weights_path, force_reload=True)
        return ModelInfoResponse(**model_loader.get_info())
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to reload model: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model reload failed: {str(exc)}",
        )
