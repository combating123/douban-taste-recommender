from __future__ import annotations

INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CineScope Studio：豆瓣私人影视策展器</title>
  <style>
    :root { --bg:#070A12; --panel:rgba(16,22,36,.80); --panel2:rgba(255,255,255,.08); --text:#F8FAFC; --muted:#A7B0C0; --line:rgba(255,255,255,.13); --gold:#F5C451; --green:#4ADE80; --red:#FB7185; --blue:#60A5FA; }
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
    .hero-showcase { display:grid; grid-template-columns:minmax(180px,260px) 1fr; gap:22px; align-items:stretch; min-height:340px; margin:8px 0 22px; padding:22px; border:1px solid rgba(245,196,81,.24); border-radius:30px; background:radial-gradient(circle at 20% 10%,rgba(245,196,81,.20),transparent 35%),linear-gradient(135deg,rgba(15,23,42,.96),rgba(30,27,75,.86)); box-shadow:0 30px 90px rgba(0,0,0,.38); overflow:hidden; }
    .hero-poster { min-height:300px; border-radius:24px; overflow:hidden; background:#111827; box-shadow:0 24px 70px rgba(0,0,0,.40); }
    .hero-poster img { width:100%; height:100%; object-fit:cover; display:block; }
    .hero-meta { display:flex; flex-direction:column; justify-content:center; gap:12px; }
    .hero-meta h2 { font-size:clamp(30px,5vw,58px); line-height:1; letter-spacing:-.04em; margin:0; }
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
    .avatar { width:30px; height:30px; display:inline-grid; place-items:center; border-radius:50%; background:linear-gradient(135deg,#F5C451,#60A5FA); color:#0B1020; font-weight:950; }
    .drawer-poster { width:150px; min-height:220px; border-radius:20px; overflow:hidden; background:#111827; margin:8px 0 18px; }
    .drawer-poster img { width:100%; height:100%; object-fit:cover; display:block; }
    .drawer { position:fixed; inset:0 0 0 auto; width:min(520px,100%); background:#0B1020; border-left:1px solid var(--line); transform:translateX(110%); transition:.25s ease; z-index:20; padding:26px; overflow:auto; }
    .drawer.open { transform:translateX(0); }
    .empty-state { padding:34px; border:1px dashed var(--line); border-radius:28px; text-align:center; color:var(--muted); }
    .mini-list { color:var(--muted); line-height:1.8; }
    .warn { color:var(--red); }
    @media(max-width:980px) { .workspace { grid-template-columns:1fr; } .metric-grid,.step-rail { grid-template-columns:1fr; } .app-shell { padding:16px; } }
  </style>
</head>
<body>
  <main class="app-shell">
    <section class="cinematic-hero">
      <div class="hero-kicker">Local-first Douban Curation</div>
      <h1>CineScope Studio</h1>
      <p class="hero-copy">豆瓣私人影视策展器：同步你的看过与想看，分析口味，用电影、电视剧、动漫构建一面真正有吸引力的推荐海报墙。</p>
      <div class="privacy-pill">本地运行，不保存 Cookie</div>
    </section>
    <nav id="stepNav" class="step-rail" aria-label="任务步骤"></nav>
    <section class="workspace">
      <aside class="glass-panel" id="controlPanel"></aside>
      <section class="glass-panel" id="mainPanel"></section>
    </section>
  </main>
  <aside class="drawer" id="detailDrawer"></aside>
<script>
const state = { step:1, items:[], ratedItems:[], counts:{}, errors:[], diagnostics:[], recommendations:[], visibleRecommendations:[], sections:[], activeSection:'全部', heroIndex:0, ratingsCsv:'', candidatesCsv:'', profile:null };
const $ = id => document.getElementById(id);
function esc(value) { return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
function setStatus(text) { const el = $('status'); if (el) el.textContent = text || ''; }
function renderStepNav() { const steps = [['第一步：连接豆瓣','同步看过 / 想看，校验 242 / 34 完整度'],['第二步：确认口味','评分高、剧情好，电视剧古装避雷'],['第三步：查看推荐','电影 / 电视剧 / 动漫海报墙']]; $('stepNav').innerHTML = steps.map((s,i) => `<div class="step-card"><b>${s[0]}</b>${s[1]}</div>`).join(''); }
function renderCookieGuide() { return `<details><summary>Cookie 教程</summary><ol class="mini-list"><li>打开浏览器并登录豆瓣。</li><li>进入 https://movie.douban.com/。</li><li>按 F12 打开开发者工具，进入 Network / 网络。</li><li>刷新页面，点任意 movie.douban.com 或 www.douban.com 请求。</li><li>在 Headers / 标头里找到 Request Headers。</li><li>复制 Cookie: 后面的整段内容，粘贴到这里。</li></ol><p class="hint">Cookie 只用于本机请求豆瓣页面，不会保存到磁盘，也不会出现在推荐报告里。</p></details>`; }
function renderCrawlerPanel() { $('controlPanel').innerHTML = `<h2>第一步：连接豆瓣</h2><p class="hint">公开页够用就不填 Cookie；如果抓成 0 / 0，再粘贴 Cookie 并查看同步诊断。</p><label>豆瓣用户 ID 或主页链接</label><input id="doubanUser" placeholder="https://www.douban.com/people/你的ID/"><label>Cookie（可选）</label><textarea id="doubanCookie" placeholder="公开数据够用就不用填"></textarea><div class="row"><div><label>期望看过</label><input id="expectedCollect" type="number" value="242"></div><div><label>期望想看</label><input id="expectedWish" type="number" value="34"></div></div><label>最多抓取页数</label><input id="maxPages" type="number" min="1" max="200" value="40"><label><input id="includeWish" type="checkbox" checked> 同步想看</label>${renderCookieGuide()}<details><summary>没有抓取数据？粘贴 CSV</summary><label>评分 CSV</label><textarea id="ratingsCsv" placeholder="title,my_rating,media_type,genres,tags">${esc(state.ratingsCsv)}</textarea><label>候选 CSV</label><textarea id="candidatesCsv" placeholder="title,media_type,douban_rating,genres,tags">${esc(state.candidatesCsv)}</textarea><button class="ghost" onclick="useCsvInputs()">使用 CSV 继续</button></details><button onclick="syncDouban()">同步豆瓣</button><button class="ghost" onclick="renderTastePanel()">下一步：确认口味</button><button class="ghost" onclick="clearCache()">清空缓存</button><div id="status" class="hint"></div>`; renderCrawlSummary(); }
function renderCrawlSummary() { const c = state.counts || {}; const rows = (state.diagnostics || []).slice(0,12).map(d => `<div class="timeline-row"><b>${esc(d.status)} start=${esc(d.start)}</b><br>${esc(d.classification)} · ${esc(d.message)} · ${esc(d.item_count)} 条</div>`).join(''); const errorSummary = (state.errors || []).length ? `<h3>错误摘要</h3><ul class="mini-list">${state.errors.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''; $('mainPanel').innerHTML = `<h2>同步诊断</h2><div class="metric-grid"><div class="metric"><b>${esc(c.collect_count ?? 0)}</b>看过数量</div><div class="metric"><b>${esc(c.wish_count ?? 0)}</b>想看数量</div><div class="metric"><b>${esc(c.pages_ok ?? 0)}</b>成功页</div><div class="metric"><b>${esc(c.pages_failed ?? 0)}</b>失败页</div></div><p class="hint">停止原因：${esc(c.stopped_reason || '-')}</p>${errorSummary}<div id="syncTimeline" class="timeline">${rows || '<div class="empty-state">还没有同步诊断。先从左侧同步豆瓣；如果出现 0 / 0，这里会告诉你是 Cookie、隐私、验证还是解析问题。</div>'}</div>`; }
function renderTastePanel() { state.step = 2; renderStepNav(); $('controlPanel').innerHTML = `<h2>第二步：确认口味</h2><label>一句话告诉我最近想看什么</label><textarea id="likeTerms">评分高，剧情好，叙事强，人物塑造扎实，电影/电视剧/动漫都可以</textarea><label>明确避雷</label><textarea id="dislikeTerms">电视剧古装，注水剧，低分狗血，粗制滥造</textarea><label><input id="includeMovies" type="checkbox" checked> 电影</label><label><input id="includeSeries" type="checkbox" checked> 电视剧</label><label><input id="includeAnime" type="checkbox" checked> 动漫</label><label><input id="fetchDouban" type="checkbox" checked> 从豆瓣探索候选池补充</label><label><input id="enrichDetails" type="checkbox" checked> 补全简介和演职员</label><label>推荐数量</label><input id="limit" type="number" min="24" max="300" value="120"><button onclick="recommend()">生成推荐</button><button class="ghost" onclick="renderCrawlerPanel()">返回同步</button><div id="status" class="hint"></div>`; $('mainPanel').innerHTML = `<h2>你的资料库</h2><div class="metric-grid"><div class="metric"><b>${state.items.length || state.ratedItems.length || 0}</b>条目</div><div class="metric"><b>${esc((state.sections || []).length)}</b>推荐分区</div></div><p class="hint">系统会用高分条目学习偏好，用低分条目学习避雷，并自动排除已经看过的条目。想看条目会作为想看优先提示。</p>`; }
function recTitle(r) { return r.title || r.item?.title || 'CineScope'; }
function recType(r) { return r.media_type || r.item?.media_type || ''; }
function recArray(r, key) { return Array.isArray(r[key]) ? r[key] : (Array.isArray(r.item?.[key]) ? r.item[key] : []); }
function itemKey(r) { return String(r.douban_id || r.item?.douban_id || recTitle(r)); }
function posterUrl(r) { const raw = r.cover || r.item?.cover || ''; return /^https?:\/\//.test(raw) ? `/api/image-proxy?url=${encodeURIComponent(raw)}` : raw; }
function posterFallback(title, mediaType) { const safeTitle = esc(title || 'CineScope'); const safeType = esc(mediaType || '私人推荐'); const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="960" viewBox="0 0 640 960"><defs><linearGradient id="g" x1="0" x2="1" y1="0" y2="1"><stop stop-color="#1E293B"/><stop offset="0.52" stop-color="#312E81"/><stop offset="1" stop-color="#0F172A"/></linearGradient><radialGradient id="r" cx="30%" cy="10%" r="70%"><stop stop-color="#F5C451" stop-opacity=".55"/><stop offset="1" stop-color="#F5C451" stop-opacity="0"/></radialGradient></defs><rect width="640" height="960" fill="url(#g)"/><rect width="640" height="960" fill="url(#r)"/><text x="52" y="120" fill="#F5C451" font-size="28" font-family="Arial" font-weight="800" letter-spacing="5">${safeType}</text><foreignObject x="52" y="230" width="536" height="430"><div xmlns="http://www.w3.org/1999/xhtml" style="font-family:Arial,'Microsoft YaHei',sans-serif;color:#F8FAFC;font-size:74px;font-weight:950;line-height:1.06;letter-spacing:-3px;">${safeTitle}</div></foreignObject><text x="52" y="850" fill="#A7B0C0" font-size="24" font-family="Arial">CineScope Studio</text></svg>`; return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`; }
function safePosterImg(r) { const title = recTitle(r); const type = recType(r); const fallback = posterFallback(title, type); const src = posterUrl(r) || fallback; return `<img src="${esc(src)}" alt="${esc(title)}" referrerpolicy="no-referrer" onerror="this.onerror=null;this.src='${fallback}'">`; }
function posterHtml(r) { return safePosterImg(r); }
function metadataLine(r) { const parts = []; if (r.year || r.item?.year) parts.push(r.year || r.item.year); if (recType(r)) parts.push(recType(r)); recArray(r,'genres').slice(0,3).forEach(x => parts.push(x)); recArray(r,'countries').slice(0,2).forEach(x => parts.push(x)); return parts.map(esc).join(' · ') || '类型信息待补全'; }
function peopleChips(names, role) { const list = (names || []).slice(0,8); if (!list.length) return `<p class="hint">${role}资料待补全</p>`; return list.map(name => { const initials = String(name || '?').trim().slice(0,2).toUpperCase(); return `<span class="person-chip"><span class="avatar">${esc(initials)}</span><span><b>${esc(name)}</b><small class="hint"> · ${esc(role)}</small></span></span>`; }).join(''); }
function sectionItems(name) { const all = state.recommendations || []; if (name === '全部') return all; if (name === '精选') return all.slice(0,24); if (['电影','电视剧','动漫'].includes(name)) return all.filter(r => recType(r) === name); const found = (state.sections || []).find(s => s.name === name); return found?.items || []; }
function buildMediaRails() { const names = ['精选','电影','电视剧','动漫','必看 Top Picks','高分剧情','想看优先']; const rails = []; const seen = new Set(); for (const name of names) { const items = sectionItems(name); if (items.length && !seen.has(name)) { rails.push({ name, items }); seen.add(name); } } for (const section of state.sections || []) { if (!seen.has(section.name) && section.items?.length) rails.push({ name:section.name, items:section.items }); } return rails; }
function mediaCard(r, index) { const key = encodeURIComponent(itemKey(r)); return `<article class="poster-card" onclick="openDetailByKey('${key}')"><div class="poster">${safePosterImg(r)}</div><div class="poster-body"><span class="badge">${esc(recType(r) || '媒体')}</span><span class="badge">豆瓣 ${esc(r.douban_rating || r.item?.douban_rating || '-')}</span><h3>${esc(recTitle(r))}</h3><div class="meta-line">${metadataLine(r)}</div><p class="micro-copy">${esc(r.summary || r.item?.summary || r.short_reason || (r.reasons || [])[0] || '质量优先策略推荐')}</p><details><summary>展开详情</summary>点击卡片打开完整抽屉。</details></div></article>`; }
function renderMediaRail(name, items) { return `<section class="media-rail"><div class="rail-head"><div class="rail-title">${esc(name)}</div><button class="ghost" onclick="state.activeSection='${esc(name)}';renderRecommendations()">查看全部</button></div><div class="rail-strip">${items.map(mediaCard).join('')}</div></section>`; }
function renderHeroShowcase() { const rows = state.recommendations || []; if (!rows.length) return ''; const r = rows[state.heroIndex % rows.length]; const directors = recArray(r,'directors').slice(0,2).join('、'); const casts = recArray(r,'casts').slice(0,4).join('、'); return `<section class="hero-showcase" id="heroShowcase"><div class="hero-poster">${safePosterImg(r)}</div><div class="hero-meta"><span class="badge">今日最值得看</span><h2>${esc(recTitle(r))}</h2><div class="meta-line">${metadataLine(r)} · 豆瓣 ${esc(r.douban_rating || '-')}</div><p class="hero-copy">${esc(r.summary || r.short_reason || (r.reasons || [])[0] || '根据你的高分偏好与避雷设置精选。')}</p><p class="hint">${directors ? '导演：' + esc(directors) : ''}${casts ? ' · 主演：' + esc(casts) : ''}</p><div><button onclick="openDetailByKey('${encodeURIComponent(itemKey(r))}')">打开详情</button><button class="ghost" onclick="state.heroIndex=(state.heroIndex+1)%Math.max(1,state.recommendations.length);renderRecommendations()">换一部</button></div></div></section>`; }
function renderRecommendations() { state.step = 3; renderStepNav(); const sectionNames = ['全部','精选','电影','电视剧','动漫', ...(state.sections || []).map(s => s.name)].filter((x,i,a)=>x && a.indexOf(x)===i); const tabs = sectionNames.map(name => `<button class="tab ${state.activeSection === name ? 'active' : ''}" onclick="state.activeSection='${esc(name)}';renderRecommendations()">${esc(name)}</button>`).join(''); const items = sectionItems(state.activeSection); state.visibleRecommendations = items; const focusedGrid = items.length ? `<section class="media-rail"><div class="rail-head"><div class="rail-title">${esc(state.activeSection)} · 当前筛选</div><span class="hint">${items.length} 部</span></div><div class="poster-grid">${items.map(mediaCard).join('')}</div></section>` : '<div class="empty-state">这个分类暂时没有结果。</div>'; const rails = buildMediaRails().map(rail => renderMediaRail(rail.name, rail.items.slice(0,18))).join(''); $('controlPanel').innerHTML = `<h2>第三步：查看推荐</h2><p class="hint">顶部是今日焦点，下面按电影、电视剧、动漫和策展主题组成横向胶片带。</p><button class="ghost" onclick="renderTastePanel()">调整口味</button><button class="ghost" onclick="renderCrawlerPanel()">重新同步</button>`; $('mainPanel').innerHTML = `<h2>私人推荐片单</h2><div class="tabs">${tabs}</div>${renderHeroShowcase()}<div class="rail-wall" id="railWall">${focusedGrid}${rails || '<div class="empty-state">还没有推荐。先同步豆瓣或直接生成 quality-first 推荐。</div>'}</div>`; }
function openDetail(index) { const r = state.visibleRecommendations[index]; if (!r) return; openDetailObject(r); }
function openDetailByKey(encodedKey) { const key = decodeURIComponent(encodedKey || ''); const all = [...(state.recommendations || []), ...(state.visibleRecommendations || [])]; const r = all.find(x => itemKey(x) === key); if (r) openDetailObject(r); }
function openDetailObject(r) { $('detailDrawer').classList.add('open'); $('detailDrawer').innerHTML = `<button class="ghost" onclick="$('detailDrawer').classList.remove('open')">关闭</button><div class="drawer-poster">${safePosterImg(r)}</div><h2>${esc(recTitle(r))}</h2><p class="meta-line">${metadataLine(r)} · 豆瓣 ${esc(r.douban_rating || r.item?.douban_rating || '-')}</p><h3>剧情简介</h3><p class="hint">${esc(r.summary || r.item?.summary || '暂无官方简介，可先根据推荐理由判断是否加入片单。')}</p><div class="people-grid"><div><h3>导演</h3>${peopleChips(recArray(r,'directors'), '导演')}</div><div><h3>主演</h3>${peopleChips(recArray(r,'casts'), '主演')}</div></div><h3>推荐理由</h3><ul>${(r.reasons || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul><h3>风险提示</h3><ul>${(r.warnings || []).map(x => `<li class="warn">${esc(x)}</li>`).join('') || '<li class="hint">没有明显避雷信号。</li>'}</ul><p><a href="${esc(r.url || '#')}" target="_blank" rel="noreferrer">打开豆瓣</a></p>`; }
async function syncDouban() { setStatus('正在同步豆瓣。'); const cookieBox = $('doubanCookie'); const payload = { user_id_or_url:$('doubanUser').value, cookie:cookieBox.value, max_pages:Number($('maxPages').value || 40), include_wish:$('includeWish').checked, expected_collect:Number($('expectedCollect').value || 0), expected_wish:Number($('expectedWish').value || 0) }; cookieBox.value = ''; const res = await fetch('/api/sync-douban', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) }); const data = await res.json(); if (!res.ok || data.error) { setStatus('同步失败：' + (data.error || '请求失败')); return; } state.items = data.items || []; state.ratedItems = state.items; state.counts = data.counts || {}; state.diagnostics = data.diagnostics || []; state.errors = data.errors || []; renderCrawlSummary(); }
function useCsvInputs() { state.items = []; state.ratedItems = []; state.ratingsCsv = $('ratingsCsv').value; state.candidatesCsv = $('candidatesCsv').value; renderTastePanel(); }
async function clearCache() { await fetch('/api/cache', { method:'DELETE' }); $('mainPanel').innerHTML = '<div class="empty-state">本地缓存已清空。</div>'; }
async function recommend() { setStatus('正在生成推荐。'); const payload = { rated_items:state.items, ratings_csv: state.items.length ? '' : state.ratingsCsv, candidates_csv: state.candidatesCsv, like_terms:$('likeTerms').value, dislike_terms:$('dislikeTerms').value, include_movies:$('includeMovies').checked, include_series:$('includeSeries').checked, include_anime:$('includeAnime').checked, fetch_douban:$('fetchDouban').checked, enrich_details:$('enrichDetails') ? $('enrichDetails').checked : true, use_sample_candidates:!state.candidatesCsv, limit:Number($('limit').value || 120) }; const res = await fetch('/api/recommend', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) }); const data = await res.json(); if (!res.ok || data.error) { setStatus('推荐失败：' + (data.error || '请求失败')); return; } state.recommendations = data.results || []; state.sections = data.sections || []; state.profile = data.profile || null; renderRecommendations(); }
function crawlDouban() { return syncDouban(); }
function goStep(step) { if (step === 1) renderCrawlerPanel(); if (step === 2) renderTastePanel(); if (step === 3) renderRecommendations(); }
renderStepNav(); renderCrawlerPanel();
</script>
</body>
</html>"""
