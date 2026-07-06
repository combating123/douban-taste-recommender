from __future__ import annotations

INDEX_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>豆瓣口味影视推荐器</title>
  <style>
    :root { --bg:#f6f7fb; --panel:#ffffff; --text:#172033; --muted:#667085; --line:#e5e7eb; --green:#16a34a; --green-bg:#ecfdf3; --blue:#2563eb; --orange:#ea580c; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif; background:var(--bg); color:var(--text); }
    .shell { max-width:1100px; margin:0 auto; padding:28px 18px 80px; }
    .hero { display:flex; justify-content:space-between; gap:18px; align-items:flex-start; margin-bottom:18px; }
    h1 { margin:0 0 8px; font-size:34px; letter-spacing:-.4px; }
    .lead { margin:0; color:var(--muted); line-height:1.7; max-width:760px; }
    .privacy { padding:10px 12px; border-radius:999px; background:var(--green-bg); color:#166534; font-weight:700; white-space:nowrap; }
    .steps { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin:18px 0; }
    .step { border:1px solid var(--line); background:var(--panel); border-radius:18px; padding:14px; color:var(--muted); }
    .step.active { border-color:#86efac; box-shadow:0 0 0 4px var(--green-bg); color:var(--text); }
    .step b { display:block; margin-bottom:4px; color:var(--text); }
    .grid { display:grid; grid-template-columns:minmax(300px,390px) 1fr; gap:16px; align-items:start; }
    .panel { background:var(--panel); border:1px solid var(--line); border-radius:22px; padding:18px; box-shadow:0 14px 35px rgba(15,23,42,.06); }
    .panel h2 { margin:0 0 6px; }
    .hint { color:var(--muted); line-height:1.65; font-size:14px; }
    label { display:block; font-weight:800; margin:14px 0 7px; }
    input[type=text], input[type=number], textarea { width:100%; border:1px solid var(--line); border-radius:14px; padding:12px; font:inherit; background:#fff; color:var(--text); }
    textarea { min-height:82px; resize:vertical; }
    .row { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
    .actions { display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; }
    button { border:0; border-radius:14px; padding:11px 14px; font-weight:900; cursor:pointer; background:var(--green); color:white; }
    button.secondary { background:#eef2ff; color:#3730a3; }
    button.ghost { background:#fff; color:var(--text); border:1px solid var(--line); }
    button:disabled { opacity:.55; cursor:not-allowed; }
    details { border:1px solid var(--line); border-radius:16px; padding:12px; background:#fff; margin-top:12px; }
    summary { cursor:pointer; font-weight:800; }
    .mini-list { margin:10px 0 0 20px; color:var(--muted); line-height:1.8; }
    .status { margin-top:12px; color:var(--muted); white-space:pre-wrap; line-height:1.6; }
    .statbar { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:10px; margin-top:12px; }
    .stat { background:#f8fafc; border:1px solid var(--line); border-radius:16px; padding:12px; }
    .stat b { display:block; font-size:20px; color:var(--text); }
    .empty { border:1px dashed var(--line); border-radius:18px; padding:28px; text-align:center; color:var(--muted); }
    .card { background:#fff; border:1px solid var(--line); border-radius:20px; padding:16px; margin:12px 0; }
    .card-top { display:flex; gap:12px; justify-content:space-between; align-items:flex-start; }
    .score { background:var(--green-bg); color:#166534; padding:6px 10px; border-radius:999px; font-weight:900; white-space:nowrap; }
    .meta { display:flex; flex-wrap:wrap; gap:7px; color:var(--muted); font-size:13px; margin:8px 0; }
    .meta span { background:#f8fafc; border:1px solid var(--line); padding:4px 8px; border-radius:999px; }
    .reasons { margin:8px 0 0 18px; line-height:1.65; }
    .warn { color:var(--orange); }
    .link { color:var(--blue); text-decoration:none; font-weight:800; }
    .hidden { display:none; }
    @media(max-width:880px) { .hero { display:block; } .privacy { display:inline-block; margin-top:12px; } .grid { grid-template-columns:1fr; } .steps { grid-template-columns:1fr; } .row { grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div>
        <h1>豆瓣口味影视推荐器</h1>
        <p class="lead">先连接豆瓣，再确认口味，最后查看推荐。Cookie 是可选项：公开数据够用就不需要填写。</p>
      </div>
      <div class="privacy">本地运行，不保存 Cookie</div>
    </section>
    <nav id="stepNav" class="steps" aria-label="任务步骤"></nav>
    <section class="grid">
      <div id="leftPanel" class="panel"></div>
      <div id="rightPanel" class="panel"></div>
    </section>
  </main>
<script>
const state = { step: 1, ratedItems: [], recommendations: [], profile: null, counts: null, errors: [], ratingsCsv: "", candidatesCsv: "", sampleRatingsCsv: "", sampleCandidatesCsv: "" };
const $ = (id) => document.getElementById(id);
function esc(value) { return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", "\"":"&quot;", "'":"&#39;" }[ch])); }
function setStatus(text) { const el = document.getElementById("status"); if (el) el.textContent = text || ""; }
function renderStepNav() {
  const steps = [
    ["第一步：连接豆瓣", "输入 ID，公开抓取；需要时再填 Cookie"],
    ["第二步：确认口味", "用短句告诉我喜欢和不喜欢什么"],
    ["第三步：查看推荐", "先看摘要，想深入再展开详情"]
  ];
  $("stepNav").innerHTML = steps.map((s, i) => `<div class="step ${state.step === i + 1 ? "active" : ""}"><b>${s[0]}</b>${s[1]}</div>`).join("");
}
function renderCookieGuide() {
  return `<details><summary>Cookie 教程</summary>
    <ol class="mini-list">
      <li>打开浏览器并登录豆瓣。</li>
      <li>进入 https://movie.douban.com/。</li>
      <li>按 F12 打开开发者工具，进入 Network / 网络。</li>
      <li>刷新页面，点任意 movie.douban.com 或 www.douban.com 请求。</li>
      <li>在 Headers / 标头里找到 Request Headers。</li>
      <li>复制 Cookie: 后面的整段内容，粘贴到这里。</li>
    </ol>
    <p class="hint">Cookie 只用于本机请求豆瓣页面，不会保存到磁盘，也不会出现在推荐报告里。</p>
  </details>`;
}
function renderCrawlerPanel() {
  $("leftPanel").innerHTML = `<h2>第一步：连接豆瓣</h2>
    <p class="hint">填写豆瓣用户 ID 或主页链接。Cookie 可不填；如果公开页面抓不到完整评分，再按教程复制 Cookie。</p>
    <label for="doubanUser">豆瓣用户 ID 或主页链接</label>
    <input id="doubanUser" type="text" placeholder="例如：https://www.douban.com/people/你的ID/" />
    <label for="doubanCookie">Cookie（可选）</label>
    <textarea id="doubanCookie" placeholder="公开数据够用就不用填"></textarea>
    <div class="row"><div><label for="maxPages">最多抓取页数</label><input id="maxPages" type="number" min="1" max="60" value="8" /></div><div><label>想看列表</label><label><input id="includeWish" type="checkbox" checked /> 同时抓取想看</label></div></div>
    <details><summary>没有抓取数据？粘贴 CSV</summary>
      <p class="hint">保留旧流程：可以直接粘贴评分 CSV 和候选 CSV，不抓取豆瓣也能生成推荐。</p>
      <label for="ratingsCsv">评分 CSV</label><textarea id="ratingsCsv" placeholder="title,my_rating,media_type,genres,tags">${esc(state.ratingsCsv)}</textarea>
      <label for="candidatesCsv">候选 CSV</label><textarea id="candidatesCsv" placeholder="title,media_type,douban_rating,genres,tags">${esc(state.candidatesCsv)}</textarea>
      <div class="actions"><button class="ghost" onclick="useCsvInputs()">使用粘贴的 CSV 继续</button></div>
    </details>
    ${renderCookieGuide()}
    <div class="actions"><button onclick="crawlDouban()">开始抓取</button><button class="secondary" onclick="loadSample()">使用示例数据</button></div>
    <div id="status" class="status"></div>`;
  renderCrawlSummary();
}
function renderCrawlSummary() {
  const hasCrawlInfo = state.ratedItems.length || state.counts || state.errors.length;
  const errorSummary = state.errors.length ? `<h3>错误摘要</h3><ul class="mini-list">${state.errors.slice(0,5).map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
  $("rightPanel").innerHTML = `<h2>抓取结果</h2>` + (hasCrawlInfo ? `<div class="statbar"><div class="stat"><b>${state.counts?.collect_count ?? 0}</b>看过数量</div><div class="stat"><b>${state.counts?.wish_count ?? 0}</b>想看数量</div><div class="stat"><b>${state.counts?.pages_ok ?? "-"}</b>成功页</div><div class="stat"><b>${state.counts?.pages_failed ?? "-"}</b>失败页</div></div><p class="hint">停止原因：${esc(state.counts?.stopped_reason || "-")}</p>${errorSummary}<h3>最近抓到</h3><ul class="mini-list">${state.ratedItems.slice(0,5).map(x => `<li>${esc(x.title)} ${x.my_rating ? "· 我的评分 " + x.my_rating : ""}</li>`).join("")}</ul><div class="actions"><button onclick="goStep(2)">下一步：确认口味</button></div>` : `<div class="empty">还没有数据。你可以抓取豆瓣，也可以粘贴 CSV 或使用示例数据先试跑。</div>`);
}
function renderTastePanel() {
  $("leftPanel").innerHTML = `<h2>第二步：确认口味</h2>
    <p class="hint">评分会自动分析；这里补充你最近想看的方向和明确避雷点。</p>
    <label for="likeTerms">喜欢的口味</label><textarea id="likeTerms">悬疑, 犯罪, 现实主义, 黑色幽默, 群像</textarea>
    <label for="dislikeTerms">不喜欢的口味</label><textarea id="dislikeTerms">甜宠, 狗血, 低幼, 恐怖血腥</textarea>
    <label>推荐范围</label>
    <label><input id="includeMovies" type="checkbox" checked /> 电影</label>
    <label><input id="includeSeries" type="checkbox" checked /> 电视剧</label>
    <details><summary>高级候选来源</summary>
      <label><input id="fetchDouban" type="checkbox" checked /> 从豆瓣探索候选池补充</label>
      <label><input id="useSampleCandidates" type="checkbox" checked /> 加入本地示例候选</label>
      <label for="limit">推荐数量</label><input id="limit" type="number" min="5" max="100" value="30" />
    </details>
    <div class="actions"><button onclick="recommend()">生成推荐</button><button class="ghost" onclick="goStep(1)">返回上一步</button></div>
    <div id="status" class="status"></div>`;
  $("rightPanel").innerHTML = `<h2>你的数据</h2><div class="statbar"><div class="stat"><b>${state.ratedItems.length || (state.sampleRatingsCsv ? "示例" : 0)}</b>评分/想看</div></div><p class="hint">系统会用高分条目学习偏好，用低分条目学习避雷，并自动排除已经看过的条目。</p>`;
}
function renderRecommendations() {
  const cards = state.recommendations.map((r, i) => `<article class="card">
    <div class="card-top"><div><h2>${i + 1}. ${r.url ? `<a class="link" href="${esc(r.url)}" target="_blank" rel="noreferrer">${esc(r.title)}</a>` : esc(r.title)}</h2><div class="meta"><span>${esc(r.media_type)}</span><span>豆瓣 ${r.douban_rating || "-"}</span><span>${esc((r.genres || []).slice(0,3).join(" / "))}</span></div></div><div class="score">${Number(r.score || 0).toFixed(1)}</div></div>
    <ul class="reasons">${(r.reasons || []).slice(0,3).map(x => `<li>${esc(x)}</li>`).join("")}</ul>
    <details><summary>展开详情</summary><ul class="mini-list">${(r.reasons || []).slice(3).map(x => `<li>${esc(x)}</li>`).join("")}${(r.warnings || []).map(x => `<li class="warn">${esc(x)}</li>`).join("")}</ul><p class="hint">导演：${esc((r.directors || []).join(" / ") || "-")}<br>主演：${esc((r.casts || []).slice(0,6).join(" / ") || "-")}<br>来源：${esc(r.source || "-")}</p></details>
  </article>`).join("");
  $("leftPanel").innerHTML = `<h2>第三步：查看推荐</h2><p class="hint">默认只展示最有用的理由；想看匹配细节再展开。</p><div class="actions"><button class="ghost" onclick="goStep(2)">调整口味</button><button class="secondary" onclick="goStep(1)">重新抓取</button></div>`;
  $("rightPanel").innerHTML = cards || `<div class="empty">还没有推荐结果。</div>`;
}
function goStep(step) {
  state.step = step;
  renderStepNav();
  if (step === 1) renderCrawlerPanel();
  if (step === 2) renderTastePanel();
  if (step === 3) renderRecommendations();
}
async function crawlDouban() {
  setStatus("正在抓取豆瓣页面，通常需要几十秒以内。");
  const cookieInput = $("doubanCookie");
  const payload = { user_id_or_url: $("doubanUser").value, cookie: cookieInput.value, max_pages: Number($("maxPages").value || 8), include_wish: $("includeWish").checked };
  cookieInput.value = "";
  const res = await fetch("/api/crawl-douban", { method:"POST", headers:{ "Content-Type":"application/json" }, body:JSON.stringify(payload) });
  const data = await res.json();
  if (!res.ok || data.error) { setStatus("抓取失败：" + (data.error || "请求失败")); return; }
  state.ratedItems = data.items || [];
  state.counts = data.counts || {};
  state.errors = data.errors || [];
  state.sampleRatingsCsv = "";
  state.sampleCandidatesCsv = "";
  state.ratingsCsv = "";
  state.candidatesCsv = "";
  renderCrawlerPanel();
}
function useCsvInputs() {
  state.ratedItems = [];
  state.ratingsCsv = $("ratingsCsv").value;
  state.candidatesCsv = $("candidatesCsv").value;
  state.sampleRatingsCsv = "";
  state.sampleCandidatesCsv = "";
  state.counts = null;
  state.errors = [];
  goStep(2);
}
async function loadSample() {
  const [ratings, candidates] = await Promise.all([
    fetch("/sample/ratings").then(r => r.text()),
    fetch("/sample/candidates").then(r => r.text()),
  ]);
  state.ratedItems = [];
  state.sampleRatingsCsv = ratings;
  state.sampleCandidatesCsv = candidates;
  state.ratingsCsv = "";
  state.candidatesCsv = "";
  state.counts = { pages_ok: "-", pages_failed: "-" };
  state.errors = [];
  goStep(2);
}
async function recommend() {
  setStatus("正在生成推荐。");
  const candidateCsv = state.candidatesCsv || state.sampleCandidatesCsv;
  const payload = { rated_items:state.ratedItems, ratings_csv: state.ratedItems.length ? "" : (state.ratingsCsv || state.sampleRatingsCsv), candidates_csv: candidateCsv, like_terms:$("likeTerms").value, dislike_terms:$("dislikeTerms").value, include_movies:$("includeMovies").checked, include_series:$("includeSeries").checked, fetch_douban:$("fetchDouban").checked, use_sample_candidates: candidateCsv ? false : $("useSampleCandidates").checked, limit:Number($("limit").value || 30) };
  const res = await fetch("/api/recommend", { method:"POST", headers:{ "Content-Type":"application/json" }, body:JSON.stringify(payload) });
  const data = await res.json();
  if (!res.ok || data.error) { setStatus("推荐失败：" + (data.error || "请求失败")); return; }
  state.recommendations = data.results || [];
  state.profile = data.profile || null;
  goStep(3);
}
goStep(1);
</script>
</body>
</html>'''
