from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .crawler import crawl_user_collections
from .douban_sources import fetch_douban_candidates, fetch_url_candidates
from .io import load_media_csv, load_media_csv_from_text, read_text_file
from .profiler import build_taste_profile
from .recommender import recommend
from .serialization import media_item_from_dict, media_item_to_dict
from .web_ui import INDEX_HTML

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_RATINGS = ROOT / "sample_data" / "ratings_sample.csv"
SAMPLE_CANDIDATES = ROOT / "sample_data" / "candidates_sample.csv"

class Handler(BaseHTTPRequestHandler):
    server_version = "DoubanTasteRecommender/0.1"

    def log_message(self, fmt: str, *args) -> None:
        print("[web] " + fmt % args)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path in {"/", "/index.html"}:
                self.send_text(INDEX_HTML, content_type="text/html; charset=utf-8")
            elif path == "/sample/ratings":
                self.send_text(read_text_file(SAMPLE_RATINGS), content_type="text/plain; charset=utf-8")
            elif path == "/sample/candidates":
                self.send_text(read_text_file(SAMPLE_CANDIDATES), content_type="text/plain; charset=utf-8")
            else:
                self.send_json({"error": "not found"}, status=404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if path == "/api/recommend":
                data = self.handle_recommend(payload)
            elif path == "/api/crawl-douban":
                data = self.handle_crawl_douban(payload)
            else:
                self.send_json({"error": "not found"}, status=404)
                return
            self.send_json(data)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def handle_crawl_douban(self, payload: dict) -> dict:
        result = crawl_user_collections(
            user_id_or_url=payload.get("user_id_or_url") or "",
            cookie=payload.get("cookie") or "",
            max_pages=max(1, min(60, int(payload.get("max_pages") or 8))),
            include_wish=bool(payload.get("include_wish", True)),
        )
        return {
            "items": [media_item_to_dict(item) for item in result.items],
            "counts": {
                "items": len(result.items),
                "pages_ok": result.pages_ok,
                "pages_failed": result.pages_failed,
            },
            "errors": result.errors,
            "stopped_reason": result.stopped_reason,
        }

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
        if payload.get("use_sample_candidates"):
            candidates.extend(load_media_csv(SAMPLE_CANDIDATES, kind="candidates"))
        candidates_csv = payload.get("candidates_csv") or ""
        if candidates_csv.strip():
            candidates.extend(load_media_csv_from_text(candidates_csv, kind="candidates"))
        urls_text = payload.get("candidate_urls") or ""
        urls = [x.strip() for x in urls_text.replace("\n", ",").split(",") if x.strip()]
        if urls:
            candidates.extend(fetch_url_candidates(urls))
        if payload.get("fetch_douban"):
            candidates.extend(fetch_douban_candidates(
                profile,
                include_movies=bool(payload.get("include_movies", True)),
                include_series=bool(payload.get("include_series", True)),
                per_query=max(5, min(50, int(payload.get("per_query") or 20))),
            ))
        recs = recommend(
            rated,
            candidates,
            profile,
            limit=max(1, min(100, int(payload.get("limit") or 30))),
            include_movies=bool(payload.get("include_movies", True)),
            include_series=bool(payload.get("include_series", True)),
        )
        return {
            "profile": profile.summary(),
            "counts": {"rated": len(rated), "candidates": len(candidates)},
            "results": [rec.to_dict() for rec in recs],
        }

    def send_text(self, text: str, content_type: str = "text/plain; charset=utf-8", status: int = 200) -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


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
