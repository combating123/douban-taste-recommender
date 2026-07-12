from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from PIL import Image


CAPTURE_MODES = {"raw-device-pixels", "normalized-css-pixels"}
HEX40 = re.compile(r"^[0-9a-f]{40}$")


class EvidenceValidationError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_path(value: str) -> str:
    candidate = PurePosixPath(str(value).replace("\\", "/"))
    if candidate.is_absolute() or not candidate.parts or any(part in {"", ".", ".."} for part in candidate.parts):
        raise EvidenceValidationError(f"unsafe artifact path: {value}")
    return candidate.as_posix()


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise EvidenceValidationError(f"{label} must be numeric") from error
    if not math.isfinite(number) or (positive and number <= 0):
        raise EvidenceValidationError(f"{label} must be {'positive and ' if positive else ''}finite")
    return number


def _dimension_pair(value: Any, label: str) -> tuple[int, int]:
    if isinstance(value, Mapping):
        width = value.get("width")
        height = value.get("height")
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        width, height = value
    else:
        raise EvidenceValidationError(f"{label} must contain width and height")
    width_number = _number(width, f"{label}.width", positive=True)
    height_number = _number(height, f"{label}.height", positive=True)
    if not width_number.is_integer() or not height_number.is_integer():
        raise EvidenceValidationError(f"{label} dimensions must be integers")
    return int(width_number), int(height_number)


def _rect(value: Any, label: str) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise EvidenceValidationError(f"{label} must be an object")
    return {key: _number(value.get(key), f"{label}.{key}") for key in ("left", "right", "top", "bottom", "width", "height")}


def _validate_bottom_nav(capture: Mapping[str, Any], visual: Mapping[str, float], path: str) -> None:
    nav = capture.get("bottom_nav")
    if not isinstance(nav, Mapping):
        raise EvidenceValidationError(f"{path}: bottom_nav metadata is required")
    expected_visible = bool(nav.get("expected_visible"))
    visible = bool(nav.get("visible"))
    if expected_visible != visible:
        raise EvidenceValidationError(f"{path}: bottom nav visibility did not match the declared viewport")
    if not visible:
        return
    if nav.get("within_viewport") is not True:
        raise EvidenceValidationError(f"{path}: bottom nav was not declared within the visual viewport")
    rect = _rect(nav.get("rect"), f"{path}.bottom_nav.rect")
    left = visual["offset_left"]
    top = visual["offset_top"]
    right = left + visual["width"]
    bottom = top + visual["height"]
    if rect["left"] < left - 2 or rect["right"] > right + 2 or rect["top"] < top - 2 or rect["bottom"] > bottom + 2:
        raise EvidenceValidationError(f"{path}: bottom nav bounds exceed the visual viewport")
    if abs(rect["bottom"] - bottom) > 2:
        raise EvidenceValidationError(f"{path}: visible bottom nav does not reach the viewport bottom")


def _validate_essential_rects(capture: Mapping[str, Any], visual: Mapping[str, float], path: str) -> None:
    essentials = capture.get("essential_rects")
    if not isinstance(essentials, list) or not essentials:
        raise EvidenceValidationError(f"{path}: essential_rects must be a nonempty list")
    left = visual["offset_left"]
    right = left + visual["width"]
    for index, entry in enumerate(essentials):
        if not isinstance(entry, Mapping):
            raise EvidenceValidationError(f"{path}: essential rect {index} must be an object")
        rect = _rect(entry.get("rect"), f"{path}.essential_rects[{index}].rect")
        if rect["left"] < left - 2 or rect["right"] > right + 2:
            raise EvidenceValidationError(f"{path}: essential rect {index} is horizontally clipped")
        dimensions = entry.get("dimensions")
        if not isinstance(dimensions, Mapping):
            raise EvidenceValidationError(f"{path}: essential rect {index} dimensions are required")
        client_width, _ = _dimension_pair(dimensions.get("client"), f"{path}.essential_rects[{index}].client")
        scroll_width, _ = _dimension_pair(dimensions.get("scroll"), f"{path}.essential_rects[{index}].scroll")
        if scroll_width > client_width + 2:
            raise EvidenceValidationError(f"{path}: essential rect {index} has clipped horizontal content")


