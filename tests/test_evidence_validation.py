import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from douban_recommender.evidence_validation import (
    EvidenceValidationError,
    validate_evidence_manifest,
    write_evidence_manifest,
)


SOURCE_COMMIT = "1" * 40
SOURCE_TREE = "2" * 40


def marker_record(width=390, height=844, *, x=None, y=None, rgba=None):
    x = width - 1 if x is None else x
    y = height - 1 if y is None else y
    return {
        "x": x,
        "y": y,
        "rgba": rgba or [255, 0, 255, 255],
        "tolerance": 0,
        "css_rect": {"left": width - 1, "top": height - 1, "right": width, "bottom": height, "width": 1, "height": 1},
    }


def manifest_metadata(expected_screenshot_count):
    return {"mandatory_edge_marker": True, "expected_screenshot_count": expected_screenshot_count}


def capture_record(
    *,
    width=390,
    height=844,
    dpr=1,
    image_width=None,
    image_height=None,
    mode="raw-device-pixels",
    marker=None,
):
    image_width = image_width if image_width is not None else round(width * dpr)
    image_height = image_height if image_height is not None else round(height * dpr)
    record = {
        "surface": "v3",
        "capture_mode": mode,
        "requested_viewport": {"width": width, "height": height},
        "inner_size": {"width": width, "height": height},
        "visual_viewport": {"width": width, "height": height, "scale": 1, "offset_left": 0, "offset_top": 0},
        "device_pixel_ratio": dpr,
        "image_size": {"width": image_width, "height": image_height},
        "document_viewport": {"client": [width, height], "scroll": [width, 1600]},
        "bottom_nav": {
            "expected_visible": True,
            "visible": True,
            "within_viewport": True,
            "rect": {"left": 0, "right": width, "top": height - 68, "bottom": height, "width": width, "height": 68},
        },
        "essential_rects": [
            {
                "path": "html>body>main>h1",
                "dimensions": {"client": [width - 32, 52], "scroll": [width - 32, 52]},
                "rect": {"left": 16, "right": width - 16, "top": 20, "bottom": 72, "width": width - 32, "height": 52},
            }
        ],
    }
    if mode == "normalized-css-pixels":
        record["normalization"] = {"operation": "resample", "source_size": [round(width * dpr), round(height * dpr)]}
    if marker:
        record["edge_marker"] = marker
    return record


