from __future__ import annotations

import json
import inspect
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import urllib.request

from .candidate_planner import build_candidate_plan
from .crawler import crawl_user_collections, normalize_douban_user_id, redact_cookie_from_message
from .curated_catalog import apply_curated_people_photos, apply_curated_posters, backfill_missing_media_types
from .douban_sources import enrich_media_items, fetch_candidates_from_plan, fetch_douban_candidates, fetch_url_candidates
from .douban_sources import build_url_opener
from .io import load_media_csv, load_media_csv_from_text, read_text_file
from .profiler import build_taste_profile
from .recommender import recommend
from .serialization import media_item_from_dict, media_item_to_dict
from .storage import CacheStore, default_cache_dir
from .web_ui import INDEX_HTML

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_RATINGS = ROOT / "sample_data" / "ratings_sample.csv"
SAMPLE_CANDIDATES = ROOT / "sample_data" / "candidates_sample.csv"
CACHE = CacheStore(default_cache_dir(ROOT))


def build_recommendation_sections(recs) -> list[dict[str, object]]:
    order = ["必看 Top Picks", "高分剧情", "电影", "电视剧", "动漫", "想看优先", "冷门惊喜"]
    grouped: dict[str, list[dict[str, object]]] = {}
    for rec in recs:
        name = rec.section or rec.item.media_type or "全部"
        grouped.setdefault(name, []).append(rec.to_dict())

    sections: list[dict[str, object]] = []
    for name in order:
        rows = grouped.pop(name, [])
        if rows:
            sections.append({"name": name, "count": len(rows), "items": rows})
    for name, rows in grouped.items():
        sections.append({"name": name, "count": len(rows), "items": rows})
    return sections


def call_crawl_user_collections(**kwargs):
    signature = inspect.signature(crawl_user_collections)
    accepts_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values())
    if accepts_kwargs:
        return crawl_user_collections(**kwargs)
    filtered = {key: value for key, value in kwargs.items() if key in signature.parameters}
    return crawl_user_collections(**filtered)


def diagnostic_to_dict(diag) -> dict:
    if isinstance(diag, dict):
        return dict(diag)
    if hasattr(diag, "__dict__"):
        return dict(diag.__dict__)
    return {"message": str(diag)}


def analyze_sync_input(user_id_or_url: str, cookie: str = "") -> dict[str, object]:
    text = str(user_id_or_url or "").strip()
    lower = text.lower()
    is_profile_url = "douban.com/people/" in lower
    analysis: dict[str, object] = {
        "user_id": "",
        "profile_url": is_profile_url,
        "cookie_provided": bool(str(cookie or "").strip()),
        "profile_url_is_not_cookie": is_profile_url and not bool(str(cookie or "").strip()),
        "can_parse": False,
    }
    try:
        analysis["user_id"] = normalize_douban_user_id(text)
        analysis["can_parse"] = True
    except Exception as exc:
        analysis["error"] = str(exc)
    return analysis


def build_sync_recovery(result, collect_count: int, wish_count: int) -> dict[str, object]:
    diagnostics = [diagnostic_to_dict(diag) for diag in getattr(result, "diagnostics", [])]
    classifications = {str(diag.get("classification") or "") for diag in diagnostics}
    http_statuses = {diag.get("http_status") for diag in diagnostics}
    has_items = (collect_count + wish_count) > 0
    if has_items:
        return {
            "status": "ok",
            "headline": "同步已拿到可用数据",
            "can_continue_without_sync": False,
            "actions": ["继续确认口味", "生成推荐"],
        }
    if "login_required" in classifications or 401 in http_statuses or 403 in http_statuses:
        return {
            "status": "needs_cookie",
            "headline": "豆瓣要求登录态或 Cookie，匿名抓取被拦截",
            "can_continue_without_sync": True,
            "actions": [
                "Cookie 解锁：复制当前浏览器里 movie.douban.com 请求的 Cookie 后重试",
                "继续用高质量片库生成推荐：先跳过同步，也能生成电影 / 电视剧 / 动漫推荐",
                "CSV 兜底：从豆瓣导出或手动整理评分后粘贴",
            ],
        }
    if "security_check" in classifications:
        return {
            "status": "security_check",
            "headline": "豆瓣触发安全验证，建议稍后重试或降低抓取频率",
            "can_continue_without_sync": True,
            "actions": ["稍后重试", "减少页数后同步", "继续用高质量片库生成推荐"],
        }
    if getattr(result, "pages_failed", 0):
        return {
            "status": "partial_failure",
            "headline": "部分分页抓取失败，可以继续使用已有数据",
            "can_continue_without_sync": True,
            "actions": ["重试失败页", "继续确认口味", "继续用高质量片库生成推荐"],
        }
    return {
        "status": "idle",
        "headline": "还没有同步数据",
        "can_continue_without_sync": True,
        "actions": ["同步豆瓣", "继续用高质量片库生成推荐"],
    }