def _validate_capture(path: Path, relative: str, capture: Mapping[str, Any], bundle_mode: str) -> None:
    mode = capture.get("capture_mode")
    if mode != bundle_mode:
        raise EvidenceValidationError(f"{relative}: mixed capture mode {mode!r}; bundle declares {bundle_mode!r}")
    requested_width, requested_height = _dimension_pair(capture.get("requested_viewport"), f"{relative}.requested_viewport")
    inner_width, inner_height = _dimension_pair(capture.get("inner_size"), f"{relative}.inner_size")
    if (requested_width, requested_height) != (inner_width, inner_height):
        raise EvidenceValidationError(f"{relative}: requested viewport and inner size differ")
    visual_source = capture.get("visual_viewport")
    if not isinstance(visual_source, Mapping):
        raise EvidenceValidationError(f"{relative}: visual_viewport metadata is required")
    visual = {
        "width": _number(visual_source.get("width"), f"{relative}.visual_viewport.width", positive=True),
        "height": _number(visual_source.get("height"), f"{relative}.visual_viewport.height", positive=True),
        "scale": _number(visual_source.get("scale"), f"{relative}.visual_viewport.scale", positive=True),
        "offset_left": _number(visual_source.get("offset_left"), f"{relative}.visual_viewport.offset_left"),
        "offset_top": _number(visual_source.get("offset_top"), f"{relative}.visual_viewport.offset_top"),
    }
    if abs(visual["width"] * visual["scale"] - inner_width) > 2 or abs(visual["height"] * visual["scale"] - inner_height) > 2:
        raise EvidenceValidationError(f"{relative}: visual viewport does not match the inner size")
    dpr = _number(capture.get("device_pixel_ratio"), f"{relative}.device_pixel_ratio", positive=True)
    declared_width, declared_height = _dimension_pair(capture.get("image_size"), f"{relative}.image_size")

    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                raise EvidenceValidationError(f"{relative}: screenshot is not a decoded PNG")
            decoded_width, decoded_height = image.size
            if mode == "raw-device-pixels":
                expected_width = round(inner_width * dpr)
                expected_height = round(inner_height * dpr)
            else:
                normalization = capture.get("normalization")
                if not isinstance(normalization, Mapping) or normalization.get("operation") != "resample":
                    raise EvidenceValidationError(f"{relative}: normalized capture must declare resample, never crop")
                source_width, source_height = _dimension_pair(normalization.get("source_size"), f"{relative}.normalization.source_size")
                if (source_width, source_height) != (round(inner_width * dpr), round(inner_height * dpr)):
                    raise EvidenceValidationError(f"{relative}: normalized capture source size does not preserve the full DPR raster")
                expected_width, expected_height = inner_width, inner_height
            if (decoded_width, decoded_height) != (expected_width, expected_height):
                raise EvidenceValidationError(
                    f"{relative}: expected {expected_width}x{expected_height} for {mode}, decoded {decoded_width}x{decoded_height}"
                )
            if (declared_width, declared_height) != (decoded_width, decoded_height):
                raise EvidenceValidationError(f"{relative}: declared image size does not match decoded PNG dimensions")
            marker = capture.get("edge_marker")
            if not isinstance(marker, Mapping):
                raise EvidenceValidationError(f"{relative}: edge marker metadata is required")
            x = int(_number(marker.get("x"), f"{relative}.edge_marker.x"))
            y = int(_number(marker.get("y"), f"{relative}.edge_marker.y"))
            expected_rgba = marker.get("rgba")
            tolerance = int(_number(marker.get("tolerance", 0), f"{relative}.edge_marker.tolerance"))
            if not isinstance(expected_rgba, list) or len(expected_rgba) != 4 or not all(isinstance(channel, int) and 0 <= channel <= 255 for channel in expected_rgba):
                raise EvidenceValidationError(f"{relative}: edge marker rgba must contain four byte values")
            if not (0 <= x < decoded_width and 0 <= y < decoded_height):
                raise EvidenceValidationError(f"{relative}: edge marker coordinate is outside the decoded image")
            if (x, y) != (decoded_width - 1, decoded_height - 1):
                raise EvidenceValidationError(f"{relative}: edge marker must be the decoded lower-right edge pixel")
            marker_rect = _rect(marker.get("css_rect"), f"{relative}.edge_marker.css_rect")
            visual_right = visual["offset_left"] + visual["width"]
            visual_bottom = visual["offset_top"] + visual["height"]
            if abs(marker_rect["right"] - visual_right) > 0.5 or abs(marker_rect["bottom"] - visual_bottom) > 0.5:
                raise EvidenceValidationError(f"{relative}: edge marker CSS rect does not reach the visual viewport edge")
            if abs(marker_rect["width"] - 1) > 0.25 or abs(marker_rect["height"] - 1) > 0.25:
                raise EvidenceValidationError(f"{relative}: edge marker CSS rect must be exactly one CSS pixel")
            if (
                abs((marker_rect["right"] - marker_rect["left"]) - marker_rect["width"]) > 0.25
                or abs((marker_rect["bottom"] - marker_rect["top"]) - marker_rect["height"]) > 0.25
            ):
                raise EvidenceValidationError(f"{relative}: edge marker CSS rect geometry is inconsistent")
            actual = image.convert("RGBA").getpixel((x, y))
            if any(abs(actual[index] - expected_rgba[index]) > tolerance for index in range(4)):
                raise EvidenceValidationError(f"{relative}: edge marker is missing at the declared right/bottom coordinate")
    except EvidenceValidationError:
        raise
    except Exception as error:
        raise EvidenceValidationError(f"{relative}: screenshot could not be decoded") from error

    document_viewport = capture.get("document_viewport")
    if not isinstance(document_viewport, Mapping):
        raise EvidenceValidationError(f"{relative}: document_viewport metadata is required")
    document_client = _dimension_pair(document_viewport.get("client"), f"{relative}.document_viewport.client")
    document_scroll = _dimension_pair(document_viewport.get("scroll"), f"{relative}.document_viewport.scroll")
    if document_client != (inner_width, inner_height):
        raise EvidenceValidationError(f"{relative}: document client viewport differs from the inner viewport")
    if document_scroll[0] > document_client[0] + 2:
        raise EvidenceValidationError(f"{relative}: document has horizontal overflow")
    _validate_bottom_nav(capture, visual, relative)
    _validate_essential_rects(capture, visual, relative)


