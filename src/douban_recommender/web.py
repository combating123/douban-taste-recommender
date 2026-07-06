from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .douban_sources import fetch_douban_candidates, fetch_url_candidates
from .io import load_media_csv, load_media_csv_from_text, read_text_file
from .profiler import build_taste_profile
from .recommender import recommend

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_RATINGS = ROOT / "sample_data" / "ratings_sample.csv"
SAMPLE_CANDIDATES = ROOT / "sample_data" / "candidates_sample.csv"

INDEX_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>豆瓣口味影视推荐器</title>
  <style>
    :root { --bg:#08111f; --panel:#101827; --card:#162133; --text:#e5e7eb; --muted:#94a3b8; --accent:#22c55e; --line:rgba(255,255,255,.1); --warn:#fb923c; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif; color:var(--text); background:radial-gradient(circle at 10% 0,#18324a,#08111f 40%,#060b13); }
    .wrap { max-width:1160px; margin:0 auto; padding:30px 18px 70px; }
    header { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; margin-bottom:18px; }
    h1 { margin:0; font-size:32px; letter-spacing:-.5px; }
    .sub { color:var(--muted); margin-top:8px; line-height:1.6; }
    .pill { border:1px solid rgba(34,197,94,.4); color:#bbf7d0; padding:7px 10px; border-radius:999px; font-size:13px; white-space:nowrap; }
    .grid { display:grid; grid-template-columns:minmax(320px,420px) 1fr; gap:16px; align-items:start; }
    .panel { background:rgba(16,24,39,.9); border:1px solid var(--line); border-radius:22px; padding:18px; box-shadow:0 20px 60px rgba(0,0,0,.25); }
    label { display:block; font-weight:700; margin:13px 0 7px; }
    textarea, input[type=text], input[type=number] { width:100%; min-height:72px; border:1px solid var(--line); border-radius:14px; background:#0d1524; color:var(--text); padding:11px; outline:none; font:inherit; }
    input[type=text], input[type=number] { min-height:auto; }
    textarea:focus, input:focus { border-color:rgba(34,197,94,.7); }
    input[type=file] { width:100%; border:1px dashed var(--line); border-radius:14px; padding:12px; background:#0d1524; color:var(--muted); }
    .row { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
    .checks { display:flex; flex-wrap:wrap; gap:10px; margin:8px 0 12px; }
    .checks label { display:flex; align-items:center; gap:6px; margin:0; font-weight:500; color:#cbd5e1; }
    button { cursor:pointer; border:none; border-radius:14px; padding:11px 14px; background:var(--accent); color:#052e16; font-weight:800; font-size:15px; }
    button.secondary { background:#253044; color:#dbeafe; }
    button.ghost { background:transparent; border:1px solid var(--line); color:#cbd5e1; }
    .buttons { display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; }
    .status { color:var(--muted); font-size:13px; margin-top:12px; line-height:1.6; white-space:pre-wrap; }
    .profile { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin-bottom:14px; }
    .stat { background:rgba(255,255,255,.055); border:1px solid var(--line); border-radius:16px; padding:12px; color:#cbd5e1; font-size:13px; line-height:1.6; }
    .stat b { display:block; color:white; font-size:14px; margin-bottom:3px; }
    .card { position:relative; display:grid; grid-template-columns:96px 1fr; gap:15px; background:rgba(22,33,51,.92); border:1px solid var(--line); border-radius:20px; padding:14px; margin:13px 0; }
    .rank { position:absolute; left:10px; top:10px; background:var(--accent); color:#052e16; border-radius:999px; padding:3px 8px; font-weight:900; font-size:12px; }
    .cover { width:96px; height:142px; object-fit:cover; border-radius:13px; background:#263244; display:flex; align-items:center; justify-content:center; color:var(--muted); font-size:12px; text-align:center; }
    h2 { margin:0 0 6px; font-size:20px; }
    h2 a { color:white; text-decoration:none; }
    h2 a:hover { color:var(--accent); }
    .meta { display:flex; flex-wrap:wrap; gap:6px; color:var(--muted); font-size:12px; margin-bottom:8px; }
    .meta span { background:rgba(255,255,255,.06); padding:3px 8px; border-radius:999px; }
    .chips { display:flex; flex-wrap:wrap; gap:5px; margin:7px 0; }
    .chips span { color:#bbf7d0; border:1px solid rgba(34,197,94,.32); padding:2px 7px; border-radius:999px; font-size:12px; }
    .section-title { font-size:13px; color:#86efac; font-weight:800; margin:10px 0 4px; }
    ul { margin:0; padding-left:19px; color:#d1d5db; line-height:1.55; font-size:14px; }
    .warn-title { color:#fdba74; }
    .warn { color:#fed7aa; }
    .empty { border:1px dashed var(--line); padding:28px; border-radius:18px; color:var(--muted); text-align:center; }
    @media(max-width:900px) { .grid { grid-template-columns:1fr; } header { display:block; } .pill { display:inline-block; margin-top:10px; } }
    @media(max-width:560px) { .card { grid-template-columns:1fr; } .cover { width:100%; height:260px; } .row { grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>豆瓣口味影视推荐器</h1>
        <div class="sub">导入你的豆瓣评分，填写喜欢/不喜欢口味；系统会调用豆瓣公开候选池，并按你的口味重新排序电影和电视剧。</div>
      </div>
      <div class="pill">本地运行 · 不上传到外部服务</div>
    </header>

    <div class="grid">
      <section class="panel">
        <label>1. 上传豆瓣评分 CSV</label>
        <input id="ratingsFile" type="file" accept=".csv,.txt" />
        <label>或直接粘贴评分 CSV</label>
        <textarea id="ratingsText" placeholder="title,my_rating,genres,countries,directors,cats,tags...&#10;寄生虫,5,剧情 / 犯罪,韩国,奉俊昊,..."></textarea>

        <div class="row">
          <div>
            <label>喜欢的口味</label>
            <textarea id="likeTerms">悬疑, 犯罪, 现实主义, 黑色幽默, 群像, 女性题材</textarea>
          </div>
          <div>
            <label>不喜欢的口味</label>
            <textarea id="dislikeTerms">甜宠, 狗血, 低幼, 恐怖血腥, 无脑爽剧</textarea>
          </div>
        </div>

        <label>2. 可选：自定义候选 CSV</label>
        <textarea id="candidateText" placeholder="title,media_type,douban_rating,genres,directors,casts,tags,url"></textarea>

        <label>3. 可选：豆瓣候选 URL</label>
        <input id="candidateUrls" type="text" placeholder="可粘贴豆瓣 Top250 / explore 接口 / 豆列 URL，多个用逗号分隔" />

        <div class="row">
          <div>
            <label>推荐数量</label>
            <input id="limit" type="number" min="5" max="100" value="30" />
          </div>
          <div>
            <label>豆瓣每个查询拉取数</label>
            <input id="perQuery" type="number" min="5" max="50" value="20" />
          </div>
        </div>

        <div class="checks">
          <label><input id="includeMovies" type="checkbox" checked />电影</label>
          <label><input id="includeSeries" type="checkbox" checked />电视剧</label>
          <label><input id="fetchDouban" type="checkbox" checked />从豆瓣拉候选</label>
          <label><input id="useSampleCandidates" type="checkbox" checked />加入示例候选</label>
        </div>

        <div class="buttons">
          <button id="runBtn">生成推荐</button>
          <button id="sampleBtn" class="secondary">填入示例数据</button>
          <button id="clearBtn" class="ghost">清空</button>
        </div>
        <div id="status" class="status"></div>
      </section>

      <section class="panel">
        <div id="output" class="empty">还没有生成推荐。可以先点“填入示例数据”试跑。</div>
      </section>
    </div>
  </div>

<script>
const $ = (id) => document.getElementById(id);
async function readFileText(input) {
  if (!input.files || !input.files[0]) return "";
  return await input.files[0].text();
}
function setStatus(text) { $("status").textContent = text || ""; }
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, m => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m])); }
async function loadSample() {
  const [ratings, candidates] = await Promise.all([
    fetch('/sample/ratings').then(r => r.text()),
    fetch('/sample/candidates').then(r => r.text()),
  ]);
  $('ratingsText').value = ratings;
  $('candidateText').value = candidates;
  setStatus('已填入示例数据。点击“生成推荐”即可试跑。');
}
function render(data) {
  const out = $('output');
  if (!data || !data.results || data.results.length === 0) {
    out.className = 'empty';
    out.innerHTML = '没有生成推荐：请增加候选库、开启豆瓣候选源，或检查 CSV 表头。';
    return;
  }
  out.className = '';
  const s = data.profile || {};
  const fmtPairs = (pairs) => (pairs || []).map(x => esc(x[0])).join('、') || '-';
  const profileHtml = `<div class="profile">
    <div class="stat"><b>评分画像</b>已评分 ${s.rated_count || 0}<br>高分 ${s.liked_count || 0} / 低分 ${s.disliked_count || 0}</div>
    <div class="stat"><b>偏好类型</b>${fmtPairs(s.top_genres)}</div>
    <div class="stat"><b>避雷类型</b>${fmtPairs(s.avoid_genres)}</div>
    <div class="stat"><b>偏好导演/地区</b>${fmtPairs(s.top_directors)}<br>${fmtPairs(s.top_countries)}</div>
  </div>`;
  const cards = data.results.map((r, i) => {
    const title = r.url ? `<a href="${esc(r.url)}" target="_blank">${esc(r.title)}</a>` : esc(r.title);
    const cover = r.cover ? `<img class="cover" src="${esc(r.cover)}" />` : `<div class="cover">No Poster</div>`;
    const chips = [...(r.genres || []), ...(r.tags || []), ...(r.countries || [])].slice(0, 12).map(x => `<span>${esc(x)}</span>`).join('');
    const reasons = (r.reasons || []).map(x => `<li>${esc(x)}</li>`).join('');
    const warnings = (r.warnings || []).map(x => `<li>${esc(x)}</li>`).join('');
    return `<article class="card">
      <div class="rank">#${i + 1}</div>${cover}
      <div>
        <h2>${title}</h2>
        <div class="meta"><span>${esc(r.media_type)}</span><span>个性化分 ${Number(r.score).toFixed(1)}</span><span>豆瓣 ${r.douban_rating || '-'}</span><span>${r.year || ''}</span></div>
        <div class="chips">${chips}</div>
        ${r.summary ? `<div class="sub">${esc(r.summary)}</div>` : ''}
        <div class="section-title">推荐理由</div><ul>${reasons}</ul>
        ${warnings ? `<div class="section-title warn-title">避雷提示</div><ul class="warn">${warnings}</ul>` : ''}
      </div>
    </article>`;
  }).join('');
  out.innerHTML = profileHtml + cards;
}
async function runRecommend() {
  setStatus('正在读取数据并生成推荐... 如果开启豆瓣候选源，通常需要 5-15 秒。');
  $('runBtn').disabled = true;
  try {
    const fileText = await readFileText($('ratingsFile'));
    const payload = {
      ratings_csv: fileText || $('ratingsText').value,
      candidates_csv: $('candidateText').value,
      like_terms: $('likeTerms').value,
      dislike_terms: $('dislikeTerms').value,
      candidate_urls: $('candidateUrls').value,
      include_movies: $('includeMovies').checked,
      include_series: $('includeSeries').checked,
      fetch_douban: $('fetchDouban').checked,
      use_sample_candidates: $('useSampleCandidates').checked,
      limit: Number($('limit').value || 30),
      per_query: Number($('perQuery').value || 20),
    };
    const res = await fetch('/api/recommend', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || '请求失败');
    render(data);
    setStatus(`完成：评分 ${data.counts.rated} 条，候选 ${data.counts.candidates} 条，输出 ${data.results.length} 条推荐。`);
  } catch (err) {
    console.error(err);
    setStatus('出错：' + err.message);
  } finally {
    $('runBtn').disabled = false;
  }
}
$('runBtn').addEventListener('click', runRecommend);
$('sampleBtn').addEventListener('click', loadSample);
$('clearBtn').addEventListener('click', () => {
  $('ratingsText').value = ''; $('candidateText').value = ''; $('candidateUrls').value = ''; $('ratingsFile').value = '';
  setStatus('已清空。'); $('output').className = 'empty'; $('output').textContent = '还没有生成推荐。';
});
</script>
</body>
</html>'''


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
        if path != "/api/recommend":
            self.send_json({"error": "not found"}, status=404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            data = self.handle_recommend(payload)
            self.send_json(data)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def handle_recommend(self, payload: dict) -> dict:
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
