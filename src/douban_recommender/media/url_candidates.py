from __future__ import annotations

import re
from urllib.parse import SplitResult, urlsplit, urlunsplit


BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
DOUBAN_IMAGE_HOSTS = (
    "img9.doubanio.com",
    "img1.doubanio.com",
    "img2.doubanio.com",
    "img3.doubanio.com",
)
WIKIMEDIA_THUMB_WIDTHS = (640, 330)


def image_request_headers(url: str) -> dict[str, str]:
    parsed = _http_url(url)
    host = (parsed.hostname or "").lower() if parsed else ""
    headers = {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    }
    if host == "douban.com" or host.endswith(".douban.com") or host.endswith(".doubanio.com"):
        headers["Referer"] = "https://movie.douban.com/"
    elif host == "upload.wikimedia.org":
        headers["Referer"] = "https://commons.wikimedia.org/"
    elif host == "image.tmdb.org":
        headers["Referer"] = "https://www.themoviedb.org/"
    elif host.endswith(".anilist.co") or host.endswith(".anilistcdn.com"):
        headers["Referer"] = "https://anilist.co/"
    elif host.endswith(".myanimelist.net"):
        headers["Referer"] = "https://myanimelist.net/"
    elif host.endswith(".tvmaze.com"):
        headers["Referer"] = "https://www.tvmaze.com/"
    return headers


def image_url_candidates(url: str) -> tuple[str, ...]:
    clean_url = str(url or "").strip()
    parsed = _http_url(clean_url)
    if parsed is None:
        return ()

    candidates: list[str] = []
    _append_unique(candidates, clean_url)

    host = (parsed.hostname or "").lower()
    if host in DOUBAN_IMAGE_HOSTS:
        for candidate_host in DOUBAN_IMAGE_HOSTS:
            _append_unique(candidates, _replace_host(parsed, candidate_host))

    if host == "upload.wikimedia.org":
        original_path, filename = _wikimedia_original(parsed.path)
        if original_path and filename:
            original = parsed._replace(path=original_path)
            _append_unique(candidates, urlunsplit(original))
            thumb_root = re.sub(r"^(/wikipedia/[^/]+/)", r"\1thumb/", original_path, count=1)
            for width in WIKIMEDIA_THUMB_WIDTHS:
                suffix = f"{width}px-{filename}"
                if filename.lower().endswith(".svg"):
                    suffix += ".png"
                thumb_path = f"{thumb_root}/{suffix}"
                _append_unique(candidates, urlunsplit(original._replace(path=thumb_path)))

    return tuple(candidates)


def _http_url(value: str) -> SplitResult | None:
    try:
        parsed = urlsplit(str(value or "").strip())
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return None
        return parsed
    except ValueError:
        return None


def _replace_host(parsed: SplitResult, host: str) -> str:
    try:
        port = parsed.port
    except ValueError:
        port = None
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit(parsed._replace(netloc=netloc))


def _wikimedia_original(path: str) -> tuple[str, str]:
    marker = re.match(r"^(/wikipedia/[^/]+/)(.+)$", str(path or ""))
    if not marker:
        return "", ""
    root, remainder = marker.groups()
    if remainder.startswith("thumb/"):
        pieces = remainder.removeprefix("thumb/").split("/")
        if len(pieces) < 4:
            return "", ""
        original_pieces = pieces[:-1]
        filename = original_pieces[-1]
        return f"{root}{'/'.join(original_pieces)}", filename
    pieces = remainder.split("/")
    if len(pieces) < 3:
        return "", ""
    return str(path), pieces[-1]


def _append_unique(values: list[str], value: str) -> None:
    clean = str(value or "").strip()
    if clean and clean not in values:
        values.append(clean)
