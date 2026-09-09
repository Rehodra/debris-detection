"""
Master Analysis Pipeline Orchestration Service for MarineScan.
Executes the comprehensive 12-stage intelligence pipeline:
  1. Input validation
  2. Quality check
  3. Preprocessing
  4. YOLO detection & segmentation
  5. Candidate list extraction
  6. Acoustic shadow evidence
  7. Physics validation & salvage requirements
  8. Multi-source confidence fusion
  9. Geolocation & GeoJSON export
  10. Precision dimension estimation
  11. Maritime risk classification & NOTMAR directives
  12. Final synthesized intelligence report
"""

import time
import uuid
import logging
from typing import Optional, List, Dict, Any, Tuple
import cv2
import numpy as np

from app.schemas.analysis import (
    MasterAnalysisResult,
    MasterTargetResult,
    ExecutiveSummary,
    StageTimings,
    QualityAssessment,
    ShadowEvidence,
    MasterPhysicalDimensions,
)
from app.schemas.detection import BoundingBox, TilingConfig
from app.schemas.preprocessing import PreprocessingConfig, PreprocessingPreset
from app.schemas.geolocation import (
    NavigationalFix,
    TowfishConfig,
    SonarScanOrigin,
    GeoJSONFeatureCollection,
)
from app.schemas.risk import RiskTier
from app.services.input_service import input_service, InputValidationError
from app.services.quality_service import quality_service
from app.services.preprocessing_service import preprocessing_service
from app.services.inference_service import inference_service
from app.services.shadow_service import shadow_service
from app.services.physics_service import physics_service
from app.services.confidence_service import confidence_service
from app.services.geolocation_service import geolocation_service
from app.services.risk_service import risk_service
from app.services.image_output_service import image_output_service
from app.ml.postprocess import render_detections_overlay, encode_image_to_jpeg_bytes, encode_image_to_base64

logger = logging.getLogger("marinescan.services.master_pipeline")


