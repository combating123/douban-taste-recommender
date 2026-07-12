from __future__ import annotations

import json
import urllib.request
from collections.abc import Iterable
from urllib.parse import quote, urlencode

from ..douban_sources import build_url_opener


_CACHE: dict[str, str] = {}
_NEGATIVE_CACHE: set[str] = set()


def resolve_public_people_photos(names: Iterable[str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    unique_names: list[str] = []
    for raw_name in names or ():
        name = str(raw_name or "").strip()
        if name and name not in unique_names:
            unique_names.append(name)
    if not unique_names:
        return resolved

    opener = build_url_opener()
    for name in unique_names[:8]:
        if name in _CACHE:
            resolved[name] = _CACHE[name]
            continue
        if name in _NEGATIVE_CACHE:
            continue
        image = _wikipedia_photo(name, opener) or _jikan_photo(name, opener)
        if image:
            _CACHE[name] = image
            resolved[name] = image
        else:
            _NEGATIVE_CACHE.add(name)
    return resolved


def _wikipedia_photo(name: str, opener) -> str:
    languages = (
        ("zh", "en", "ja", "ko")
        if any(ord(character) > 127 for character in name)
        else ("en", "zh", "ja", "ko")
    )
    for language in languages:
        url = f"https://{language}.wikipedia.org/api/rest_v1/page/summary/{quote(name, safe='')}"
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "CineScopeLocalPersonalRecommender/3.0",
                "Accept": "application/json",
            },
        )
        try:
            with opener.open(request, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8", "ignore"))
        except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
            continue
        for key in ("thumbnail", "originalimage"):
            nested = payload.get(key) if isinstance(payload, dict) else None
            image = str(nested.get("source") or "").strip() if isinstance(nested, dict) else ""
            if image.startswith("https://"):
                return image
    return ""


def _jikan_photo(name: str, opener) -> str:
    url = "https://api.jikan.moe/v4/people?" + urlencode({"q": name, "limit": "1"})
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CineScopeLocalPersonalRecommender/3.0",
            "Accept": "application/json",
        },
    )
    try:
        with opener.open(request, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore"))
    except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
        return ""
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return ""
    for row in rows:
        images = row.get("images") if isinstance(row, dict) else None
        jpg = images.get("jpg") if isinstance(images, dict) else None
        image = str(jpg.get("image_url") or "").strip() if isinstance(jpg, dict) else ""
        if image.startswith("https://") and "cdn.myanimelist.net" in image:
            return image
    return ""