def fetch_proxy_image(url: str) -> tuple[bytes, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("invalid image url")
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Referer": "https://m.douban.com/" if "doubanio.com" in parsed.netloc else "https://movie.douban.com/",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    })
    opener = build_url_opener()
    with opener.open(request, timeout=12) as response:
        content_type = response.headers.get("Content-Type") or "image/jpeg"
        return response.read(), content_type.split(";")[0]


class Handler(BaseHTTPRequestHandler):
    server_version = "DoubanTasteRecommender/0.1"

    def log_message(self, fmt: str, *args) -> None:
        print("[web] " + fmt % args)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path in {"/", "/index.html"}:
                self.send_text(INDEX_HTML, content_type="text/html; charset=utf-8")
            elif path == "/sample/ratings":
                self.send_text(read_text_file(SAMPLE_RATINGS), content_type="text/plain; charset=utf-8")
            elif path == "/sample/candidates":
                self.send_text(read_text_file(SAMPLE_CANDIDATES), content_type="text/plain; charset=utf-8")
            elif path == "/api/cache":
                self.send_json(self.handle_cache_get())
            elif path == "/api/image-proxy":
                query = parse_qs(parsed.query)
                image_url = query.get("url", [""])[0]
                data, content_type = fetch_proxy_image(image_url)
                self.send_bytes(data, content_type=content_type)
            else:
                self.send_json({"error": "not found"}, status=404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        payload = {}
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if path == "/api/recommend":
                data = self.handle_recommend(payload)
            elif path in {"/api/crawl-douban", "/api/sync-douban"}:
                data = self.handle_sync_douban(payload)
            else:
                self.send_json({"error": "not found"}, status=404)
                return
            self.send_json(data)
        except Exception as exc:
            cookie = payload.get("cookie") if isinstance(payload, dict) else ""
            self.send_json({"error": redact_cookie_from_message(str(exc), cookie or "")}, status=500)

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/cache":
                self.send_json(self.handle_cache_delete())
            else:
                self.send_json({"error": "not found"}, status=404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def handle_cache_get(self) -> dict:
        items, report = CACHE.load_library()
        summary = CACHE.summary()
        return {
            "cache_dir": summary.cache_dir,
            "files": summary.files,
            "library_count": len(items),
            "sync_report": report,
        }

    def handle_cache_delete(self) -> dict:
        return {"removed": CACHE.clear()}

    def handle_sync_douban(self, payload: dict) -> dict:
        user_id_or_url = payload.get("user_id_or_url") or ""
        cookie = payload.get("cookie") or ""
        input_analysis = analyze_sync_input(user_id_or_url, cookie)
        result = call_crawl_user_collections(
            user_id_or_url=user_id_or_url,
            cookie=cookie,
            max_pages=max(1, min(200, int(payload.get("max_pages") or 40))),
            include_wish=bool(payload.get("include_wish", True)),
            include_do=bool(payload.get("include_do", False)),
            expected_collect=int(payload["expected_collect"]) if str(payload.get("expected_collect") or "").strip() else None,
            expected_wish=int(payload["expected_wish"]) if str(payload.get("expected_wish") or "").strip() else None,
        )
        collect_count, wish_count = count_crawl_sources(result.items)
        diagnostics = [diagnostic_to_dict(diag) for diag in getattr(result, "diagnostics", [])]
        CACHE.save_library(result.items, {
            "counts": getattr(result, "completeness", {}),
            "diagnostics": diagnostics,
            "stopped_reason": result.stopped_reason,
        })
        return {
            "items": [media_item_to_dict(item) for item in result.items],
            "counts": {
                "items": len(result.items),
                "collect_count": collect_count,
                "wish_count": wish_count,
                "pages_ok": result.pages_ok,
                "pages_failed": result.pages_failed,
                "stopped_reason": result.stopped_reason,
            },
            "diagnostics": diagnostics,
            "completeness": getattr(result, "completeness", {}),
            "errors": result.errors,
            "stopped_reason": result.stopped_reason,
            "input_analysis": input_analysis,
            "recovery": build_sync_recovery(result, collect_count, wish_count),
        }

    handle_crawl_douban = handle_sync_douban

    def handle_recommend(self, payload: dict) -> dict:
        rated_items_payload = payload.get("rated_items") or []
        if rated_items_payload:
            string_defaults = {
                "title": "",
                "media_type": "",
                "url": "",
                "douban_id": "",
                "cover": "",
                "summary": "",
                "source": "",
            }
            rated = [media_item_from_dict({**string_defaults, **item}) for item in rated_items_payload if isinstance(item, dict)]
        else:
            ratings_csv = payload.get("ratings_csv") or ""
            rated = load_media_csv_from_text(ratings_csv, kind="ratings") if ratings_csv.strip() else load_media_csv(SAMPLE_RATINGS, kind="ratings")
        profile = build_taste_profile(
            rated,
            like_terms=payload.get("like_terms") or "",
            dislike_terms=payload.get("dislike_terms") or "",
        )

        candidates = []
        candidates_csv = payload.get("candidates_csv") or ""
        has_custom_candidates = bool(candidates_csv.strip())
        if has_custom_candidates:
            candidates.extend(load_media_csv_from_text(candidates_csv, kind="candidates"))
        elif payload.get("use_sample_candidates"):
            candidates.extend(load_media_csv(SAMPLE_CANDIDATES, kind="candidates"))
        apply_curated_people_photos(apply_curated_posters(candidates))
        urls_text = payload.get("candidate_urls") or ""
        urls = [x.strip() for x in urls_text.replace("\n", ",").split(",") if x.strip()]
        if urls:
            candidates.extend(fetch_url_candidates(urls))
        include_anime = bool(payload.get("include_anime", True))
        if payload.get("fetch_douban"):
            wishlist = [item for item in rated if "想看" in set(item.tags or [])]
            plan = build_candidate_plan(
                profile,
                include_movies=bool(payload.get("include_movies", True)),
                include_series=bool(payload.get("include_series", True)),
                include_anime=include_anime,
                wishlist=wishlist,
            )
            report = fetch_candidates_from_plan(plan, sleep_seconds=0.02, max_consecutive_failures=8)
            candidates.extend(report.items)
            if not candidates:
                candidates.extend(fetch_douban_candidates(
                    profile,
                    include_movies=bool(payload.get("include_movies", True)),
                    include_series=bool(payload.get("include_series", True)),
                    per_query=max(5, min(50, int(payload.get("per_query") or 20))),
                ))
        curated_before = len(candidates)
        if not has_custom_candidates:
            candidates = backfill_missing_media_types(
                candidates,
                include_movies=bool(payload.get("include_movies", True)),
                include_series=bool(payload.get("include_series", True)),
                include_anime=include_anime,
            )
        apply_curated_people_photos(apply_curated_posters(candidates))
        curated_added = max(0, len(candidates) - curated_before)
        recs = recommend(
            rated,
            candidates,
            profile,
            limit=max(1, min(300, int(payload.get("limit") or 120))),
            include_movies=bool(payload.get("include_movies", True)),
            include_series=bool(payload.get("include_series", True)),
            include_anime=include_anime,
        )
        if bool(payload.get("enrich_details", True)) and recs:
            enrich_limit = max(1, min(24, len(recs), int(payload.get("limit") or 120)))
            enrich_media_items([rec.item for rec in recs[:enrich_limit]], limit=enrich_limit)
        return {
            "profile": profile.summary(),
            "counts": {"rated": len(rated), "candidates": len(candidates), "curated_candidates": curated_added},
            "sections": build_recommendation_sections(recs),
            "results": [rec.to_dict() for rec in recs],
        }

    def send_text(self, text: str, content_type: str = "text/plain; charset=utf-8", status: int = 200) -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_bytes(self, data: bytes, content_type: str = "application/octet-stream", status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def count_crawl_sources(items) -> tuple[int, int]:
    collect_count = 0
    wish_count = 0
    for item in items:
        source = str(getattr(item, "source", "") or "")
        tags = set(getattr(item, "tags", []) or [])
        if source.endswith(":wish") or "想看" in tags:
            wish_count += 1
        else:
            collect_count += 1
    return collect_count, wish_count


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="启动豆瓣口味影视推荐器网页")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7861)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"豆瓣口味影视推荐器已启动：{url}")
    print("按 Ctrl+C 停止。")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
