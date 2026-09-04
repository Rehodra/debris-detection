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
    MODEL_PATH: str = "ml/weights/best.pt"
    DEMO_MODE: bool = True
    CONFIDENCE_THRESHOLD: float = 0.50

    # Optional Cloudinary delivery for generated prediction images.
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

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
