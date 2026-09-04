import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1 import api_v1_router
from app.ml.model_loader import model_loader



logger = logging.getLogger("marinescan.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Loads and warms up the ML model on startup to ensure instant inference response.
    """
    logger.info("Initializing MarineScan API...")
    try:
        model_loader.load()
        logger.info("MarineScan YOLO model successfully initialized on startup.")
    except Exception as exc:
        logger.warning(
            "Could not load ML model on startup: %s. Model will be loaded on demand.",
            exc,
        )
    yield
    logger.info("Shutting down MarineScan API...")


def create_application() -> FastAPI:
    application = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Set up CORS middleware
    if settings.BACKEND_CORS_ORIGINS:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Include API routers
    application.include_router(api_v1_router, prefix=settings.API_V1_STR)

    @application.get("/", tags=["Root"])
    async def root_endpoint():
        return {
            "name": settings.PROJECT_NAME,
            "version": "1.0.0",
            "health_check": f"{settings.API_V1_STR}/health",
            "models_endpoint": f"{settings.API_V1_STR}/models/current",
            "detections_endpoint": f"{settings.API_V1_STR}/detections/predict",
            "documentation": "/docs",
        }

    return application


app = create_application()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
