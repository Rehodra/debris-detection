import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from app.core.config import settings
    from app.api.v1 import api_v1_router
except ImportError:
    from backend.app.core.config import settings
    from backend.app.api.v1 import api_v1_router


def create_application() -> FastAPI:
    application = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
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
