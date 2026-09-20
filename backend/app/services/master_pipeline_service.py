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
    SonarMetadataContext,
)
from app.schemas.detection import BoundingBox, TilingConfig
from app.schemas.sonar import SonarNavigationTrack
from app.schemas.preprocessing import PreprocessingConfig, PreprocessingPreset
from app.schemas.geolocation import (
    NavigationalFix,
    TowfishConfig,
    SonarScanOrigin,
    GeoJSONFeatureCollection,
)
from app.schemas.risk import RiskTier
from app.services.input_service import input_service, InputValidationError
from app.services.sonar_ingestion_service import sonar_ingestion_service, SonarIngestionError
from app.services.quality_service import quality_service
from app.services.preprocessing_service import preprocessing_service
from app.services.inference_service import inference_service
from app.services.anomaly_service import anomaly_service
from app.services.shadow_service import shadow_service
from app.services.physics_service import physics_service
from app.services.confidence_service import confidence_service
from app.services.geolocation_service import geolocation_service
from app.services.dimension_service import dimension_service
from app.services.risk_service import risk_service
from app.services.image_output_service import image_output_service
from app.services.sonar_artifact_service import sonar_artifact_service
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
        # Phase 5: Optional raw sonar ingestion parameters
        filename: Optional[str] = None,
        max_pings: Optional[int] = None,
        channels: Optional[List[int]] = None,
    ) -> MasterAnalysisResult:
        """
        Execute all 12 stages in sequence and return the synthesized intelligence result.
        Supports both standard marine imagery (JPEG, PNG, etc.) and raw sonar files (.xtf, .jsf).
        """
        pipeline_start = time.perf_counter()
        m_id = mission_id or f"msn_{uuid.uuid4().hex[:10]}"

        # =====================================================================
        # STAGE 1: Input Ingestion & Validation
        # =====================================================================
        t0 = time.perf_counter()
        sonar_context: Optional[SonarMetadataContext] = None
        navigation_track: Optional[SonarNavigationTrack] = None

        if sonar_ingestion_service.is_sonar_file(image_bytes, filename=filename):
            logger.info("Ingesting raw sonar stream (filename=%s)", filename)
            ingest_res = sonar_ingestion_service.ingest_sonar(
                image_bytes=image_bytes,
                filename=filename,
                max_pings=max_pings,
                channels=channels,
            )
            img_bgr = ingest_res.image_bgr
            img_meta = ingest_res.image_metadata
            sonar_context = ingest_res.sonar_context
            navigation_track = ingest_res.navigation_track

            # Persist stable waterfall raster artifact linked to mission_id (analysis ID)
            if ingest_res.waterfall_raster is not None:
                try:
                    artifact_meta = sonar_artifact_service.save_waterfall_artifact(
                        analysis_id=m_id,
                        raster=ingest_res.waterfall_raster,
                        metadata={
                            "sonar_format": sonar_context.format,
                            "filename": filename or sonar_context.filename,
                            "total_pings": sonar_context.total_pings,
                            "waterfall_width": sonar_context.waterfall_width,
                            "waterfall_height": sonar_context.waterfall_height,
                            "channel_layout": sonar_context.channel_layout,
                            "channels_included": sonar_context.channels_included,
                            "nadir_pixel_x": sonar_context.nadir_pixel_x,
                            "meters_per_pixel": sonar_context.meters_per_pixel,
                            "slant_range_m": sonar_context.slant_range_m,
                        },
                    )
                    sonar_context.artifact_id = artifact_meta["artifact_id"]
                    sonar_context.raster_reference = artifact_meta["relative_url"]
                    sonar_context.raster_path = artifact_meta["local_path"]
                except Exception as exc:
                    logger.warning("Failed to persist sonar waterfall artifact for %s: %s", m_id, exc)

            # Persist stable navigation track artifact linked to mission_id (analysis ID)
            if ingest_res.navigation_track is not None:
                try:
                    ingest_res.navigation_track.analysis_id = m_id
                    track_meta = sonar_artifact_service.save_track_artifact(
                        analysis_id=m_id,
                        track=ingest_res.navigation_track,
                        metadata={
                            "sonar_format": sonar_context.format,
                            "filename": filename or sonar_context.filename,
                            "total_pings": ingest_res.navigation_track.total_pings,
                            "available_navigation_pings": ingest_res.navigation_track.available_navigation_pings,
                        },
                    )
                    sonar_context.track_artifact_id = track_meta["artifact_id"]
                    sonar_context.track_reference = track_meta["relative_url"]
                except Exception as exc:
                    logger.warning("Failed to persist sonar navigation track artifact for %s: %s", m_id, exc)

            # Use calibrated sonar physical parameters if not explicitly overridden by caller
            if ingest_res.nadir_pixel_x is not None and nadir_x is None:
                nadir_x = ingest_res.nadir_pixel_x

            # If meters_per_pixel is recorded in sonar and caller used default 0.05
            if ingest_res.meters_per_pixel is not None and meters_per_pixel == 0.05:
                meters_per_pixel = ingest_res.meters_per_pixel

            if ingest_res.slant_range_m is not None and slant_range_m is None:
                slant_range_m = ingest_res.slant_range_m

            # Connect validated sonar navigation if present
            if ingest_res.navigation:
                if ingest_res.navigation.latitude is not None and ingest_res.navigation.longitude is not None:
                    vessel_lat = ingest_res.navigation.latitude
                    vessel_lon = ingest_res.navigation.longitude
                if ingest_res.navigation.heading_deg is not None:
                    vessel_heading_deg = ingest_res.navigation.heading_deg
                if ingest_res.navigation.altitude_m is not None and sensor_altitude_m is None:
                    sensor_altitude_m = ingest_res.navigation.altitude_m
                if ingest_res.navigation.depth_m is not None and fish_depth_m is None:
                    fish_depth_m = ingest_res.navigation.depth_m
        else:
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
        # STAGE 5: Candidate List Extraction (YOLO + open-set anomaly branch)
        # =====================================================================
        t0 = time.perf_counter()
        candidates = [d.model_dump() for d in det_response.detections]
        # Branch 2: merge feature-space anomaly candidates (P_CAE) not covered by YOLO.
        candidates = anomaly_service.merge_with(candidates, processed_bgr)
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

        if sonar_context is not None:
            geo_batch = geolocation_service.geolocate_sonar_detections(
                detections=candidates,
                navigation_track=navigation_track,
                nadir_pixel_x=actual_nadir_x,
                meters_per_pixel=meters_per_pixel,
                slant_range_m=slant_range_m,
                towfish_cfg=towfish_cfg,
                default_heading_deg=vessel_heading_deg,
            )
        else:
            geo_batch = geolocation_service.geolocate_batch(
                detections=candidates,
                nav_fix=vessel_fix,
                sonar_origin=scan_origin,
                towfish_cfg=towfish_cfg,
            )
        geo_map = {g.target_id: g for g in geo_batch.targets}
        t_geolocation = (time.perf_counter() - t0) * 1000.0

        # =====================================================================
        # STAGE 10: Dimension Estimation
        # =====================================================================
        t0_dim = time.perf_counter()
        dim_map = dimension_service.estimate_batch_dimensions(
            candidates=candidates,
            meters_per_pixel=meters_per_pixel,
            shadow_results=shadow_response.results,
            physics_results=physics_response.results,
            sonar_context=sonar_context,
            navigation_track=navigation_track,
            sensor_altitude_m=sensor_altitude_m,
            slant_range_m=slant_range_m,
        )
        t_dimension = (time.perf_counter() - t0_dim) * 1000.0

        # =====================================================================
        # STAGE 11: Risk Classification & NOTMAR Directives
        # =====================================================================
        t0_risk = time.perf_counter()
        risk_batch = risk_service.assess_batch_risk(
            detections=candidates,
            water_depth_m=water_depth_m,
            physics_analyses=physics_response.results,
            confidence_profiles=confidence_response.results,
            meters_per_pixel=meters_per_pixel,
            geo_map=geo_map,
            dim_map=dim_map,
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
            dim_obj = dim_map.get(tid)
            if dim_obj is None:
                dim_obj = dimension_service.estimate_target_dimensions(
                    candidate=cand,
                    meters_per_pixel=meters_per_pixel,
                    shadow_result=shd,
                    physics_result=phy,
                    sonar_context=sonar_context,
                    navigation_track=navigation_track,
                    sensor_altitude_m=sensor_altitude_m,
                    slant_range_m=slant_range_m,
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
                georef = geo.georeference
            else:
                if sonar_context is not None:
                    geo_coords = None
                    dist_m = None
                    bearing_deg = None
                    georef = None
                else:
                    geo_coords = geolocation_service.to_geo_coordinates(vessel_lat, vessel_lon)
                    dist_m = 0.0
                    bearing_deg = 0.0
                    georef = None

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
                distance_from_sensor_m=round(dist_m, 2) if dist_m is not None else None,
                bearing_degrees=round(bearing_deg, 1) if bearing_deg is not None else None,
                risk_score=round(r_score, 1),
                risk_tier=r_tier,
                color_hex=r_color,
                clearance=clearance_obj,
                action_recommendations=recs,
                georeference=georef,
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
            # Composite rendering: shadow contours + projection rays + detection boxes with risk/dimension tags
            overlay_candidates = []
            target_map = {t.detection_id: t for t in master_targets}
            for cand in candidates:
                c_copy = dict(cand)
                tid = cand.get("detection_id")
                if tid in risk_map:
                    c_copy["risk_tier"] = risk_map[tid].risk_tier
                if tid in dim_map:
                    c_copy["dimensions"] = dim_map[tid]
                if tid in geo_map:
                    c_copy["georeference"] = geo_map[tid].georeference
                    c_copy["coordinates"] = geo_map[tid].coordinates
                # Trust tier + fused confidence so the overlay reflects the decision, not raw scores
                if tid in target_map:
                    c_copy["trust_tier"] = target_map[tid].trust_tier
                    c_copy["calibrated_confidence"] = target_map[tid].calibrated_confidence
                overlay_candidates.append(c_copy)

            rejected_ids = {
                t.detection_id for t in master_targets
                if str(getattr(t.trust_tier, "value", t.trust_tier)) == "SUSPECTED_FALSE_ALARM"
            }
            rendered_bgr = shadow_service.render_shadow_overlay(
                img_bgr, shadow_response.results, skip_detection_ids=rejected_ids
            )
            rendered_bgr = render_detections_overlay(rendered_bgr, overlay_candidates)
            rendered_jpeg_bytes = encode_image_to_jpeg_bytes(rendered_bgr)
            # Inline base64 for direct browser consumption (used by tests + frontend)
            annotated_b64 = image_output_service.as_data_url(rendered_jpeg_bytes)
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
            sonar_metadata=sonar_context,
        )


# Global master service instance
master_pipeline_service = MasterPipelineService()
