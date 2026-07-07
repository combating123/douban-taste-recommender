from __future__ import annotations

INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CineScope Studio：豆瓣私人影视策展器</title>
  <style>
    :root { --bg:#070A12; --panel:rgba(16,22,36,.80); --panel2:rgba(255,255,255,.08); --text:#F8FAFC; --muted:#A7B0C0; --line:rgba(255,255,255,.13); --gold:#F5C451; --green:#4ADE80; --red:#FB7185; --blue:#60A5FA; --violet:#A78BFA; --cyan:#22D3EE; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif; color:var(--text); background:radial-gradient(circle at 12% 0%,#27345C 0,transparent 32%),radial-gradient(circle at 86% 10%,#4C1D95 0,transparent 30%),var(--bg); }
    .app-shell { max-width:1440px; margin:0 auto; padding:28px; }
    .cinematic-hero { min-height:260px; border:1px solid var(--line); border-radius:34px; padding:34px; background:linear-gradient(135deg,rgba(245,196,81,.20),rgba(96,165,250,.12)),rgba(255,255,255,.06); box-shadow:0 30px 100px rgba(0,0,0,.35); position:relative; overflow:hidden; }
    .hero-kicker { color:var(--gold); font-weight:900; letter-spacing:.18em; text-transform:uppercase; }
    h1 { font-size:clamp(42px,7vw,92px); line-height:.92; margin:14px 0; letter-spacing:-.06em; }
    h2 { margin:0 0 12px; }
    .hero-copy,.hint { color:var(--muted); line-height:1.8; }
    .privacy-pill { display:inline-flex; margin-top:14px; padding:9px 13px; border:1px solid rgba(74,222,128,.35); border-radius:999px; color:var(--green); background:rgba(74,222,128,.10); font-weight:900; }
    .step-rail { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin:22px 0; }
    .step-card { border:1px solid var(--line); border-radius:22px; padding:16px; background:rgba(255,255,255,.07); color:var(--muted); }
    .step-card b { display:block; color:var(--text); margin-bottom:4px; }
    .workspace { display:grid; grid-template-columns:390px 1fr; gap:22px; align-items:start; }
    .glass-panel { border:1px solid var(--line); border-radius:28px; padding:22px; background:var(--panel); backdrop-filter:blur(18px); box-shadow:0 24px 70px rgba(0,0,0,.28); }
    .homepage-studio { position:relative; }
    .homepage-studio:before { content:""; position:fixed; inset:0; pointer-events:none; background:linear-gradient(90deg,rgba(255,255,255,.03) 1px,transparent 1px),linear-gradient(rgba(255,255,255,.03) 1px,transparent 1px); background-size:72px 72px; mask-image:radial-gradient(circle at 50% 0%,#000 0,transparent 65%); }
    .cinema-nav { display:flex; gap:10px; flex-wrap:wrap; margin-top:20px; }
    .cinema-nav span { padding:9px 12px; border:1px solid var(--line); border-radius:999px; background:rgba(255,255,255,.07); color:var(--muted); font-weight:800; }
    .quick-actions { display:flex; gap:10px; flex-wrap:wrap; margin-top:16px; }
    .story-panel { border:1px solid var(--line); border-radius:24px; padding:18px; background:linear-gradient(135deg,rgba(255,255,255,.09),rgba(255,255,255,.035)); margin:14px 0; }

    .control-hero { display:grid; gap:10px; padding:18px; border:1px solid rgba(245,196,81,.22); border-radius:24px; background:radial-gradient(circle at 10% 0%,rgba(245,196,81,.20),transparent 46%),rgba(255,255,255,.06); }
    .control-hero b { font-size:22px; letter-spacing:-.03em; }
    .sync-command-center { display:grid; gap:18px; }
    .sync-health { display:grid; grid-template-columns:minmax(180px,.8fr) 1.2fr; gap:18px; align-items:stretch; padding:20px; border:1px solid rgba(96,165,250,.22); border-radius:28px; background:linear-gradient(135deg,rgba(15,23,42,.88),rgba(30,41,59,.72)); box-shadow:0 24px 70px rgba(0,0,0,.30); }
    .health-orb { min-height:180px; border-radius:24px; display:grid; place-items:center; text-align:center; background:radial-gradient(circle at 35% 25%,rgba(245,196,81,.45),transparent 28%),radial-gradient(circle at 70% 70%,rgba(96,165,250,.35),transparent 34%),linear-gradient(135deg,#111827,#312E81); }
    .health-orb b { display:block; font-size:58px; line-height:1; color:var(--gold); }
    .blocked-brief { border:1px solid rgba(251,113,133,.34); border-radius:24px; padding:18px; background:linear-gradient(135deg,rgba(251,113,133,.16),rgba(245,196,81,.08)); }
    .blocked-brief h3 { margin:4px 0 8px; font-size:26px; }
    .recovery-actions { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:10px; margin-top:12px; }
    .recovery-action { padding:12px; border:1px solid var(--line); border-radius:16px; background:rgba(255,255,255,.07); color:var(--text); line-height:1.55; }
    .diagnosis-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }
    .diagnosis-card { padding:14px; border:1px solid var(--line); border-radius:18px; background:rgba(255,255,255,.06); }
    .diagnosis-card b { display:block; color:var(--gold); margin-bottom:6px; }
    .sync-copy { max-width:780px; color:var(--muted); line-height:1.8; }
    .sync-playbook { display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:12px; margin-top:14px; }
    .playbook-card { border:1px solid rgba(245,196,81,.20); border-radius:20px; padding:14px; background:linear-gradient(145deg,rgba(245,196,81,.10),rgba(96,165,250,.06)); }
    .playbook-card b { display:block; color:var(--text); margin-bottom:6px; }
    .recovery-action b { display:block; color:var(--gold); margin-bottom:6px; }
    .progress-meter { height:8px; border-radius:999px; overflow:hidden; background:rgba(255,255,255,.10); margin-top:9px; }
    .progress-meter span { display:block; height:100%; border-radius:999px; background:linear-gradient(90deg,var(--gold),var(--cyan)); }
    .taste-dna { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:16px 0; }
    .tasteDNA { display:grid; gap:8px; }
    .dna-chip { padding:12px; border-radius:18px; border:1px solid rgba(245,196,81,.20); background:rgba(245,196,81,.08); }
    .image-resilience { max-width:100%; border-color:rgba(34,211,238,.28); background:rgba(34,211,238,.07); overflow-wrap:anywhere; word-break:break-word; }
    .image-resilience * { max-width:100%; overflow-wrap:anywhere; word-break:break-word; }
    .resilience-card { display:grid; gap:10px; max-width:100%; overflow:hidden; border:1px solid rgba(34,211,238,.18); border-radius:18px; padding:14px; margin-top:12px; background:rgba(2,6,23,.38); }
    .resilience-card code { display:block; max-width:100%; padding:10px 12px; border-radius:12px; background:rgba(15,23,42,.82); color:#CFFAFE; overflow-wrap:anywhere; word-break:break-word; white-space:pre-wrap; }
    label { display:block; color:var(--text); font-weight:800; margin:14px 0 7px; }
    input, textarea, select { width:100%; border:1px solid var(--line); border-radius:16px; padding:13px 14px; color:var(--text); background:rgba(255,255,255,.08); font:inherit; }
    input[type="checkbox"] { width:18px; height:18px; padding:0; margin:0 8px 0 0; accent-color:var(--gold); vertical-align:middle; }
    textarea { min-height:96px; resize:vertical; }
    .row { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    button { border:0; border-radius:16px; padding:12px 16px; font-weight:900; color:#101828; background:var(--gold); cursor:pointer; margin:4px 4px 4px 0; }
    button.ghost { color:var(--text); background:rgba(255,255,255,.10); border:1px solid var(--line); }
    details { border:1px solid var(--line); border-radius:18px; padding:12px; background:rgba(255,255,255,.06); margin-top:12px; }
    summary { cursor:pointer; font-weight:900; }
    .metric-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }
    .metric { padding:16px; border-radius:20px; background:var(--panel2); border:1px solid var(--line); }
    .metric b { display:block; font-size:30px; color:var(--gold); }
    .timeline { display:grid; gap:10px; margin-top:14px; }
    .timeline-row { padding:12px; border-radius:16px; background:rgba(255,255,255,.06); border:1px solid var(--line); }
    .tabs { display:flex; gap:10px; flex-wrap:wrap; margin:18px 0; }
    .tab { color:var(--text); background:rgba(255,255,255,.08); }
    .tab.active { background:var(--gold); color:#101828; }
    .hero-showcase { display:grid; grid-template-columns:minmax(180px,280px) 1fr; gap:22px; align-items:stretch; min-height:360px; margin:8px 0 22px; padding:22px; border:1px solid rgba(245,196,81,.24); border-radius:30px; background:radial-gradient(circle at 20% 10%,rgba(245,196,81,.20),transparent 35%),linear-gradient(135deg,rgba(15,23,42,.96),rgba(30,27,75,.86)); box-shadow:0 30px 90px rgba(0,0,0,.38); overflow:hidden; position:relative; }
    .category-spotlight { isolation:isolate; }
    .category-spotlight:after { content:""; position:absolute; inset:auto -15% -35% 30%; height:260px; background:radial-gradient(circle,rgba(167,139,250,.24),transparent 65%); z-index:-1; }
    .hero-poster { min-height:300px; border-radius:24px; overflow:hidden; background:#111827; box-shadow:0 24px 70px rgba(0,0,0,.40); }
    .hero-poster img { width:100%; height:100%; object-fit:cover; display:block; }
    .hero-meta { display:flex; flex-direction:column; justify-content:center; gap:12px; }
    .hero-meta h2 { font-size:clamp(30px,5vw,58px); line-height:1; letter-spacing:-.04em; margin:0; }
    .hero-track { display:grid; grid-template-columns:repeat(4,minmax(120px,1fr)); gap:10px; margin-top:8px; }
    .hero-slide { border:1px solid var(--line); border-radius:16px; padding:10px; background:rgba(255,255,255,.06); color:var(--muted); text-align:left; cursor:pointer; }
    .hero-slide.active { border-color:rgba(245,196,81,.65); color:var(--text); background:rgba(245,196,81,.13); }
    .hero-dots { display:flex; gap:7px; align-items:center; margin:8px 0; }
    .hero-dot { width:9px; height:9px; border-radius:50%; border:1px solid var(--line); background:rgba(255,255,255,.12); padding:0; margin:0; }
    .hero-dot.active { width:26px; border-radius:999px; background:var(--gold); }
    .meta-line { color:var(--muted); line-height:1.7; }
    .rail-wall { display:grid; gap:30px; }
    .media-rail { display:grid; gap:14px; }
    .rail-head { display:flex; align-items:end; justify-content:space-between; gap:14px; }
    .rail-title { font-size:24px; font-weight:950; letter-spacing:-.03em; }
    .rail-strip { display:grid; grid-auto-flow:column; grid-auto-columns:minmax(190px,220px); gap:18px; overflow-x:auto; padding:4px 4px 18px; scroll-snap-type:x proximity; }
    .rail-strip::-webkit-scrollbar { height:10px; }
    .rail-strip::-webkit-scrollbar-thumb { background:rgba(245,196,81,.32); border-radius:999px; }
    .poster-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:18px; }
    .poster-card { min-height:372px; border:1px solid var(--line); border-radius:24px; overflow:hidden; background:#111827; position:relative; box-shadow:0 20px 50px rgba(0,0,0,.28); transition:.18s ease; }
    .poster-card:hover { transform:translateY(-4px); border-color:rgba(245,196,81,.45); }
    .poster { height:242px; background:linear-gradient(145deg,#1f2937,#334155); display:flex; align-items:center; justify-content:center; text-align:center; padding:0; font-weight:900; }
    .poster img { width:100%; height:100%; object-fit:cover; display:block; }
    .poster-body { padding:14px; }
    .poster-body h3 { margin:10px 0 8px; }
    .badge { display:inline-flex; border:1px solid var(--line); border-radius:999px; padding:4px 8px; color:var(--muted); font-size:12px; margin:2px; }
    .micro-copy { color:var(--muted); font-size:13px; line-height:1.55; margin-top:8px; }
    .people-grid { display:grid; grid-template-columns:1fr; gap:12px; margin:14px 0; }
    .person-chip { display:inline-flex; align-items:center; gap:8px; padding:7px 10px; border:1px solid var(--line); border-radius:999px; background:rgba(255,255,255,.07); margin:3px; color:var(--text); }
    .person-chip .person-photo { width:30px; height:30px; min-width:30px; border-radius:50%; margin:0; box-shadow:none; }
    .avatar { width:30px; height:30px; display:inline-grid; place-items:center; border-radius:50%; background:linear-gradient(135deg,#F5C451,#60A5FA); color:#0B1020; font-weight:950; }
    .people-carousel { display:grid; grid-auto-flow:column; grid-auto-columns:minmax(150px,190px); gap:12px; overflow-x:auto; padding:6px 0 14px; margin:12px 0; }
    .person-card { border:1px solid var(--line); border-radius:20px; padding:12px; background:linear-gradient(180deg,rgba(255,255,255,.10),rgba(255,255,255,.04)); color:var(--text); text-align:left; min-height:214px; position:relative; overflow:hidden; }
    .person-card:before { content:""; position:absolute; inset:0; background:radial-gradient(circle at 30% 0%,rgba(245,196,81,.15),transparent 42%); pointer-events:none; }
    .person-card > * { position:relative; z-index:1; }
    .person-photo { width:100%; height:112px; display:block; border-radius:16px; overflow:hidden; margin-bottom:10px; background:linear-gradient(135deg,rgba(245,196,81,.22),rgba(96,165,250,.20)); box-shadow:0 16px 34px rgba(0,0,0,.30); }
    .person-photo img { width:100%; height:100%; object-fit:cover; display:block; }
    .portrait-fallback { border:1px solid rgba(245,196,81,.24); background:radial-gradient(circle at 30% 20%,rgba(245,196,81,.34),transparent 34%),linear-gradient(135deg,#111827,#312E81 58%,#0F172A); }
    .person-card .avatar { width:54px; height:54px; font-size:18px; margin-bottom:10px; }
    .person-card small { display:block; color:var(--muted); line-height:1.5; margin-top:6px; }
    .drawer-poster { width:150px; min-height:220px; border-radius:20px; overflow:hidden; background:#111827; margin:8px 0 18px; }
    .drawer-poster img { width:100%; height:100%; object-fit:cover; display:block; }
    .drawer { position:fixed; inset:0 0 0 auto; width:min(520px,100%); background:#0B1020; border-left:1px solid var(--line); transform:translateX(110%); transition:.25s ease; z-index:20; padding:26px; overflow:auto; }
    .drawer.open { transform:translateX(0); }
    .empty-state { padding:34px; border:1px dashed var(--line); border-radius:28px; text-align:center; color:var(--muted); }
    .mini-list { color:var(--muted); line-height:1.8; }
    .warn { color:var(--red); }
    @media(max-width:980px) { .workspace { grid-template-columns:1fr; } .metric-grid,.step-rail,.hero-showcase { grid-template-columns:1fr; } .hero-track { grid-template-columns:1fr 1fr; } .app-shell { padding:16px; } }
  </style>
</head>
<body>
  <main class="app-shell homepage-studio">
    <section class="cinematic-hero">
      <div class="hero-kicker">Local-first Douban Curation</div>
      <h1>CineScope Studio</h1>
      <p class="hero-copy">豆瓣私人影视策展器：同步你的看过与想看，分析口味，用电影、电视剧、动漫构建一面真正有吸引力的推荐海报墙。</p>
      <div class="privacy-pill">本地运行，不保存 Cookie</div>
      <div class="cinema-nav"><span>电影策展</span><span>剧集避雷</span><span>动漫补齐</span><span>图片韧性</span><span>口味 DNA</span></div>
    </section>
    <nav id="stepNav" class="step-rail" aria-label="任务步骤"></nav>
    <section class="workspace">
      <aside class="glass-panel" id="controlPanel"></aside>
      <section class="glass-panel" id="mainPanel"></section>
    </section>
  </main>
  <aside class="drawer" id="detailDrawer"></aside>
<script>
const state = { step:1, items:[], ratedItems:[], counts:{}, completeness:{}, errors:[], diagnostics:[], recommendations:[], visibleRecommendations:[], sections:[], activeSection:'全部', heroIndex:0, heroBySection:{}, ratingsCsv:'', candidatesCsv:'', profile:null, lastCounts:{}, recovery:null };
const $ = id => document.getElementById(id);
function esc(value) { return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
function setStatus(text) { const el = $('status'); if (el) el.textContent = text || ''; }
function renderStepNav() { const steps = [['第一步：连接豆瓣','同步看过 / 想看，校验 242 / 34 完整度'],['第二步：确认口味','评分高、剧情好，电视剧古装避雷'],['第三步：查看推荐','电影 / 电视剧 / 动漫海报墙']]; $('stepNav').innerHTML = steps.map((s,i) => `<div class="step-card"><b>${s[0]}</b>${s[1]}</div>`).join(''); }
function renderCookieGuide() { return `<details><summary>Cookie 教程</summary><ol class="mini-list"><li>打开浏览器并登录豆瓣。</li><li>进入 https://movie.douban.com/。</li><li>按 F12 打开开发者工具，进入 Network / 网络。</li><li>刷新页面，点任意 movie.douban.com 或 www.douban.com 请求。</li><li>在 Headers / 标头里找到 Request Headers。</li><li>复制 Cookie: 后面的整段内容，粘贴到这里。</li></ol><p class="hint">Cookie 只用于本机请求豆瓣页面，不会保存到磁盘，也不会出现在推荐报告里。</p></details>`; }
function imageResilienceGuide() { return `<details class="image-resilience" open><summary>图片韧性与 Clash / V2Ray 教程</summary><div class="resilience-card" id="imageResilienceGuide"><b>海报加载不出来时优先这样做</b><span class="hint">本项目会先走本地 /api/image-proxy，再失败才切换 SVG 标题海报。若你的网络需要代理，只配置本机 HTTP 代理端口，不要粘贴订阅地址。</span><code>PowerShell: $env:DOUBAN_RECOMMENDER_HTTP_PROXY="http://127.0.0.1:7890"</code><span class="hint">Clash 常见 Mixed Port 是 7890；V2Ray / v2rayN 可开启 HTTP 代理端口后填同样格式。不要粘贴订阅地址，订阅 URL 不会被项目保存，也不应该写进代码。</span></div></details>`; }
function renderCrawlerPanel() {
  $('controlPanel').innerHTML = `<h2>第一步：连接豆瓣</h2>
  <div class="control-hero"><span class="badge">Cookie 解锁 · 本地隐私</span><b>把抓取失败变成可恢复流程</b><p class="hint">匿名访问遇到 403 时，页面会直接告诉你：豆瓣要求登录态、需要 Cookie，或可以跳过同步继续用高质量片库生成推荐。</p></div>
  <div class="story-panel"><b>全站同步、口味、推荐和详情统一重做</b><p class="hint">这里不再是冷冰冰的日志区，而是“同步作战室”：目标完整度、失败原因、恢复路线和下一步动作会一起显示。</p></div>
  <label>豆瓣用户 ID 或主页链接</label><input id="doubanUser" placeholder="https://www.douban.com/people/你的ID/">
  <label>Cookie（可选）</label><textarea id="doubanCookie" placeholder="如果出现 403 / 登录跳转，把浏览器请求里的 Cookie 粘贴到这里；同步后输入框会自动清空"></textarea>
  <div class="row"><div><label>期望看过</label><input id="expectedCollect" type="number" value="242"></div><div><label>期望想看</label><input id="expectedWish" type="number" value="34"></div></div>
  <label>最多抓取页数</label><input id="maxPages" type="number" min="1" max="200" value="60">
  <label><input id="includeWish" type="checkbox" checked> 同步想看</label>
  ${renderCookieGuide()}${imageResilienceGuide()}
  <details><summary>没有抓取数据？粘贴 CSV 继续</summary><label>评分 CSV</label><textarea id="ratingsCsv" placeholder="title,my_rating,media_type,genres,tags">${esc(state.ratingsCsv)}</textarea><label>候选 CSV</label><textarea id="candidatesCsv" placeholder="title,media_type,douban_rating,genres,tags">${esc(state.candidatesCsv)}</textarea><button class="ghost" onclick="useCsvInputs()">使用 CSV 继续</button></details>
  <div class="quick-actions"><button onclick="syncDouban()">同步豆瓣</button><button class="ghost" onclick="continueWithoutSync()">继续用高质量片库生成推荐</button><button class="ghost" onclick="clearCache()">清空缓存</button></div><div id="status" class="hint"></div>`;
  renderCrawlSummary();
}
function renderSyncRecovery(recovery) {
  if (!recovery || !recovery.status || recovery.status === 'idle') return '';
  const labels = ['Cookie 解锁','继续推荐','CSV 兜底'];
  const actions = (recovery.actions || []).map((x,i) => `<div class="recovery-action"><b>${esc(labels[i] || '恢复路线')}</b>${esc(x)}</div>`).join('');
  const cta = recovery.can_continue_without_sync ? `<div class="quick-actions"><button onclick="continueWithoutSync()">继续用高质量片库生成推荐</button><button class="ghost" onclick="document.getElementById('doubanCookie')?.focus()">粘贴 Cookie 重试</button></div>` : '';
  return `<section class="blocked-brief"><span class="badge">豆瓣要求登录态 · Recovery</span><h3>${esc(recovery.headline || '豆瓣要求登录态或 Cookie')}</h3><p class="sync-copy">这不是你的 ID 错，也不是页数太少。豆瓣当前返回登录跳转 / 403，匿名抓取被拦截。你可以走 Cookie 解锁，也可以先跳过同步，用内置高分电影、电视剧、动漫片库生成推荐。</p><div class="recovery-actions">${actions}</div>${cta}</section>`;
}
function syncCommandCenter(c, rows, errorSummary) {
  const recovery = state.recovery || {};
  const completeness = state.completeness || {};
  const collect = Number(c.collect_count ?? 0);
  const wish = Number(c.wish_count ?? 0);
  const total = collect + wish;
  const collectPercent = Number(completeness.collect_percent ?? (collect ? 100 : 0));
  const wishPercent = Number(completeness.wish_percent ?? (wish ? 100 : 0));
  const health = recovery.status === 'needs_cookie' ? '需要 Cookie' : total ? '可用资料库' : '等待同步';
  const diagnosis = rows || '<div class="empty-state">还没有同步诊断。点击左侧同步；如果出现 403，这里会给出 Cookie 解锁、CSV 兜底和继续推荐路线。</div>';
  return `<div class="sync-command-center"><section class="sync-health"><div class="health-orb"><div><b>${esc(total)}</b><span>${esc(health)}</span></div></div><div><span class="badge">同步作战室</span><h2>同步诊断</h2><p class="sync-copy">目标是尽量拿到你的 242 部看过和 34 部想看；拿不到时不再只丢出 HTTP Error，而是拆解为登录态、权限、安全验证、解析结构和网络五类问题。</p><div class="metric-grid"><div class="metric"><b>${esc(collect)}</b>看过数量<div class="progress-meter"><span style="width:${Math.max(0, Math.min(100, collectPercent))}%"></span></div></div><div class="metric"><b>${esc(wish)}</b>想看数量<div class="progress-meter"><span style="width:${Math.max(0, Math.min(100, wishPercent))}%"></span></div></div><div class="metric"><b>${esc(c.pages_ok ?? 0)}</b>成功页</div><div class="metric"><b>${esc(c.pages_failed ?? 0)}</b>失败页</div></div></div></section>${renderSyncRecovery(recovery)}<div class="sync-playbook"><div class="playbook-card"><b>1. Cookie 解锁</b><span class="hint">登录豆瓣后复制请求 Cookie，只用于本机抓取。</span></div><div class="playbook-card"><b>2. 本地片库继续</b><span class="hint">不用等抓取成功，也能生成电影 / 电视剧 / 动漫推荐。</span></div><div class="playbook-card"><b>3. CSV 精准导入</b><span class="hint">如果你有导出的评分表，可直接粘贴保持最高完整度。</span></div></div><p class="hint">停止原因：${esc(c.stopped_reason || recovery.headline || '-')}</p>${errorSummary}<div id="syncTimeline" class="timeline diagnosis-grid">${diagnosis}</div></div>`;
}
function renderCrawlSummary() {
  const c = state.counts || {};
  const rows = (state.diagnostics || []).slice(0,12).map(d => `<div class="timeline-row diagnosis-card"><b>${esc(d.status)} start=${esc(d.start)}${d.http_status ? ' · HTTP ' + esc(d.http_status) : ''}</b><br>${esc(d.classification)} · ${esc(d.message)} · ${esc(d.item_count)} 条</div>`).join('');
  const errorSummary = (state.errors || []).length ? `<h3>错误摘要</h3><ul class="mini-list">${state.errors.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '';
  $('mainPanel').innerHTML = syncCommandCenter(c, rows, errorSummary);
}
function continueWithoutSync() { state.items = []; state.ratedItems = []; renderTastePanel(); setStatus('已进入本地高质量片库模式：电影 / 电视剧 / 动漫都会参与推荐。'); }
function tasteDNA() { const profile = state.profile || {}; const chips = []; (profile.top_genres || []).slice(0,5).forEach(([name, value]) => chips.push(`<div class="dna-chip"><b>${esc(name)}</b><span class="hint">偏好强度 ${esc(value)}</span></div>`)); (profile.top_directors || []).slice(0,3).forEach(([name]) => chips.push(`<div class="dna-chip"><b>${esc(name)}</b><span class="hint">导演偏好</span></div>`)); if (!chips.length) chips.push(`<div class="dna-chip"><b>剧情优先</b><span class="hint">默认按高分、叙事、人物塑造起步</span></div>`, `<div class="dna-chip"><b>剧集避雷</b><span class="hint">电视剧古装和注水剧强降权</span></div>`, `<div class="dna-chip"><b>动漫补齐</b><span class="hint">默认补足高分动漫剧集候选</span></div>`); return `<div class="taste-dna tasteDNA">${chips.join('')}</div>`; }
function renderTastePanel() { state.step = 2; renderStepNav(); $('controlPanel').innerHTML = `<h2>第二步：确认口味</h2><div class="story-panel"><b>不要死板打标签</b><p class="hint">你可以什么都看，系统会把“高分 + 剧情好 + 叙事强 + 人物塑造”作为主轴，再把电视剧古装、注水和狗血当作软避雷。</p></div><label>一句话告诉我最近想看什么</label><textarea id="likeTerms">评分高，剧情好，叙事强，人物塑造扎实，电影/电视剧/动漫都可以</textarea><label>明确避雷</label><textarea id="dislikeTerms">电视剧古装，注水剧，低分狗血，粗制滥造</textarea><label><input id="includeMovies" type="checkbox" checked> 电影</label><label><input id="includeSeries" type="checkbox" checked> 电视剧</label><label><input id="includeAnime" type="checkbox" checked> 动漫</label><label><input id="fetchDouban" type="checkbox" checked> 从豆瓣探索候选池补充</label><label><input id="enrichDetails" type="checkbox" checked> 补全简介、海报和演职员</label><label>推荐数量</label><input id="limit" type="number" min="24" max="300" value="160"><div class="quick-actions"><button onclick="recommend()">生成推荐</button><button class="ghost" onclick="renderCrawlerPanel()">返回同步</button></div><div id="status" class="hint"></div>`; $('mainPanel').innerHTML = `<h2>你的资料库</h2><div class="metric-grid"><div class="metric"><b>${state.items.length || state.ratedItems.length || 0}</b>条目</div><div class="metric"><b>${esc((state.sections || []).length)}</b>推荐分区</div><div class="metric"><b>${esc(state.lastCounts.curated_candidates ?? 0)}</b>本地精选补齐</div><div class="metric"><b>3</b>电影 / 剧集 / 动漫</div></div><h3>口味 DNA</h3>${tasteDNA()}<p class="hint">系统会用高分条目学习偏好，用低分条目学习避雷，并自动排除已经看过的条目。想看条目会作为想看优先提示。</p>`; }
function recTitle(r) { return r.title || r.item?.title || 'CineScope'; }
function recType(r) { return r.media_type || r.item?.media_type || ''; }
function recArray(r, key) { return Array.isArray(r[key]) ? r[key] : (Array.isArray(r.item?.[key]) ? r.item[key] : []); }
function itemKey(r) { return String(r.douban_id || r.item?.douban_id || recTitle(r)); }
function posterUrl(r) { const raw = r.cover || r.item?.cover || ''; return /^https?:\/\//.test(raw) ? `/api/image-proxy?url=${encodeURIComponent(raw)}` : raw; }
function posterFallback(title, mediaType) { const safeTitle = esc(title || 'CineScope'); const safeType = esc(mediaType || '私人推荐'); const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="960" viewBox="0 0 640 960"><defs><linearGradient id="g" x1="0" x2="1" y1="0" y2="1"><stop stop-color="#1E293B"/><stop offset="0.52" stop-color="#312E81"/><stop offset="1" stop-color="#0F172A"/></linearGradient><radialGradient id="r" cx="30%" cy="10%" r="70%"><stop stop-color="#F5C451" stop-opacity=".55"/><stop offset="1" stop-color="#F5C451" stop-opacity="0"/></radialGradient></defs><rect width="640" height="960" fill="url(#g)"/><rect width="640" height="960" fill="url(#r)"/><text x="52" y="120" fill="#F5C451" font-size="28" font-family="Arial" font-weight="800" letter-spacing="5">${safeType}</text><foreignObject x="52" y="230" width="536" height="430"><div xmlns="http://www.w3.org/1999/xhtml" style="font-family:Arial,Microsoft YaHei,sans-serif;color:#F8FAFC;font-size:74px;font-weight:950;line-height:1.06;letter-spacing:-3px;">${safeTitle}</div></foreignObject><text x="52" y="850" fill="#A7B0C0" font-size="24" font-family="Arial">CineScope Studio</text></svg>`; return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`; }
function safePosterImg(r) { const title = recTitle(r); const type = recType(r); const fallback = posterFallback(title, type); const safeFallback = fallback.replace(/'/g, '%27'); const rawSrc = posterUrl(r) || safeFallback; const src = rawSrc === fallback ? safeFallback : rawSrc; return `<img src="${esc(src)}" alt="${esc(title)}" referrerpolicy="no-referrer" onerror="this.onerror=null;this.src='${safeFallback}'">`; }
function posterHtml(r) { return safePosterImg(r); }
function metadataLine(r) { const parts = []; if (r.year || r.item?.year) parts.push(r.year || r.item.year); if (recType(r)) parts.push(recType(r)); recArray(r,'genres').slice(0,3).forEach(x => parts.push(x)); recArray(r,'countries').slice(0,2).forEach(x => parts.push(x)); return parts.map(esc).join(' · ') || '类型信息待补全'; }
function peoplePhotoMap(r) { return r?.people_photos || r?.item?.people_photos || r?.raw?.people_photos || r?.item?.raw?.people_photos || {}; }
function personPhotoSvg(name, role) { const initials = esc(String(name || '?').trim().slice(0,2).toUpperCase()); const safeName = esc(name || '人物肖像'); const safeRole = esc(role || '演职员'); const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="360" height="420" viewBox="0 0 360 420"><defs><linearGradient id="g" x1="0" x2="1" y1="0" y2="1"><stop stop-color="#F5C451"/><stop offset=".48" stop-color="#60A5FA"/><stop offset="1" stop-color="#312E81"/></linearGradient><radialGradient id="r" cx="30%" cy="15%" r="75%"><stop stop-color="#fff" stop-opacity=".35"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient></defs><rect width="360" height="420" rx="34" fill="#0B1020"/><rect width="360" height="420" rx="34" fill="url(#g)" opacity=".82"/><rect width="360" height="420" rx="34" fill="url(#r)"/><circle cx="180" cy="150" r="64" fill="rgba(11,16,32,.72)"/><path d="M76 344c14-72 68-112 104-112s90 40 104 112" fill="rgba(11,16,32,.72)"/><text x="180" y="164" text-anchor="middle" fill="#F8FAFC" font-size="44" font-family="Arial,Microsoft YaHei,sans-serif" font-weight="900">${initials}</text><text x="28" y="56" fill="#0B1020" font-size="22" font-family="Arial,Microsoft YaHei,sans-serif" font-weight="900">${safeRole}</text><text x="28" y="386" fill="#F8FAFC" font-size="24" font-family="Arial,Microsoft YaHei,sans-serif" font-weight="800">${safeName}</text></svg>`; return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg).replace(/'/g, '%27')}`; }
function personPhotoUrl(person) { const raw = person.photo || ''; return /^https?:\/\//.test(raw) ? `/api/image-proxy?url=${encodeURIComponent(raw)}` : raw; }
function personPortrait(person) { const fallback = personPhotoSvg(person.name, person.role); const src = personPhotoUrl(person) || fallback; const safeFallback = fallback.replace(/'/g, '%27'); const cls = person.photo ? 'person-photo' : 'person-photo portrait-fallback'; return `<span class="${cls}" title="${esc(person.role)}人物肖像"><img src="${esc(src)}" alt="${esc(person.name)} 人物肖像" referrerpolicy="no-referrer" onerror="this.onerror=null;this.src='${safeFallback}'"></span>`; }
function peopleForItem(r) { const photos = peoplePhotoMap(r); const photoFor = (name, role) => photos[name] || photos[`${role}:${name}`] || photos[`导演:${name}`] || photos[`主演:${name}`] || ''; const people = []; recArray(r,'directors').slice(0,4).forEach(name => people.push({name, role:'导演', photo:photoFor(name,'导演')})); recArray(r,'casts').slice(0,8).forEach(name => people.push({name, role:'主演', photo:photoFor(name,'主演')})); return people; }
function peopleChips(names, role, r=null) { const list = (names || []).slice(0,8); if (!list.length) return `<p class="hint">${role}资料待补全</p>`; const photos = peoplePhotoMap(r || {}); return list.map(name => { const person = {name, role, photo:photos[name] || photos[`${role}:${name}`] || ''}; return `<span class="person-chip">${personPortrait(person)}<span><b>${esc(name)}</b><small class="hint"> · ${esc(role)}</small></span></span>`; }).join(''); }
function peopleCarousel(r) { const people = peopleForItem(r); if (!people.length) return `<p class="hint">人物资料待补全。</p>`; return `<div class="people-carousel">${people.map(person => { const encoded = encodeURIComponent(person.name || ''); return `<button class="person-card" onclick="filterByPerson('${encoded}')">${personPortrait(person)}<b>${esc(person.name)}</b><small>${esc(person.role)} · 点击查看 TA 参与的相关推荐</small></button>`; }).join('')}</div>`; }
function filterByPerson(encodedName) { const name = decodeURIComponent(encodedName || ''); if (!name) return; const matched = (state.recommendations || []).filter(item => recArray(item,'directors').includes(name) || recArray(item,'casts').includes(name)); if (!matched.length) return; const sectionName = `人物：${name}`; state.sections = [{name:sectionName, count:matched.length, items:matched}, ...(state.sections || []).filter(s => s.name !== sectionName)]; state.activeSection = sectionName; $('detailDrawer').classList.remove('open'); renderRecommendations(); }
function sectionItems(name) { const all = state.recommendations || []; if (name === '全部') return all; if (name === '精选') return all.slice(0,24); if (['电影','电视剧','动漫'].includes(name)) return all.filter(r => recType(r) === name); const found = (state.sections || []).find(s => s.name === name); return found?.items || []; }
function buildMediaRails() { const names = ['精选','电影','电视剧','动漫','必看 Top Picks','高分剧情','想看优先']; const rails = []; const seen = new Set(); for (const name of names) { const items = sectionItems(name); if (items.length && !seen.has(name)) { rails.push({ name, items }); seen.add(name); } } for (const section of state.sections || []) { if (!seen.has(section.name) && section.items?.length) rails.push({ name:section.name, items:section.items }); } return rails; }
function mediaCard(r, index) { const key = encodeURIComponent(itemKey(r)); return `<article class="poster-card" onclick="openDetailByKey('${key}')"><div class="poster">${safePosterImg(r)}</div><div class="poster-body"><span class="badge">${esc(recType(r) || '媒体')}</span><span class="badge">豆瓣 ${esc(r.douban_rating || r.item?.douban_rating || '-')}</span><h3>${esc(recTitle(r))}</h3><div class="meta-line">${metadataLine(r)}</div><p class="micro-copy">${esc(r.summary || r.item?.summary || r.short_reason || (r.reasons || [])[0] || '质量优先策略推荐')}</p><details><summary>展开详情</summary>点击卡片打开完整抽屉。</details></div></article>`; }
function selectSection(name) { state.activeSection = name; renderRecommendations(); }
function renderMediaRail(name, items) { return `<section class="media-rail"><div class="rail-head"><div class="rail-title">${esc(name)}</div><button class="ghost" onclick="selectSection('${esc(name)}')">查看全部</button></div><div class="rail-strip">${items.map(mediaCard).join('')}</div></section>`; }
function spotlightPool(name) { const scoped = sectionItems(name || state.activeSection); if (scoped.length) return scoped; const featured = sectionItems('精选'); return featured.length ? featured : (state.recommendations || []); }
function heroIndexFor(name, total) { const raw = state.heroBySection[name] ?? state.heroIndex ?? 0; return total ? Math.abs(raw) % total : 0; }
function setHeroForSection(name, index) { state.heroBySection[name] = index; renderRecommendations(); }
function nextHeroForSection(name, delta) { const rows = spotlightPool(name); const current = heroIndexFor(name, rows.length); setHeroForSection(name, current + delta + rows.length); }
function categorySpotlight(name) { return renderHeroCarousel(name); }
function renderHeroCarousel(name = state.activeSection) { const rows = spotlightPool(name).slice(0,8); if (!rows.length) return ''; const idx = heroIndexFor(name, rows.length); const r = rows[idx]; const directors = recArray(r,'directors').slice(0,2).join('、'); const casts = recArray(r,'casts').slice(0,4).join('、'); const key = encodeURIComponent(itemKey(r)); const slides = rows.slice(0,4).map((item,i) => `<button class="hero-slide ${i===idx ? 'active' : ''}" onclick="setHeroForSection('${esc(name)}',${i})"><b>${esc(recTitle(item))}</b><br><span>${esc(metadataLine(item))}</span></button>`).join(''); const dots = rows.map((_,i) => `<button class="hero-dot ${i===idx ? 'active' : ''}" aria-label="第 ${i+1} 张焦点" onclick="setHeroForSection('${esc(name)}',${i})"></button>`).join(''); return `<section class="hero-showcase category-spotlight" id="heroShowcase"><div class="hero-poster">${safePosterImg(r)}</div><div class="hero-meta"><span class="badge">${esc(name)}焦点 · 今日最值得看</span><h2>${esc(recTitle(r))}</h2><div class="meta-line">${metadataLine(r)} · 豆瓣 ${esc(r.douban_rating || '-')}</div><p class="hero-copy">${esc(r.summary || r.short_reason || (r.reasons || [])[0] || '根据你的高分偏好与避雷设置精选。')}</p><p class="hint">${directors ? '导演：' + esc(directors) : ''}${casts ? ' · 主演：' + esc(casts) : ''}</p><div class="hero-dots">${dots}</div><div class="hero-track">${slides}</div><div><button onclick="openDetailByKey('${key}')">打开详情</button><button class="ghost" onclick="nextHeroForSection('${esc(name)}',1)">换一部</button></div></div></section>`; }
function renderHeroShowcase() { return renderHeroCarousel(state.activeSection); }
function renderRecommendations() { state.step = 3; renderStepNav(); const sectionNames = ['全部','精选','电影','电视剧','动漫', ...(state.sections || []).map(s => s.name)].filter((x,i,a)=>x && a.indexOf(x)===i); const tabs = sectionNames.map(name => `<button class="tab ${state.activeSection === name ? 'active' : ''}" onclick="selectSection('${esc(name)}')">${esc(name)}</button>`).join(''); const items = sectionItems(state.activeSection); state.visibleRecommendations = items; const focusedGrid = items.length ? `<section class="media-rail"><div class="rail-head"><div class="rail-title">${esc(state.activeSection)} · 当前筛选</div><span class="hint">${items.length} 部</span></div><div class="poster-grid">${items.map(mediaCard).join('')}</div></section>` : '<div class="empty-state">这个分类暂时没有结果。默认候选池会自动用本地高分片单补齐电影 / 电视剧 / 动漫。</div>'; const rails = buildMediaRails().map(rail => renderMediaRail(rail.name, rail.items.slice(0,24))).join(''); $('controlPanel').innerHTML = `<h2>第三步：查看推荐</h2><p class="hint">每个分类都有独立焦点轮播；电影、电视剧、动漫会按各自片池展示，不再共用一张 Hero。</p><div class="metric-grid"><div class="metric"><b>${state.recommendations.length}</b>推荐</div><div class="metric"><b>${esc(state.lastCounts.candidates ?? '-')}</b>候选</div></div><h3>口味 DNA</h3>${tasteDNA()}<div class="quick-actions"><button class="ghost" onclick="renderTastePanel()">调整口味</button><button class="ghost" onclick="renderCrawlerPanel()">重新同步</button></div>${imageResilienceGuide()}`; $('mainPanel').innerHTML = `<h2>私人推荐片单</h2><div class="tabs">${tabs}</div>${categorySpotlight(state.activeSection)}<div class="rail-wall" id="railWall">${focusedGrid}${rails || '<div class="empty-state">还没有推荐。先同步豆瓣或直接生成 quality-first 推荐。</div>'}</div>`; }
function openDetail(index) { const r = state.visibleRecommendations[index]; if (!r) return; openDetailObject(r); }
function openDetailByKey(encodedKey) { const key = decodeURIComponent(encodedKey || ''); const all = [...(state.recommendations || []), ...(state.visibleRecommendations || [])]; const r = all.find(x => itemKey(x) === key); if (r) openDetailObject(r); }
function openDetailObject(r) { $('detailDrawer').classList.add('open'); $('detailDrawer').innerHTML = `<button class="ghost" onclick="$('detailDrawer').classList.remove('open')">关闭</button><div class="drawer-poster">${safePosterImg(r)}</div><h2>${esc(recTitle(r))}</h2><p class="meta-line">${metadataLine(r)} · 豆瓣 ${esc(r.douban_rating || r.item?.douban_rating || '-')}</p><h3>剧情简介</h3><p class="hint">${esc(r.summary || r.item?.summary || '暂无官方简介，可先根据推荐理由判断是否加入片单。')}</p><h3>演职员胶片带</h3>${peopleCarousel(r)}<div class="people-grid"><div><h3>导演</h3>${peopleChips(recArray(r,'directors'), '导演', r)}</div><div><h3>主演</h3>${peopleChips(recArray(r,'casts'), '主演', r)}</div></div><h3>推荐理由</h3><ul>${(r.reasons || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul><h3>风险提示</h3><ul>${(r.warnings || []).map(x => `<li class="warn">${esc(x)}</li>`).join('') || '<li class="hint">没有明显避雷信号。</li>'}</ul><p><a href="${esc(r.url || '#')}" target="_blank" rel="noreferrer">打开豆瓣</a></p>`; }
async function syncDouban() { setStatus('正在同步豆瓣。'); const cookieBox = $('doubanCookie'); const payload = { user_id_or_url:$('doubanUser').value, cookie:cookieBox.value, max_pages:Number($('maxPages').value || 40), include_wish:$('includeWish').checked, expected_collect:Number($('expectedCollect').value || 0), expected_wish:Number($('expectedWish').value || 0) }; cookieBox.value = ''; const res = await fetch('/api/sync-douban', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) }); const data = await res.json(); if (!res.ok || data.error) { setStatus('同步失败：' + (data.error || '请求失败')); return; } state.items = data.items || []; state.ratedItems = state.items; state.counts = data.counts || {}; state.completeness = data.completeness || {}; state.diagnostics = data.diagnostics || []; state.errors = data.errors || []; state.recovery = data.recovery || null; renderCrawlSummary(); if (state.recovery?.status === 'needs_cookie') setStatus('豆瓣要求登录态：可粘贴 Cookie 重试，也可继续用高质量片库生成推荐。'); else setStatus(`同步完成：${state.items.length} 条资料已进入口味分析。`); }
function useCsvInputs() { state.items = []; state.ratedItems = []; state.ratingsCsv = $('ratingsCsv').value; state.candidatesCsv = $('candidatesCsv').value; renderTastePanel(); }
async function clearCache() { await fetch('/api/cache', { method:'DELETE' }); $('mainPanel').innerHTML = '<div class="empty-state">本地缓存已清空。</div>'; }
async function recommend() { setStatus('正在生成推荐。'); const payload = { rated_items:state.items, ratings_csv: state.items.length ? '' : state.ratingsCsv, candidates_csv: state.candidatesCsv, like_terms:$('likeTerms').value, dislike_terms:$('dislikeTerms').value, include_movies:$('includeMovies').checked, include_series:$('includeSeries').checked, include_anime:$('includeAnime').checked, fetch_douban:$('fetchDouban').checked, enrich_details:$('enrichDetails') ? $('enrichDetails').checked : true, use_sample_candidates:!state.candidatesCsv, limit:Number($('limit').value || 160) }; const res = await fetch('/api/recommend', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) }); const data = await res.json(); if (!res.ok || data.error) { setStatus('推荐失败：' + (data.error || '请求失败')); return; } state.recommendations = data.results || []; state.sections = data.sections || []; state.profile = data.profile || null; state.lastCounts = data.counts || {}; state.heroBySection = {}; renderRecommendations(); }
function crawlDouban() { return syncDouban(); }
function goStep(step) { if (step === 1) renderCrawlerPanel(); if (step === 2) renderTastePanel(); if (step === 3) renderRecommendations(); }
renderStepNav(); renderCrawlerPanel();
</script>
</body>
</html>"""
