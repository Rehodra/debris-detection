"""Downloadable JSON and CSV reports generated from a sonar analysis."""

import csv
import io
import logging
from typing import Literal, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response

from app.schemas.common import ErrorResponse
from app.services.input_service import InputValidationError
from app.services.master_pipeline_service import master_pipeline_service

logger = logging.getLogger("marinescan.api.exports")

router = APIRouter()


def _target_csv(result) -> str:
	output = io.StringIO(newline="")
	fieldnames = [
		"mission_id",
		"detection_id",
		"class_name",
		"ai_confidence",
		"calibrated_confidence",
		"trust_tier",
		"latitude",
		"longitude",
		"length_m",
		"width_m",
		"height_m",
		"risk_score",
		"risk_tier",
		"water_clearance_m",
		"action_recommendations",
	]
	writer = csv.DictWriter(output, fieldnames=fieldnames)
	writer.writeheader()

	for target in result.targets:
		coords = getattr(target, "coordinates", None)
		dims = getattr(target, "dimensions", None)
		clr = getattr(target, "clearance", None)
		t_tier = getattr(target, "trust_tier", None)
		trust_tier_str = t_tier.value if hasattr(t_tier, "value") else str(t_tier or "")
		r_tier = getattr(target, "risk_tier", None)
		risk_tier_str = r_tier.value if hasattr(r_tier, "value") else str(r_tier or "")
		recs = getattr(target, "action_recommendations", []) or []

		writer.writerow(
			{
				"mission_id": result.mission_id,
				"detection_id": target.detection_id,
				"class_name": target.class_name,
				"ai_confidence": target.ai_confidence,
				"calibrated_confidence": target.calibrated_confidence,
				"trust_tier": trust_tier_str,
				"latitude": coords.latitude if coords else None,
				"longitude": coords.longitude if coords else None,
				"length_m": dims.length_m if dims else None,
				"width_m": dims.width_m if dims else None,
				"height_m": dims.height_m if dims else None,
				"risk_score": target.risk_score,
				"risk_tier": risk_tier_str,
				"water_clearance_m": clr.clearance_m if clr else None,
				"action_recommendations": " | ".join(
					getattr(recommendation, "action_text", str(recommendation)) for recommendation in recs
				),
			}
		)

	return output.getvalue()


@router.post(
	"/report",
	responses={
		200: {"description": "Downloadable JSON or CSV marine debris report"},
		400: {"model": ErrorResponse, "description": "Invalid input image or report format"},
		500: {"model": ErrorResponse, "description": "Report generation failure"},
	},
	summary="Download Marine Debris Analysis Report",
	description="Run the master pipeline and download the complete report as JSON or one-row-per-target CSV.",
)
async def download_report(
	file: UploadFile = File(..., description="Raw sonar or camera image file"),
	report_format: Literal["json", "csv"] = Query("json", description="Report format"),
	vessel_lat: float = Query(24.8607),
	vessel_lon: float = Query(67.0011),
	vessel_heading_deg: float = Query(0.0, ge=0.0, lt=360.0),
	water_depth_m: float = Query(30.0, gt=0.0),
	meters_per_pixel: float = Query(0.05, gt=0.0),
	nadir_x: Optional[float] = Query(None),
	cable_payout_m: Optional[float] = Query(None, ge=0.0),
	fish_depth_m: Optional[float] = Query(None, ge=0.0),
	sensor_altitude_m: Optional[float] = Query(None, gt=0.0),
	slant_range_m: Optional[float] = Query(None, gt=0.0),
	confidence_threshold: float = Query(0.25, ge=0.01, le=1.0),
	preprocessing_preset: Optional[str] = Query("sonar_acoustic"),
	use_tiling: bool = Query(False),
	mission_id: Optional[str] = Query(None),
) -> Response:
	try:
		image_bytes = await file.read()
		if not image_bytes:
			raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

		result = master_pipeline_service.execute_pipeline(
			image_bytes=image_bytes,
			vessel_lat=vessel_lat,
			vessel_lon=vessel_lon,
			vessel_heading_deg=vessel_heading_deg,
			cable_payout_m=cable_payout_m,
			fish_depth_m=fish_depth_m,
			water_depth_m=water_depth_m,
			meters_per_pixel=meters_per_pixel,
			nadir_x=nadir_x,
			sensor_altitude_m=sensor_altitude_m,
			slant_range_m=slant_range_m,
			confidence_threshold=confidence_threshold,
			preprocessing_preset=preprocessing_preset,
			use_tiling=use_tiling,
			return_visualization=False,
			mission_id=mission_id,
		)

		if report_format == "csv":
			content = _target_csv(result)
			return Response(
				content=content,
				media_type="text/csv; charset=utf-8",
				headers={"Content-Disposition": f'attachment; filename="{result.mission_id}_report.csv"'},
			)

		return Response(
			content=result.model_dump_json(indent=2),
			media_type="application/json",
			headers={"Content-Disposition": f'attachment; filename="{result.mission_id}_report.json"'},
		)

	except InputValidationError as exc:
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
	except HTTPException:
		raise
	except Exception as exc:
		logger.exception("Report generation error: %s", exc)
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=f"Report generation failed: {exc}",
		)
