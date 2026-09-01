from __future__ import annotations

import hashlib
import io

from PIL import Image, UnidentifiedImageError

from .models import ValidatedImage


FORMAT_MAP = {
    "JPEG": (".jpg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "WEBP": (".webp", "image/webp"),
}


class MediaValidationError(ValueError):
    pass


def _looks_like_document(data: bytes) -> bool:
    prefix = data[:128].lstrip().lower()
    return prefix.startswith((b"<html", b"<!doctype", b"<?xml", b"{", b"["))


def validate_image_bytes(
    data: bytes,
    declared_type: str = "",
    min_width: int = 80,
    min_height: int = 80,
    kind: str = "",
) -> ValidatedImage:
    payload = bytes(data or b"")
    if not payload or _looks_like_document(payload):
        raise MediaValidationError("response is not an image")

    content_type = str(declared_type or "").split(";", 1)[0].strip().lower()
    if content_type and not content_type.startswith("image/"):
        raise MediaValidationError(f"declared content type is not an image: {content_type}")

    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.verify()
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            width, height = image.size
            image_format = str(image.format or "").upper()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise MediaValidationError("response is not a decodable image") from exc

    if image_format not in FORMAT_MAP:
        raise MediaValidationError(f"unsupported image format: {image_format or 'unknown'}")
    if width < int(min_width) or height < int(min_height):
        raise MediaValidationError(f"image too small: {width}x{height}")

    extension, mime_type = FORMAT_MAP[image_format]
    validated = ValidatedImage(
        data=payload,
        mime_type=mime_type,
        extension=extension,
        width=int(width),
        height=int(height),
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    validate_image_kind(validated, kind)
    return validated


def validate_image_kind(image: ValidatedImage, kind: str) -> None:
    normalized = str(kind or "").strip().casefold()
    width = int(image.width)
    height = int(image.height)
    if normalized == "poster":
        if width < 180 or height < 250 or (height / max(width, 1)) < 1.15:
            raise MediaValidationError(f"poster dimensions are invalid: {width}x{height}")
    elif normalized == "portrait":
        if width < 96 or height < 96:
            raise MediaValidationError(f"portrait dimensions are invalid: {width}x{height}")