def write_evidence_manifest(
    bundle_dir: str | Path,
    *,
    source_commit: str,
    source_tree: str,
    capture_mode: str,
    screenshot_captures: Mapping[str, Mapping[str, Any]],
    metadata: Mapping[str, Any] | None = None,
    manifest_name: str = "manifest.json",
) -> Path:
    bundle = Path(bundle_dir).resolve()
    bundle.mkdir(parents=True, exist_ok=True)
    if capture_mode not in CAPTURE_MODES:
        raise EvidenceValidationError(f"unsupported capture mode: {capture_mode}")
    manifest_path = bundle / manifest_name
    captures = {_relative_path(path): dict(value) for path, value in screenshot_captures.items()}
    artifacts = []
    files = sorted(path for path in bundle.rglob("*") if path.is_file() and path.resolve() != manifest_path.resolve())
    for path in files:
        relative = path.relative_to(bundle).as_posix()
        row: dict[str, Any] = {"path": relative, "bytes": path.stat().st_size, "sha256": _sha256(path)}
        if path.suffix.lower() == ".png":
            if relative not in captures:
                raise EvidenceValidationError(f"missing capture metadata for screenshot: {relative}")
            row["capture"] = captures[relative]
        artifacts.append(row)
    missing_captures = sorted(set(captures) - {row["path"] for row in artifacts})
    if missing_captures:
        raise EvidenceValidationError(f"capture metadata points to missing screenshot: {missing_captures[0]}")
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "source_commit": source_commit,
        "source_tree": source_tree,
        "capture_mode": capture_mode,
        "manifest_excludes_self": True,
        "artifacts": artifacts,
    }
    if metadata:
        for key, value in metadata.items():
            if key in manifest:
                raise EvidenceValidationError(f"metadata cannot replace manifest field: {key}")
            manifest[key] = value
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def validate_evidence_manifest(manifest_path: str | Path) -> dict[str, Any]:
    manifest_file = Path(manifest_path).resolve()
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8-sig"))
    except Exception as error:
        raise EvidenceValidationError("manifest could not be decoded") from error
    if not isinstance(manifest, Mapping) or manifest.get("schema_version") != 1:
        raise EvidenceValidationError("unsupported evidence manifest schema")
    source_commit = str(manifest.get("source_commit") or "")
    source_tree = str(manifest.get("source_tree") or "")
    if not HEX40.fullmatch(source_commit) or not HEX40.fullmatch(source_tree):
        raise EvidenceValidationError("manifest must bind a full source commit and tree")
    capture_mode = manifest.get("capture_mode")
    if capture_mode not in CAPTURE_MODES:
        raise EvidenceValidationError("manifest capture mode is invalid")
    if manifest.get("mandatory_edge_marker") is not True:
        raise EvidenceValidationError("manifest mandatory edge marker contract must be true")
    expected_screenshot_count = manifest.get("expected_screenshot_count")
    if (
        isinstance(expected_screenshot_count, bool)
        or not isinstance(expected_screenshot_count, int)
        or expected_screenshot_count < 0
    ):
        raise EvidenceValidationError("manifest expected screenshot count must be a nonnegative integer")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise EvidenceValidationError("manifest artifacts must be a list")
    bundle = manifest_file.parent
    listed: set[str] = set()
    screenshot_count = 0
    for row in artifacts:
        if not isinstance(row, Mapping):
            raise EvidenceValidationError("manifest artifact row must be an object")
        relative = _relative_path(str(row.get("path") or ""))
        if relative in listed:
            raise EvidenceValidationError(f"duplicate artifact path: {relative}")
        listed.add(relative)
        path = bundle.joinpath(*PurePosixPath(relative).parts)
        if not path.is_file():
            raise EvidenceValidationError(f"listed artifact is missing: {relative}")
        if row.get("bytes") != path.stat().st_size:
            raise EvidenceValidationError(f"artifact size mismatch: {relative}")
        if row.get("sha256") != _sha256(path):
            raise EvidenceValidationError(f"artifact hash mismatch: {relative}")
        if path.suffix.lower() == ".png":
            capture = row.get("capture")
            if not isinstance(capture, Mapping):
                raise EvidenceValidationError(f"missing capture metadata for screenshot: {relative}")
            _validate_capture(path, relative, capture, capture_mode)
            screenshot_count += 1
    actual = {
        path.relative_to(bundle).as_posix()
        for path in bundle.rglob("*")
        if path.is_file() and path.resolve() != manifest_file
    }
    unlisted = sorted(actual - listed)
    if unlisted:
        raise EvidenceValidationError(f"unlisted artifact is not hashed by the manifest: {unlisted[0]}")
    missing = sorted(listed - actual)
    if missing:
        raise EvidenceValidationError(f"manifest lists an absent artifact: {missing[0]}")
    if screenshot_count != expected_screenshot_count:
        raise EvidenceValidationError(
            f"manifest screenshot count mismatch: expected {expected_screenshot_count}, found {screenshot_count}"
        )
    return {
        "artifact_count": len(artifacts),
        "screenshot_count": screenshot_count,
        "capture_mode": capture_mode,
        "source_commit": source_commit,
        "source_tree": source_tree,
    }


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print("usage: python -m douban_recommender.evidence_validation <manifest.json>", file=sys.stderr)
        return 2
    try:
        summary = validate_evidence_manifest(arguments[0])
    except EvidenceValidationError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
