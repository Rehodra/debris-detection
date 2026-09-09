"""
SQLAlchemy model for persisted MarineScan analysis records.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Float, DateTime, JSON

from app.db.base import Base


class AnalysisRecord(Base):
    """One row per completed /analyses/analyze run — the real backing store for
    Dashboard aggregates and the History page. Nothing here is derived or faked;
    every field comes directly from that run's MasterAnalysisResult."""

    __tablename__ = "analysis_records"

    mission_id = Column(String, primary_key=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    filename = Column(String, nullable=False)

    vessel_lat = Column(Float, nullable=False)
    vessel_lon = Column(Float, nullable=False)
    vessel_heading_deg = Column(Float, nullable=False)

    total_targets = Column(Integer, nullable=False, default=0)
    verified_targets = Column(Integer, nullable=False, default=0)
    max_risk_tier = Column(String, nullable=True)
    class_breakdown = Column(JSON, nullable=False, default=dict)

    # Full MasterAnalysisResult.model_dump() — lets History reconstruct
    # everything (targets, geojson, summary) without re-deriving anything.
    result_json = Column(JSON, nullable=False)
