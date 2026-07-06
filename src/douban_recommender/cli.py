from __future__ import annotations

import argparse
from pathlib import Path

from .douban_sources import fetch_douban_candidates, fetch_url_candidates
from .io import load_media_csv
from .profiler import build_taste_profile
from .recommender import recommend
from .report import write_csv_report, write_html_report

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="根据豆瓣评分和口味生成影视推荐")
    parser.add_argument("--ratings", help="你的豆瓣评分 CSV")
    parser.add_argument("--candidates", action="append", default=[], help="候选影视 CSV，可重复传入")
    parser.add_argument("--candidate-url", action="append", default=[], help="豆瓣候选页面/接口 URL，可重复传入")
    parser.add_argument("--like", default="", help="喜欢的口味，逗号分隔")
    parser.add_argument("--dislike", default="", help="不喜欢的口味，逗号分隔")
    parser.add_argument("--fetch-douban", action="store_true", help="从豆瓣公开候选池拉取候选")
    parser.add_argument("--movies", action="store_true", help="包含电影；默认电影和电视剧都包含")
    parser.add_argument("--series", action="store_true", help="包含电视剧；默认电影和电视剧都包含")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--output", default="output/recommendations.html", help="输出 .html 或 .csv")
    args = parser.parse_args(argv)

    ratings_path = Path(args.ratings) if args.ratings else ROOT / "sample_data" / "ratings_sample.csv"
    rated = load_media_csv(ratings_path, kind="ratings")
    profile = build_taste_profile(rated, like_terms=args.like, dislike_terms=args.dislike)

    candidates = []
    for path in args.candidates:
        candidates.extend(load_media_csv(path, kind="candidates"))
    if not candidates and not args.fetch_douban and not args.candidate_url:
        candidates.extend(load_media_csv(ROOT / "sample_data" / "candidates_sample.csv", kind="candidates"))
    if args.candidate_url:
        candidates.extend(fetch_url_candidates(args.candidate_url))
    if args.fetch_douban:
        include_movies = args.movies or not args.series
        include_series = args.series or not args.movies
        candidates.extend(fetch_douban_candidates(profile, include_movies=include_movies, include_series=include_series))

    include_movies = args.movies or not args.series
    include_series = args.series or not args.movies
    recs = recommend(rated, candidates, profile, limit=args.limit, include_movies=include_movies, include_series=include_series)

    out = Path(args.output)
    if out.suffix.lower() == ".csv":
        write_csv_report(out, recs)
    else:
        write_html_report(out, recs, profile)
    print(f"已生成 {out.resolve()}")
    print("Top 10:")
    for idx, rec in enumerate(recs[:10], 1):
        print(f"{idx:02d}. {rec.item.title} [{rec.item.media_type}] score={rec.score:.1f} douban={rec.item.douban_rating or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
