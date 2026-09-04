"""Common Pydantic schemas across the MarineScan API."""

from typing import Optional, Any
from pydantic import BaseModel, Field


class StatusResponse(BaseModel):
    status: str = Field("ok", description="Operation or service status")
    message: Optional[str] = Field(None, description="Optional informational message")


class ErrorResponse(BaseModel):
    status: str = Field("error", description="Error indicator")
    detail: str = Field(..., description="Description of the encountered error")
    code: Optional[str] = Field(None, description="Application-specific error code")