class EvidenceValidationTests(unittest.TestCase):
    def test_validates_raw_capture_geometry_hashes_bottom_nav_and_edge_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            screenshot = bundle / "screenshots" / "390x844" / "health.png"
            screenshot.parent.mkdir(parents=True)
            image = Image.new("RGBA", (390, 844), (12, 18, 32, 255))
            image.putpixel((389, 843), (255, 0, 255, 255))
            image.save(screenshot, format="PNG")
            (bundle / "browser-smoke.json").write_text(json.dumps({"rows": 1}), encoding="utf-8")
            marker = marker_record()
            manifest_path = write_evidence_manifest(
                bundle,
                source_commit=SOURCE_COMMIT,
                source_tree=SOURCE_TREE,
                capture_mode="raw-device-pixels",
                screenshot_captures={"screenshots/390x844/health.png": capture_record(marker=marker)},
                metadata=manifest_metadata(1),
            )

            summary = validate_evidence_manifest(manifest_path)

            self.assertEqual(2, summary["artifact_count"])
            self.assertEqual(1, summary["screenshot_count"])
            self.assertEqual("raw-device-pixels", summary["capture_mode"])

    def test_rejects_dpr_one_point_five_left_top_crop_saved_at_css_dimensions(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            screenshot = bundle / "screenshots" / "390x844" / "cropped.png"
            screenshot.parent.mkdir(parents=True)
            Image.new("RGBA", (390, 844), (0, 0, 0, 255)).save(screenshot, format="PNG")
            manifest_path = write_evidence_manifest(
                bundle,
                source_commit=SOURCE_COMMIT,
                source_tree=SOURCE_TREE,
                capture_mode="raw-device-pixels",
                screenshot_captures={
                    "screenshots/390x844/cropped.png": capture_record(
                        dpr=1.5,
                        image_width=390,
                        image_height=844,
                    )
                },
                metadata=manifest_metadata(1),
            )

            with self.assertRaisesRegex(EvidenceValidationError, r"expected 585x1266.*decoded 390x844"):
                validate_evidence_manifest(manifest_path)

    def test_rejects_dimension_correct_raster_when_right_bottom_marker_is_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            screenshot = bundle / "screenshots" / "raw" / "missing-marker.png"
            screenshot.parent.mkdir(parents=True)
            Image.new("RGBA", (585, 1266), (0, 0, 0, 255)).save(screenshot, format="PNG")
            marker = marker_record(390, 844, x=584, y=1265)
            manifest_path = write_evidence_manifest(
                bundle,
                source_commit=SOURCE_COMMIT,
                source_tree=SOURCE_TREE,
                capture_mode="raw-device-pixels",
                screenshot_captures={"screenshots/raw/missing-marker.png": capture_record(dpr=1.5, marker=marker)},
                metadata=manifest_metadata(1),
            )

            with self.assertRaisesRegex(EvidenceValidationError, "edge marker"):
                validate_evidence_manifest(manifest_path)

    def test_rejects_screenshot_capture_when_edge_marker_metadata_is_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            screenshot = bundle / "screenshots" / "390x844" / "missing-marker-metadata.png"
            screenshot.parent.mkdir(parents=True)
            Image.new("RGBA", (390, 844), (12, 18, 32, 255)).save(screenshot, format="PNG")
            manifest_path = write_evidence_manifest(
                bundle,
                source_commit=SOURCE_COMMIT,
                source_tree=SOURCE_TREE,
                capture_mode="raw-device-pixels",
                screenshot_captures={
                    "screenshots/390x844/missing-marker-metadata.png": capture_record()
                },
                metadata=manifest_metadata(1),
            )

            with self.assertRaisesRegex(EvidenceValidationError, "edge marker metadata is required"):
                validate_evidence_manifest(manifest_path)

    def test_rejects_unlisted_artifacts_added_after_manifest_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            (bundle / "result.json").write_text("{}", encoding="utf-8")
            manifest_path = write_evidence_manifest(
                bundle,
                source_commit=SOURCE_COMMIT,
                source_tree=SOURCE_TREE,
                capture_mode="raw-device-pixels",
                screenshot_captures={},
                metadata=manifest_metadata(0),
            )
            (bundle / "unlisted.txt").write_text("not hashed", encoding="utf-8")

            with self.assertRaisesRegex(EvidenceValidationError, "unlisted artifact"):
                validate_evidence_manifest(manifest_path)

    def test_rejects_matching_marker_that_is_not_the_lower_right_edge(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            screenshot = bundle / "screenshots" / "390x844" / "interior-marker.png"
            screenshot.parent.mkdir(parents=True)
            image = Image.new("RGBA", (390, 844), (12, 18, 32, 255))
            image.putpixel((100, 100), (255, 0, 255, 255))
            image.save(screenshot, format="PNG")
            marker = marker_record(x=100, y=100)
            manifest_path = write_evidence_manifest(
                bundle,
                source_commit=SOURCE_COMMIT,
                source_tree=SOURCE_TREE,
                capture_mode="raw-device-pixels",
                screenshot_captures={"screenshots/390x844/interior-marker.png": capture_record(marker=marker)},
                metadata=manifest_metadata(1),
            )

            with self.assertRaisesRegex(EvidenceValidationError, "lower-right edge"):
                validate_evidence_manifest(manifest_path)

    def test_rejects_manifest_when_actual_screenshot_count_differs_from_declared_count(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            screenshot = bundle / "screenshots" / "390x844" / "health.png"
            screenshot.parent.mkdir(parents=True)
            image = Image.new("RGBA", (390, 844), (12, 18, 32, 255))
            image.putpixel((389, 843), (255, 0, 255, 255))
            image.save(screenshot, format="PNG")
            manifest_path = write_evidence_manifest(
                bundle,
                source_commit=SOURCE_COMMIT,
                source_tree=SOURCE_TREE,
                capture_mode="raw-device-pixels",
                screenshot_captures={"screenshots/390x844/health.png": capture_record(marker=marker_record())},
                metadata=manifest_metadata(2),
            )

            with self.assertRaisesRegex(EvidenceValidationError, "screenshot count"):
                validate_evidence_manifest(manifest_path)

    def test_rejects_manifest_that_does_not_require_edge_markers(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            screenshot = bundle / "screenshots" / "390x844" / "health.png"
            screenshot.parent.mkdir(parents=True)
            image = Image.new("RGBA", (390, 844), (12, 18, 32, 255))
            image.putpixel((389, 843), (255, 0, 255, 255))
            image.save(screenshot, format="PNG")
            manifest_path = write_evidence_manifest(
                bundle,
                source_commit=SOURCE_COMMIT,
                source_tree=SOURCE_TREE,
                capture_mode="raw-device-pixels",
                screenshot_captures={"screenshots/390x844/health.png": capture_record(marker=marker_record())},
                metadata={"mandatory_edge_marker": False, "expected_screenshot_count": 1},
            )

            with self.assertRaisesRegex(EvidenceValidationError, "mandatory edge marker"):
                validate_evidence_manifest(manifest_path)


if __name__ == "__main__":
    unittest.main()
