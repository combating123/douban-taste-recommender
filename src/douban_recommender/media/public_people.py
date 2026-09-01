from __future__ import annotations

import html
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from collections.abc import Iterable
from urllib.parse import quote, urlencode

from ..douban_sources import build_url_opener


_CACHE: dict[str, str] = {}
_NEGATIVE_CACHE: dict[str, float] = {}
NEGATIVE_CACHE_TTL_SECONDS = 120.0


def resolve_public_people_photos(names: Iterable[str], work_context: Iterable[str] = ()) -> dict[str, str]:
    resolved: dict[str, str] = {}
    works = tuple(str(value or "").strip() for value in work_context or () if str(value or "").strip())
    unique_names: list[str] = []
    for raw_name in names or ():
        name = str(raw_name or "").strip()
        if name and name not in unique_names:
            unique_names.append(name)
    if not unique_names:
        return resolved

    opener = build_url_opener()
    for name in unique_names[:8]:
        cache_key = name if not works else f"{name}\u241f{'\u241e'.join(works)}"
        if cache_key in _CACHE:
            resolved[name] = _CACHE[cache_key]
            continue
        now = time.monotonic()
        negative_at = _NEGATIVE_CACHE.get(cache_key)
        if negative_at is not None and now - negative_at < NEGATIVE_CACHE_TTL_SECONDS:
            continue
        _NEGATIVE_CACHE.pop(cache_key, None)
        image = (
            (_tmdb_contextual_photo(name, works, opener) if works else "")
            or _tmdb_photo(name, opener)
            or _wikipedia_photo(name, opener)
            or _tvmaze_photo(name, opener)
            or _jikan_photo(name, opener)
        )
        if image:
            _CACHE[cache_key] = image
            resolved[name] = image
        else:
            _NEGATIVE_CACHE[cache_key] = now
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
        except (OSError, urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
            payload = {}
        for key in ("thumbnail", "originalimage"):
            nested = payload.get(key) if isinstance(payload, dict) else None
            image = str(nested.get("source") or "").strip() if isinstance(nested, dict) else ""
            if image.startswith("https://"):
                return image
        image = _wikipedia_search_photo(name, language, opener)
        if image:
            return image
    return ""


def _normalized_name(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(character for character in text if character.isalnum())


def _plausible_name_match(query: str, candidate: str) -> bool:
    left = _normalized_name(query)
    right = _normalized_name(candidate)
    if not left or not right:
        return False
    return left == right or (min(len(left), len(right)) >= 4 and (left in right or right in left))


def _wikipedia_search_photo(name: str, language: str, opener) -> str:
    url = f"https://{language}.wikipedia.org/w/api.php?" + urlencode({
        "action": "query",
        "generator": "search",
        "gsrsearch": name,
        "gsrnamespace": "0",
        "gsrlimit": "4",
        "prop": "pageimages",
        "piprop": "thumbnail|original",
        "pithumbsize": "720",
        "format": "json",
    })
    request = urllib.request.Request(url, headers={"User-Agent": "CineScopeLocalPersonalRecommender/3.0", "Accept": "application/json"})
    try:
        with opener.open(request, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore"))
    except (OSError, urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return ""
    pages = payload.get("query", {}).get("pages") if isinstance(payload, dict) else None
    if not isinstance(pages, dict):
        return ""
    rows = sorted((row for row in pages.values() if isinstance(row, dict)), key=lambda row: int(row.get("index") or 999))
    for row in rows:
        if not _plausible_name_match(name, row.get("title")):
            continue
        for key in ("thumbnail", "original"):
            nested = row.get(key)
            image = str(nested.get("source") or "").strip() if isinstance(nested, dict) else ""
            if image.startswith("https://"):
                return image
    return ""


def _tmdb_photo(name: str, opener) -> str:
    url = "https://www.themoviedb.org/search/person?" + urlencode({"query": name})
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CineScopeLocalPersonalRecommender/3.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.themoviedb.org/",
        },
    )
    try:
        with opener.open(request, timeout=6) as response:
            page = response.read().decode("utf-8", "ignore")
    except (OSError, urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return ""

    def attribute(markup: str, key: str) -> str:
        match = re.search(rf'\b{re.escape(key)}=["\']([^"\']+)["\']', markup, flags=re.I)
        return html.unescape(match.group(1)).strip() if match else ""

    expected = _normalized_name(name)
    for image_markup in re.findall(r"<img\b[^>]+>", page, flags=re.I | re.S):
        class_name = attribute(image_markup, "class")
        if "profile" not in class_name.casefold().split():
            continue
        candidate_name = attribute(image_markup, "alt") or attribute(image_markup, "title")
        if not expected or _normalized_name(candidate_name) != expected:
            continue
        image = attribute(image_markup, "src")
        if not image.startswith("https://media.themoviedb.org/t/p/"):
            continue
        return re.sub(r"/t/p/[^/]+/", "/t/p/h632/", image, count=1)
    return ""


def _tmdb_contextual_photo(name: str, work_context: Iterable[str], opener) -> str:
    works = [str(value or "").strip() for value in work_context or () if str(value or "").strip()]
    if not name or not works:
        return ""
    url = "https://www.themoviedb.org/search/person?" + urlencode({"query": name})
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CineScopeLocalPersonalRecommender/3.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.themoviedb.org/",
        },
    )
    try:
        with opener.open(request, timeout=6) as response:
            page = response.read().decode("utf-8", "ignore")
    except (OSError, urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return ""

    cards = re.findall(
        r'(<div\b[^>]*class=["\'][^"\']*\bitem\b[^"\']*\bprofile\b[^"\']*\blist_item\b[^"\']*["\'][^>]*>.*?)(?=<div\b[^>]*class=["\'][^"\']*\bitem\b[^"\']*\bprofile\b[^"\']*\blist_item\b|\Z)',
        page,
        flags=re.I | re.S,
    )
    expected_person = _normalized_name(name)
    expected_works = [_normalized_name(value) for value in works if _normalized_name(value)]
    matches: list[str] = []
    for card in cards:
        image_markup = next(iter(re.findall(r"<img\b[^>]+>", card, flags=re.I | re.S)), "")
        if not image_markup:
            continue

        def attribute(markup: str, key: str) -> str:
            match = re.search(rf'\b{re.escape(key)}=["\']([^"\']+)["\']', markup, flags=re.I)
            return html.unescape(match.group(1)).strip() if match else ""

        candidate_name = attribute(image_markup, "alt")
        candidate_key = _normalized_name(candidate_name)
        if not expected_person or candidate_key != expected_person:
            continue
        sub_match = re.search(r'<p\b[^>]*class=["\'][^"\']*\bsub\b[^"\']*["\'][^>]*>(.*?)</p>', card, flags=re.I | re.S)
        sub_markup = sub_match.group(1) if sub_match else ""
        known_works = []
        for anchor in re.findall(r"<a\b[^>]*>.*?</a>", sub_markup, flags=re.I | re.S):
            title = attribute(anchor, "title") or attribute(anchor, "alt")
            if not title:
                title = html.unescape(re.sub(r"<[^>]+>", "", anchor)).strip()
            normalized = _normalized_name(title)
            if normalized:
                known_works.append(normalized)
        work_match = any(
            expected == known
            or (min(len(expected), len(known)) >= 4 and (expected in known or known in expected))
            for expected in expected_works
            for known in known_works
        )
        if not work_match:
            continue
        image = attribute(image_markup, "src")
        if image.startswith("https://media.themoviedb.org/t/p/"):
            promoted = re.sub(r"/t/p/[^/]+/", "/t/p/h632/", image, count=1)
            if promoted not in matches:
                matches.append(promoted)
    return matches[0] if len(matches) == 1 else ""


def _tvmaze_photo(name: str, opener) -> str:
    url = "https://api.tvmaze.com/search/people?" + urlencode({"q": name})
    request = urllib.request.Request(url, headers={"User-Agent": "CineScopeLocalPersonalRecommender/3.0", "Accept": "application/json"})
    try:
        with opener.open(request, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore"))
    except (OSError, urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, list):
        return ""
    for row in payload[:5]:
        person = row.get("person") if isinstance(row, dict) else None
        if not isinstance(person, dict) or not _plausible_name_match(name, person.get("name")):
            continue
        image_payload = person.get("image")
        if not isinstance(image_payload, dict):
            continue
        image = str(image_payload.get("original") or image_payload.get("medium") or "").strip()
        if image.startswith("https://") and "static.tvmaze.com" in image:
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
    except (OSError, urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
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
