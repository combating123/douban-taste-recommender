from __future__ import annotations

import csv
import html
import io
from pathlib import Path

from .profiler import TasteProfile
from .recommender import Recommendation


def write_html_report(path: str | Path, recs: list[Recommendation], profile: TasteProfile, title: str = "豆瓣口味影视推荐") -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(render_html_report(recs, profile, title=title), encoding="utf-8")


def write_csv_report(path: str | Path, recs: list[Recommendation]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(render_csv_report(recs), encoding="utf-8-sig")


def render_csv_report(recs: list[Recommendation]) -> str:
    buf = io.StringIO()
    fields = ["rank", "title", "media_type", "year", "score", "douban_rating", "genres", "tags", "directors", "casts", "url", "reasons", "warnings"]
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    for idx, rec in enumerate(recs, 1):
        item = rec.item
        writer.writerow({
            "rank": idx,
            "title": item.title,
            "media_type": item.media_type,
            "year": item.year or "",
            "score": round(rec.score, 2),
            "douban_rating": item.douban_rating or "",
            "genres": " / ".join(item.genres),
            "tags": " / ".join(item.tags),
            "directors": " / ".join(item.directors),
            "casts": " / ".join(item.casts[:6]),
            "url": item.url,
            "reasons": "；".join(rec.reasons),
            "warnings": "；".join(rec.warnings),
        })
    return buf.getvalue()


def render_html_report(recs: list[Recommendation], profile: TasteProfile, title: str = "豆瓣口味影视推荐") -> str:
    summary = profile.summary()
    cards = []
    for idx, rec in enumerate(recs, 1):
        item = rec.item
        cover = f'<img class="cover" src="{esc(item.cover)}" alt="cover" />' if item.cover else '<div class="cover placeholder">No Poster</div>'
        url_title = f'<a href="{esc(item.url)}" target="_blank">{esc(item.title)}</a>' if item.url else esc(item.title)
        tags = item.genres + item.tags + item.countries
        warnings = ""
        if rec.warnings:
            warnings = '<h3 class="warn-title">避雷提示</h3><ul class="warn">' + "".join(f"<li>{esc(x)}</li>" for x in rec.warnings) + "</ul>"
        cards.append(f'''
        <article class="card">
          <div class="rank">#{idx}</div>
          {cover}
          <div class="body">
            <h2>{url_title}</h2>
            <div class="meta"><span>{esc(item.media_type)}</span><span>个性化分 {rec.score:.1f}</span><span>豆瓣 {item.douban_rating or "-"}</span><span>{item.year or ""}</span></div>
            <div class="chips">{''.join(f'<span>{esc(t)}</span>' for t in tags[:12])}</div>
            <p class="summary">{esc(item.summary)}</p>
            <h3>推荐理由</h3>
            <ul>{''.join(f'<li>{esc(x)}</li>' for x in rec.reasons)}</ul>
            {warnings}
          </div>
        </article>
        ''')
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc(title)}</title>
  <style>
    :root {{ --bg:#0f172a; --panel:#111827; --card:#182235; --text:#e5e7eb; --muted:#9ca3af; --accent:#22c55e; --warn:#f97316; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif; background:linear-gradient(160deg,#0f172a,#111827 45%,#0b1220); color:var(--text); }}
    .wrap {{ max-width:1120px; margin:0 auto; padding:32px 20px 80px; }}
    h1 {{ font-size:34px; margin:0 0 10px; }}
    .sub {{ color:var(--muted); margin-bottom:22px; }}
    .profile {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:12px; margin:20px 0 28px; }}
    .box {{ background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.08); border-radius:16px; padding:14px; }}
    .box b {{ color:white; }}
    .mini {{ font-size:13px; color:var(--muted); line-height:1.8; }}
    .card {{ position:relative; display:grid; grid-template-columns:110px 1fr; gap:18px; padding:18px; margin:16px 0; background:rgba(24,34,53,.92); border:1px solid rgba(255,255,255,.08); border-radius:20px; box-shadow:0 10px 30px rgba(0,0,0,.22); }}
    .rank {{ position:absolute; top:12px; left:12px; background:var(--accent); color:#06210f; font-weight:800; border-radius:999px; padding:4px 9px; font-size:12px; }}
    .cover {{ width:110px; height:160px; object-fit:cover; border-radius:14px; background:#243047; display:flex; align-items:center; justify-content:center; color:var(--muted); font-size:13px; }}
    h2 {{ margin:0 0 8px; font-size:22px; }}
    h2 a {{ color:#fff; text-decoration:none; }}
    h2 a:hover {{ color:var(--accent); }}
    .meta {{ display:flex; flex-wrap:wrap; gap:8px; color:var(--muted); font-size:13px; margin-bottom:10px; }}
    .meta span {{ background:rgba(255,255,255,.06); padding:4px 8px; border-radius:999px; }}
    .chips {{ display:flex; flex-wrap:wrap; gap:6px; margin:8px 0; }}
    .chips span {{ border:1px solid rgba(34,197,94,.35); color:#bbf7d0; padding:3px 8px; border-radius:999px; font-size:12px; }}
    .summary {{ color:#cbd5e1; }}
    h3 {{ font-size:14px; margin:12px 0 5px; color:#86efac; }}
    ul {{ margin:0; padding-left:20px; color:#d1d5db; line-height:1.7; }}
    .warn-title {{ color:#fdba74; }}
    .warn li {{ color:#fed7aa; }}
    @media(max-width:640px) {{ .card {{ grid-template-columns:1fr; }} .cover {{ width:100%; height:260px; }} }}
  </style>
</head>
<body>
  <main class="wrap">
    <h1>{esc(title)}</h1>
    <div class="sub">基于你的豆瓣评分、手动口味和豆瓣公开候选池做本地个性化重排。</div>
    <section class="profile">
      <div class="box"><b>评分画像</b><div class="mini">已评分 {summary['rated_count']}；高分 {summary['liked_count']}；低分 {summary['disliked_count']}</div></div>
      <div class="box"><b>偏好类型</b><div class="mini">{esc(format_pairs(summary['top_genres']))}</div></div>
      <div class="box"><b>避雷类型</b><div class="mini">{esc(format_pairs(summary['avoid_genres']))}</div></div>
      <div class="box"><b>偏好导演/地区</b><div class="mini">{esc(format_pairs(summary['top_directors'][:4]) or '-')}<br>{esc(format_pairs(summary['top_countries'][:4]) or '-')}</div></div>
    </section>
    {''.join(cards) if cards else '<div class="box">没有生成推荐，请增加候选库或开启豆瓣候选源。</div>'}
  </main>
</body>
</html>'''


def format_pairs(pairs: list[tuple[str, float]]) -> str:
    return "、".join(x for x, _ in pairs) or "-"


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)
