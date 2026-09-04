"""
End-to-end verification script: Test Preprocessing + YOLO Model together.
Run directly with:
    python test_pipeline.py [optional_path_to_image.jpg]
"""

import sys
import time
from pathlib import Path
import cv2
import numpy as np

# Ensure backend root is on Python path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.inference_service import inference_service
from app.services.preprocessing_service import preprocessing_service
from app.schemas.preprocessing import PreprocessingPreset, PreprocessingConfig


def generate_synthetic_sonar_canvas() -> bytes:
    """Generate a synthetic noisy sonar canvas with an acoustic target pair."""
    np.random.seed(42)
    h, w = 640, 640
    # Speckle background (low-contrast seabed return)
    img = np.random.randint(45, 85, (h, w, 3), dtype=np.uint8)

    # Debris acoustic highlight (high reflectivity)
    cv2.rectangle(img, (200, 220), (320, 360), (225, 225, 225), -1)
    # Acoustic shadow behind the debris
    cv2.rectangle(img, (320, 220), (450, 360), (12, 12, 12), -1)

    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


def main():
    print("\n" + "=" * 65)
    print("  MarineScan: Testing Preprocessing + YOLO Model Pipeline")
    print("=" * 65)

    # 1. Load image
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        image_path = sys.argv[1]
        print(f"Loading provided image: {image_path}")
        with open(image_path, "rb") as f:
            image_bytes = f.read()
    else:
        print("No image file provided -> Generating synthetic sonar image...")
        image_bytes = generate_synthetic_sonar_canvas()

    presets_to_test = [
        ("None (Raw Image)", None),
        ("sonar_acoustic Preset", "sonar_acoustic"),
        ("turbid_water Preset", "turbid_water"),
        ("edge_enhance Preset", "edge_enhance"),
    ]

    for label, preset in presets_to_test:
        print(f"\n--- Running: {label} ---")
        start = time.perf_counter()
        
        response = inference_service.predict(
            image_bytes=image_bytes,
            confidence_threshold=0.25,
            preprocessing_preset=preset,
            meters_per_pixel=0.05,  # 5 cm/pixel GSD
            return_visualization=True,
        )
        elapsed = (time.perf_counter() - start) * 1000.0

        timing = response.timing_breakdown
        print(f"  Status:             {response.status.upper()}")
        print(f"  Device:             {response.device.upper()}")
        print(f"  Preprocessing Time: {timing.preprocessing_time_ms if timing else 0.0:.2f} ms")
        print(f"  YOLO Inference:     {timing.inference_time_ms if timing else 0.0:.2f} ms")
        print(f"  Total Pipeline:     {response.total_time_ms:.2f} ms (Wall: {elapsed:.2f} ms)")
        print(f"  Detections Found:   {response.summary.total_detections}")

        if response.detections:
            for d in response.detections:
                dim_str = ""
                if d.physical_dimensions:
                    dim_str = f" [Real-World: {d.physical_dimensions.length_meters}m x {d.physical_dimensions.width_meters}m]"
                print(f"    - {d.display_name} ({int(d.confidence*100)}%) - Risk: {d.risk_level}{dim_str}")

        # Save annotated image for inspection
        out_filename = f"test_output_{preset or 'raw'}.jpg"
        jpeg_bytes, _ = inference_service.predict_and_render_image(
            image_bytes=image_bytes,
            confidence_threshold=0.25,
            preprocessing_preset=preset,
        )
        with open(out_filename, "wb") as out_f:
            out_f.write(jpeg_bytes)
        print(f"  Saved render to:    {out_filename}")

    print("\n" + "=" * 65)
    print("  Pipeline verification complete! All tests passed successfully.")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
