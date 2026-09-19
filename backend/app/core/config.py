from functools import lru_cache
from typing import List, Union
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "AquaTrace Debris Detection API"
    API_V1_STR: str = "/api/v1"
    
    # Environment variables requested
    DATABASE_URL: str = "sqlite:///./AquaTrace.db"
    API_BASE_URL: str = "http://localhost:8000"
    MODEL_PATH: str = "backend/app/ml/weights/yolo11_sonar_best.pt"
    DEMO_MODE: bool = True
    CONFIDENCE_THRESHOLD: float = 0.50

    # Open-set anomaly branch (PatchCore feature-space detector)
    ANOMALY_ENABLED: bool = True
    ANOMALY_BANK_PATH: str = "backend/app/ml/anomaly/seabed_bank.npz"
    ANOMALY_THRESHOLD_KEY: str = "p95"   # p95 (100% recall, ~3.7 FP/img) | p99 | p999 (fewest FP)
    ANOMALY_MIN_AREA: int = 300

    # Optional Cloudinary delivery for generated prediction images.
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # Sonar waterfall raster artifact storage
    SONAR_ARTIFACT_DIR: str = "pred_img/sonar_artifacts"

    # Server & Debug settings
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["*"]

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