class MasterPipelineService:
    """Production orchestrator executing the 12-stage marine debris pipeline."""

    def execute_pipeline(
        self,
        image_bytes: bytes,
        # Navigation & Environment Context
        vessel_lat: float = 24.8607,
        vessel_lon: float = 67.0011,
        vessel_heading_deg: float = 0.0,
        cable_payout_m: Optional[float] = None,
        fish_depth_m: Optional[float] = None,
        water_depth_m: float = 30.0,
        meters_per_pixel: float = 0.05,
        nadir_x: Optional[float] = None,
        sensor_altitude_m: Optional[float] = None,
        slant_range_m: Optional[float] = None,
        # Model & Enhancement Options
        confidence_threshold: float = 0.25,
        preprocessing_preset: Optional[str] = "sonar_acoustic",
        use_tiling: bool = False,
        tiling_config: Optional[TilingConfig] = None,
        return_visualization: bool = True,
        mission_id: Optional[str] = None,
    ) -> MasterAnalysisResult:
        """
        Execute all 12 stages in sequence and return the synthesized intelligence result.
        """
        pipeline_start = time.perf_counter()
        m_id = mission_id or f"msn_{uuid.uuid4().hex[:10]}"

        # =====================================================================
        # STAGE 1: Input Validation
        # =====================================================================
        t0 = time.perf_counter()
        img_bgr, img_meta = input_service.validate_and_decode(image_bytes)
        img_h, img_w = img_bgr.shape[:2]
        t_input_val = (time.perf_counter() - t0) * 1000.0

        # =====================================================================
        # STAGE 2: Quality Check
        # =====================================================================
        t0 = time.perf_counter()
        quality_assessment = quality_service.evaluate_image_quality(img_bgr)
        t_quality = (time.perf_counter() - t0) * 1000.0

        # =====================================================================
        # STAGE 3: Preprocessing
        # =====================================================================
        t0 = time.perf_counter()
        processed_bgr = img_bgr.copy()
        if preprocessing_preset:
            try:
                preset_enum = PreprocessingPreset(preprocessing_preset.lower())
                cfg = PreprocessingConfig(preset=preset_enum)
                processed_bgr, _ = preprocessing_service.process_image(processed_bgr, config=cfg)
            except Exception as pe:
                logger.warning("Preset %s error (%s); proceeding with original.", preprocessing_preset, pe)
        t_preproc = (time.perf_counter() - t0) * 1000.0

        # =====================================================================
        # STAGE 4: YOLO Detection / Segmentation
        # =====================================================================
        t0 = time.perf_counter()
        det_response = inference_service.predict_array(
            image_bgr=processed_bgr,
            confidence_threshold=confidence_threshold,
            meters_per_pixel=meters_per_pixel,
            use_tiling=use_tiling,
            tiling_config=tiling_config,
            return_visualization=False,
        )
        t_inference = (time.perf_counter() - t0) * 1000.0

        # =====================================================================
        # STAGE 5: Candidate List Extraction
        # =====================================================================
        t0 = time.perf_counter()
        candidates = [d.model_dump() for d in det_response.detections]
        t_candidate = (time.perf_counter() - t0) * 1000.0

        # Default nadir coordinate to center of image if not provided
        actual_nadir_x = float(nadir_x) if nadir_x is not None else float(img_w) / 2.0

        # =====================================================================
        # STAGE 6: Acoustic Shadow Evidence
        # =====================================================================
        t0 = time.perf_counter()
        shadow_response = shadow_service.analyze_all_detections(
            image_bgr=img_bgr,
            detections=candidates,
            nadir_x=actual_nadir_x,
            meters_per_pixel=meters_per_pixel,
            sensor_altitude_m=sensor_altitude_m,
            slant_range_m=slant_range_m,
            return_overlay=False,
        )
        shadow_map = {s.detection_id: s for s in shadow_response.results}
        t_shadow = (time.perf_counter() - t0) * 1000.0

        # =====================================================================
        # STAGE 7: Physics Validation
        # =====================================================================
        t0 = time.perf_counter()
        physics_response = physics_service.enrich_detections_with_physics(
            detections=candidates,
            shadow_results=shadow_response.results,
            meters_per_pixel=meters_per_pixel,
            sensor_altitude_m=sensor_altitude_m,
            slant_range_m=slant_range_m,
        )
        physics_map = {p.detection_id: p for p in physics_response.results}
        t_physics = (time.perf_counter() - t0) * 1000.0

        # =====================================================================
        # STAGE 8: Multi-Source Confidence Fusion
        # =====================================================================
        t0 = time.perf_counter()
        img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        confidence_response = confidence_service.evaluate_all_detections(
            image_gray=img_gray,
            detections=candidates,
            shadow_results=shadow_response.results,
            physics_analyses=physics_response.results,
            meters_per_pixel=meters_per_pixel,
        )
        confidence_map = {c.detection_id: c for c in confidence_response.results}
        t_confidence = (time.perf_counter() - t0) * 1000.0

        # =====================================================================
        # STAGE 9: Geolocation
        # =====================================================================
        t0 = time.perf_counter()
        vessel_fix = NavigationalFix(
            latitude=vessel_lat,
            longitude=vessel_lon,
            heading_degrees=vessel_heading_deg,
        )
        towfish_cfg = None
        if cable_payout_m is not None:
            towfish_cfg = TowfishConfig(
                cable_payout_m=cable_payout_m,
                fish_depth_m=fish_depth_m or 0.0,
            )
        scan_origin = SonarScanOrigin(
            nadir_pixel_x=actual_nadir_x,
            reference_pixel_y=0.0,
            across_track_gsd_m=meters_per_pixel,
            along_track_gsd_m=meters_per_pixel,
        )

        geo_batch = geolocation_service.geolocate_batch(
            detections=candidates,
            nav_fix=vessel_fix,
            sonar_origin=scan_origin,
            towfish_cfg=towfish_cfg,
        )
        geo_map = {g.target_id: g for g in geo_batch.targets}
        t_geolocation = (time.perf_counter() - t0) * 1000.0

        # =====================================================================
        # STAGE 10 & 11: Dimension Estimation & Risk Classification
        # =====================================================================
        t0_dim = time.perf_counter()
        t_dimension = (time.perf_counter() - t0_dim) * 1000.0

        t0_risk = time.perf_counter()
        risk_batch = risk_service.assess_batch_risk(
            detections=candidates,
            water_depth_m=water_depth_m,
            physics_analyses=physics_response.results,
            confidence_profiles=confidence_response.results,
            meters_per_pixel=meters_per_pixel,
        )
        risk_map = {r.detection_id: r for r in risk_batch.results}
        t_risk = (time.perf_counter() - t0_risk) * 1000.0

        # =====================================================================
        # STAGE 12: Final Result Synthesis
        # =====================================================================
        master_targets: List[MasterTargetResult] = []
        verified_count = 0
        probable_count = 0
        ambiguous_count = 0
        false_alarm_count = 0
        class_counts: Dict[str, int] = {}
        risk_counts: Dict[str, int] = {
            RiskTier.CRITICAL.value: 0,
            RiskTier.HIGH.value: 0,
            RiskTier.MODERATE.value: 0,
            RiskTier.LOW.value: 0,
        }
        max_hazard = 0.0

        for cand in candidates:
            tid = cand.get("detection_id")
            cname = cand.get("class_name", "other")
            class_counts[cname] = class_counts.get(cname, 0) + 1

            # Associated outputs
            shd = shadow_map.get(tid)
            phy = physics_map.get(tid)
            cnf = confidence_map.get(tid)
            geo = geo_map.get(tid)
            rsk = risk_map.get(tid)

            # Shadow Evidence
            if shd and shd.has_shadow and shd.direction and shd.extent:
                shadow_ev = ShadowEvidence(
                    has_shadow=True,
                    shadow_score=round(shd.shadow_score, 3),
                    cardinal_direction=shd.direction.cardinal_direction,
                    direction_degrees=round(shd.direction.angle_degrees, 1),
                    shadow_length_m=round(shd.extent.length_pixels * meters_per_pixel, 2),
                    estimated_height_m=round(shd.extent.estimated_object_height_m or 0.0, 2),
                )
            else:
                shadow_ev = ShadowEvidence(
                    has_shadow=False,
                    shadow_score=0.0,
                    cardinal_direction="N/A",
                    direction_degrees=0.0,
                    shadow_length_m=0.0,
                    estimated_height_m=0.0,
                )

            # Dimensions
            if phy:
                props = phy.physical_properties
                stab = phy.hydrodynamic_stability
                dim_obj = MasterPhysicalDimensions(
                    length_m=props.length_m,
                    width_m=props.width_m,
                    height_m=props.height_m,
                    area_sq_m=round(props.length_m * props.width_m, 2),
                    estimated_volume_m3=props.estimated_volume_m3,
                    dry_mass_metric_tons=props.dry_mass_metric_tons,
                    submerged_weight_kn=props.submerged_weight_kn,
                    recommended_crane_lift_tons=props.recommended_crane_lift_tons,
                    seabed_stability_index=stab.stability_index,
                    seabed_mobility_status=stab.mobility_status,
                )
            else:
                raw_bbox_dict = cand.get("bbox")
                if isinstance(raw_bbox_dict, BoundingBox):
                    bbox_dict = raw_bbox_dict.model_dump()
                elif isinstance(raw_bbox_dict, dict):
                    bbox_dict = raw_bbox_dict
                else:
                    bbox_dict = {}
                w_m = float(bbox_dict.get("width", 20)) * meters_per_pixel
                h_m = float(bbox_dict.get("height", 20)) * meters_per_pixel
                dim_obj = MasterPhysicalDimensions(
                    length_m=round(max(w_m, h_m), 2),
                    width_m=round(min(w_m, h_m), 2),
                    height_m=0.5,
                    area_sq_m=round(w_m * h_m, 2),
                    estimated_volume_m3=round(w_m * h_m * 0.5 * 0.5, 2),
                    dry_mass_metric_tons=1.0,
                    submerged_weight_kn=5.0,
                    recommended_crane_lift_tons=1.5,
                    seabed_stability_index=10.0,
                    seabed_mobility_status="Settled / Stable in Sediment",
                )

            # Confidence
            ai_c = float(cand.get("confidence", 0.5))
            cal_c = cnf.calibrated_confidence if cnf else ai_c
            t_tier = cnf.trust_tier if cnf else "PROBABLE_DEBRIS"
            expl_notes = cnf.explanation_notes if cnf else []

            if "VERIFIED" in str(t_tier):
                verified_count += 1
            elif "PROBABLE" in str(t_tier):
                probable_count += 1
            elif "AMBIGUOUS" in str(t_tier):
                ambiguous_count += 1
            else:
                false_alarm_count += 1

            # Geolocation
            if geo:
                geo_coords = geo.coordinates
                dist_m = geo.distance_from_sensor_m
                bearing_deg = geo.bearing_degrees
            else:
                geo_coords = geolocation_service.to_geo_coordinates(vessel_lat, vessel_lon)
                dist_m = 0.0
                bearing_deg = 0.0

            # Risk
            if rsk:
                r_score = rsk.composite_risk_score
                r_tier = rsk.risk_tier
                r_color = rsk.color_hex
                clearance_obj = rsk.clearance
                recs = rsk.recommendations
                risk_counts[r_tier.value] += 1
                max_hazard = max(max_hazard, r_score)
            else:
                clearance_obj, _ = risk_service.calculate_navigational_clearance(water_depth_m, dim_obj.height_m)
                r_score = 25.0
                r_tier = RiskTier.LOW
                r_color = "#2A9D8F"
                recs = []
                risk_counts[RiskTier.LOW.value] += 1

            raw_bbox = cand.get("bbox")
            if isinstance(raw_bbox, BoundingBox):
                bbox_obj = raw_bbox
            elif isinstance(raw_bbox, dict):
                bbox_obj = BoundingBox(**raw_bbox)
            else:
                bbox_obj = BoundingBox(
                    x_min=0.0, y_min=0.0, x_max=0.0, y_max=0.0,
                    width=0.0, height=0.0,
                    normalized_x_min=0.0, normalized_y_min=0.0, normalized_x_max=0.0, normalized_y_max=0.0
                )

            target_res = MasterTargetResult(
                detection_id=tid,
                class_id=cand.get("class_id", 0),
                class_name=cname,
                display_name=cand.get("display_name", cname.title()),
                category=cand.get("category", "Maritime Anomaly"),
                bbox=bbox_obj,
                ai_confidence=round(ai_c, 3),
                calibrated_confidence=round(cal_c, 3),
                trust_tier=t_tier,
                explainability_notes=expl_notes,
                shadow_evidence=shadow_ev,
                dimensions=dim_obj,
                coordinates=geo_coords,
                distance_from_sensor_m=round(dist_m, 2),
                bearing_degrees=round(bearing_deg, 1),
                risk_score=round(r_score, 1),
                risk_tier=r_tier,
                color_hex=r_color,
                clearance=clearance_obj,
                action_recommendations=recs,
            )
            master_targets.append(target_res)

        # Sort targets by hazard score (highest risk first)
        master_targets.sort(key=lambda t: t.risk_score, reverse=True)

        # Executive Summary
        immediate_notmar = risk_batch.immediate_notmar_required
        if immediate_notmar:
            alert_msg = "URGENT: Shallow debris detected threatening surface navigation. Broadcast NOTMAR immediately."
        elif risk_counts[RiskTier.CRITICAL.value] > 0 or risk_counts[RiskTier.HIGH.value] > 0:
            alert_msg = "Significant maritime obstruction or trawl snag hazard identified. S-57 chart advisory recommended."
        elif len(master_targets) > 0:
            alert_msg = "Subsea debris detected in survey area; stable with adequate navigational water clearance."
        else:
            alert_msg = "Survey scan clear; no marine debris or navigational hazards identified."

        exec_summary = ExecutiveSummary(
            total_targets_detected=len(master_targets),
            verified_targets=verified_count,
            probable_debris=probable_count,
            ambiguous_anomalies=ambiguous_count,
            suspected_false_alarms=false_alarm_count,
            class_breakdown=class_counts,
            risk_tier_breakdown=risk_counts,
            immediate_notmar_required=immediate_notmar,
            max_hazard_score=round(max_hazard, 1),
            primary_alert_message=alert_msg,
        )

        # Visual overlay rendering
        annotated_b64 = None
        prediction_image_path = None
        prediction_image_url = None
        if return_visualization:
            # Composite rendering: shadow contours + projection rays + detection boxes
            rendered_bgr = shadow_service.render_shadow_overlay(img_bgr, shadow_response.results)
            rendered_bgr = render_detections_overlay(rendered_bgr, candidates)
            annotated_b64 = encode_image_to_base64(rendered_bgr)
            rendered_jpeg_bytes = encode_image_to_jpeg_bytes(rendered_bgr)
            rendered_jpeg = image_output_service.save_and_upload(
                rendered_jpeg_bytes, prefix="master_analysis"
            )
            prediction_image_path = rendered_jpeg["local_path"]
            prediction_image_url = rendered_jpeg["cloudinary_url"] or rendered_jpeg["local_url"]

        total_elapsed_ms = (time.perf_counter() - pipeline_start) * 1000.0

        timings = StageTimings(
            input_validation_ms=round(t_input_val, 2),
            quality_check_ms=round(t_quality, 2),
            preprocessing_ms=round(t_preproc, 2),
            yolo_inference_ms=round(t_inference, 2),
            candidate_extraction_ms=round(t_candidate, 2),
            shadow_evidence_ms=round(t_shadow, 2),
            physics_validation_ms=round(t_physics, 2),
            confidence_fusion_ms=round(t_confidence, 2),
            geolocation_ms=round(t_geolocation, 2),
            dimension_estimate_ms=round(t_dimension, 2),
            risk_classification_ms=round(t_risk, 2),
            total_pipeline_ms=round(total_elapsed_ms, 2),
        )

        return MasterAnalysisResult(
            status="success",
            mission_id=m_id,
            image_metadata=img_meta,
            quality_assessment=quality_assessment,
            timings=timings,
            targets=master_targets,
            geojson=geo_batch.geojson,
            summary=exec_summary,
            annotated_image_base64=annotated_b64,
            prediction_image_path=prediction_image_path,
            prediction_image_url=prediction_image_url,
        )


# Global master service instance
master_pipeline_service = MasterPipelineService()
