from __future__ import annotations

import json

from .curated_catalog import (
    PEOPLE_PHOTOS_BY_DOUBAN_ID,
    POSTER_URLS_BY_DOUBAN_ID,
    TITLE_PEOPLE_METADATA,
    curated_seed_candidates,
)
from .douban_sources import STATIC_POSTER_URLS_BY_TITLE

INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CineScope Studio：豆瓣私人影视策展器</title>
  <style>
    :root { --bg:#070A12; --panel:rgba(16,22,36,.80); --panel2:rgba(255,255,255,.08); --text:#F8FAFC; --muted:#A7B0C0; --line:rgba(255,255,255,.13); --gold:#F5C451; --green:#4ADE80; --red:#FB7185; --blue:#60A5FA; --violet:#A78BFA; --cyan:#22D3EE; --surface-ink:rgba(5,8,18,.92); --surface-glass:rgba(12,18,32,.70); --surface-glow:rgba(245,196,81,.18); --ease-premium:cubic-bezier(.2,.8,.2,1); }
    * { box-sizing:border-box; }
    html, body { max-width:100%; overflow-x:hidden; }
    p, li, summary, label, h1, h2, h3, h4, a, span { min-width:0; max-width:100%; overflow-wrap:anywhere; word-break:break-word; }
    .anti-overflow, .anti-overflow *, .workspace, .glass-panel, .sync-command-center, .sync-command-center *, .timeline-row, .diagnosis-card, .metric, .story-panel, .blocked-brief, .recovery-action, .playbook-card, .drawer, .drawer *, .poster-body, .poster-body *, .hero-meta, .hero-slide, .rail-title, .tab, .badge, .mini-list, .empty-state, .resilience-card, button, input, textarea, code { min-width:0; max-width:100%; overflow-wrap:anywhere; word-break:break-word; }
    .row > *, .metric-grid > *, .sync-health > *, .recovery-actions > *, .sync-playbook > *, .hero-showcase > *, .hero-track > *, .rail-head > *, .poster-card, .poster-body, .drawer, .drawer * { min-width:0; max-width:100%; }
    body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif; color:var(--text); background:radial-gradient(circle at 12% 0%,#27345C 0,transparent 32%),radial-gradient(circle at 86% 10%,#4C1D95 0,transparent 30%),var(--bg); background-attachment:fixed; }
    .app-shell { max-width:1440px; margin:0 auto; padding:28px; transition:max-width .25s ease, padding .25s ease; }
    .results-shell { max-width:min(1880px,calc(100vw - 20px)); padding:20px; }
    .results-shell.rail-hidden-shell { max-width:min(2040px,calc(100vw - 12px)); padding:14px; }
    .results-shell.rail-hidden-shell .cinema-wall { grid-template-columns:repeat(auto-fill,minmax(min(100%,210px),1fr)); gap:16px; }
    .results-shell .cinematic-hero { min-height:188px; padding:24px 28px; }
    .results-shell h1 { font-size:clamp(38px,5vw,72px); }
    .results-shell .step-rail { margin:14px 0; }
    .cinematic-hero { min-height:260px; border:1px solid var(--line); border-radius:34px; padding:34px; background:linear-gradient(135deg,rgba(245,196,81,.20),rgba(96,165,250,.12)),rgba(255,255,255,.06); box-shadow:0 30px 100px rgba(0,0,0,.35); position:relative; overflow:hidden; }
    .hero-kicker { color:var(--gold); font-weight:900; letter-spacing:.18em; text-transform:uppercase; }
    h1 { font-size:clamp(42px,7vw,92px); line-height:.92; margin:14px 0; letter-spacing:-.06em; }
    h2 { margin:0 0 12px; }
    .hero-copy,.hint { color:var(--muted); line-height:1.8; }
    .privacy-pill { display:inline-flex; margin-top:14px; padding:9px 13px; border:1px solid rgba(74,222,128,.35); border-radius:999px; color:var(--green); background:rgba(74,222,128,.10); font-weight:900; }
    .step-rail { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin:22px 0; }
    .step-card { border:1px solid var(--line); border-radius:22px; padding:16px; background:rgba(255,255,255,.07); color:var(--muted); }
    .step-card b { display:block; color:var(--text); margin-bottom:4px; }
    .workspace { display:grid; grid-template-columns:minmax(320px,390px) minmax(0,1fr); gap:22px; align-items:start; }
    .workspace.recommendation-stage { grid-template-columns:minmax(280px,330px) minmax(0,1fr); gap:18px; }
    .workspace.recommendation-stage #controlPanel { grid-column:1; }
    .workspace.recommendation-stage #mainPanel { grid-column:2; }
    .workspace.recommendation-stage.results-rail-hidden { grid-template-columns:minmax(0,1fr); gap:0; }
    .workspace.recommendation-stage.results-rail-hidden #controlPanel { display:none; }
    .workspace.recommendation-stage.results-rail-hidden #mainPanel { grid-column:1 / -1; }
    .drawer-safe-stage { transition:margin-right .25s var(--ease-premium), filter .25s var(--ease-premium); }
    .detail-open .workspace.recommendation-stage #mainPanel { margin-right:min(560px,34vw); }
    .detail-open .workspace.recommendation-stage.results-rail-hidden #mainPanel { margin-right:min(540px,32vw); }
    .detail-open .banner-content { grid-template-columns:minmax(0,1fr); }
    .detail-open .banner-poster-float { width:0; min-width:0; opacity:0; pointer-events:none; transform:perspective(1200px) rotateY(-14deg) translateX(34px) scale(.92); }
    .glass-panel { border:1px solid var(--line); border-radius:28px; padding:22px; background:var(--panel); backdrop-filter:blur(18px); box-shadow:0 24px 70px rgba(0,0,0,.28); }
    .homepage-studio { position:relative; }
    .homepage-studio:before { content:""; position:fixed; inset:0; pointer-events:none; background:linear-gradient(90deg,rgba(255,255,255,.03) 1px,transparent 1px),linear-gradient(rgba(255,255,255,.03) 1px,transparent 1px); background-size:72px 72px; mask-image:radial-gradient(circle at 50% 0%,#000 0,transparent 65%); }
    .ambient-orb { position:fixed; width:42vw; height:42vw; border-radius:50%; filter:blur(72px); opacity:.20; pointer-events:none; z-index:-1; background:radial-gradient(circle,#F5C451,transparent 62%); animation:ambientDrift 18s var(--ease-premium) infinite alternate; }
    .ambient-orb.orb-a { left:-14vw; top:18vh; }
    .ambient-orb.orb-b { right:-16vw; top:8vh; background:radial-gradient(circle,#22D3EE,transparent 62%); animation-delay:-7s; }
    .figma-grade-stage { position:relative; }
    .figma-grade-stage:before { content:""; position:fixed; inset:0; pointer-events:none; z-index:-2; background:linear-gradient(90deg,rgba(255,255,255,.035) 1px,transparent 1px),linear-gradient(rgba(255,255,255,.028) 1px,transparent 1px); background-size:96px 96px; mask-image:radial-gradient(circle at 50% 20%,#000 0,transparent 70%); }
    .figma-grade-stage:after { content:""; position:fixed; inset:0; pointer-events:none; z-index:40; opacity:.035; mix-blend-mode:screen; background-image:radial-gradient(circle at 1px 1px,white 1px,transparent 0); background-size:4px 4px; }
    @keyframes ambientDrift { from { transform:translate3d(0,0,0) scale(1); } to { transform:translate3d(6vw,-4vh,0) scale(1.12); } }
    .cinema-nav { display:flex; gap:10px; flex-wrap:wrap; margin-top:20px; }
    .cinema-nav span { padding:9px 12px; border:1px solid var(--line); border-radius:999px; background:rgba(255,255,255,.07); color:var(--muted); font-weight:800; }
    .quick-actions { display:flex; gap:10px; flex-wrap:wrap; margin-top:16px; }
    .quick-actions button { flex:1 1 180px; }
    .story-panel { border:1px solid var(--line); border-radius:24px; padding:18px; background:linear-gradient(135deg,rgba(255,255,255,.09),rgba(255,255,255,.035)); margin:14px 0; }

    .control-hero { display:grid; gap:10px; padding:18px; border:1px solid rgba(245,196,81,.22); border-radius:24px; background:radial-gradient(circle at 10% 0%,rgba(245,196,81,.20),transparent 46%),rgba(255,255,255,.06); }
    .control-hero b { font-size:22px; letter-spacing:-.03em; }
    .sync-command-center { display:grid; gap:18px; }
    .sync-health { display:grid; grid-template-columns:minmax(180px,.8fr) 1.2fr; gap:18px; align-items:stretch; padding:20px; border:1px solid rgba(96,165,250,.22); border-radius:28px; background:linear-gradient(135deg,rgba(15,23,42,.88),rgba(30,41,59,.72)); box-shadow:0 24px 70px rgba(0,0,0,.30); }
    .health-orb { min-height:180px; border-radius:24px; display:grid; place-items:center; text-align:center; background:radial-gradient(circle at 35% 25%,rgba(245,196,81,.45),transparent 28%),radial-gradient(circle at 70% 70%,rgba(96,165,250,.35),transparent 34%),linear-gradient(135deg,#111827,#312E81); }
    .health-orb b { display:block; font-size:58px; line-height:1; color:var(--gold); }
    .blocked-brief { border:1px solid rgba(251,113,133,.34); border-radius:24px; padding:18px; background:linear-gradient(135deg,rgba(251,113,133,.16),rgba(245,196,81,.08)); }
    .blocked-brief h3 { margin:4px 0 8px; font-size:26px; }
    .sync-success-brief { border:1px solid rgba(74,222,128,.34); border-radius:24px; padding:18px; background:linear-gradient(135deg,rgba(74,222,128,.16),rgba(34,211,238,.08)); box-shadow:0 18px 50px rgba(0,0,0,.22); }
    .sync-success-brief h3 { margin:4px 0 8px; font-size:26px; }
    .recovery-actions { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,210px),1fr)); gap:10px; margin-top:12px; }
    .recovery-action { padding:12px; border:1px solid var(--line); border-radius:16px; background:rgba(255,255,255,.07); color:var(--text); line-height:1.55; }
    .diagnosis-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr)); gap:12px; }
    .diagnosis-card { padding:14px; border:1px solid var(--line); border-radius:18px; background:rgba(255,255,255,.06); }
    .diagnosis-card b { display:block; color:var(--gold); margin-bottom:6px; }
    .sync-copy { max-width:780px; color:var(--muted); line-height:1.8; }
    .sync-playbook { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,190px),1fr)); gap:12px; margin-top:14px; }
    .playbook-card { border:1px solid rgba(245,196,81,.20); border-radius:20px; padding:14px; background:linear-gradient(145deg,rgba(245,196,81,.10),rgba(96,165,250,.06)); }
    .playbook-card b { display:block; color:var(--text); margin-bottom:6px; }
    .user-input-card { border:1px solid rgba(96,165,250,.22); border-radius:22px; padding:16px; background:linear-gradient(145deg,rgba(96,165,250,.10),rgba(245,196,81,.06)); color:var(--muted); line-height:1.75; }
    .user-input-card b { display:block; color:var(--text); margin-bottom:6px; }
    .inputInsight { margin:10px 0 4px; }
    .cookie-import-assistant { display:grid; gap:10px; margin:12px 0; padding:14px; border:1px solid rgba(245,196,81,.24); border-radius:20px; background:linear-gradient(135deg,rgba(245,196,81,.10),rgba(34,211,238,.06)); }
    .cookie-import-assistant b { color:var(--text); }
    .recovery-action b { display:block; color:var(--gold); margin-bottom:6px; }
    .progress-meter { height:8px; border-radius:999px; overflow:hidden; background:rgba(255,255,255,.10); margin-top:9px; }
    .progress-meter span { display:block; height:100%; border-radius:999px; background:linear-gradient(90deg,var(--gold),var(--cyan)); }
    .taste-dna { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:16px 0; }
    .tasteDNA { display:grid; gap:8px; }
    .dna-chip { padding:12px; border-radius:18px; border:1px solid rgba(245,196,81,.20); background:rgba(245,196,81,.08); }
    .image-resilience { max-width:100%; border-color:rgba(34,211,238,.28); background:rgba(34,211,238,.07); overflow-wrap:anywhere; word-break:break-word; }
    .image-resilience * { max-width:100%; overflow-wrap:anywhere; word-break:break-word; }
    .resilience-card { display:grid; gap:10px; max-width:100%; overflow:hidden; border:1px solid rgba(34,211,238,.18); border-radius:18px; padding:14px; margin-top:12px; background:rgba(2,6,23,.38); }
    .resilience-card .hint { white-space:pre-wrap; }
    .resilience-toolbar { display:flex; align-items:center; justify-content:space-between; gap:8px; flex-wrap:wrap; }
    .proxy-command { min-width:0; max-width:100%; overflow:hidden; border-radius:14px; border:1px solid rgba(34,211,238,.20); background:rgba(15,23,42,.82); }
    .resilience-card code { display:block; width:100%; max-width:100%; padding:10px 12px; color:#CFFAFE; overflow-x:auto; overflow-y:hidden; overflow-wrap:normal; word-break:normal; white-space:pre; font-size:12px; line-height:1.6; }
    .source-settings { display:grid; gap:12px; margin:14px 0; padding:14px; border:1px solid rgba(167,139,250,.28); border-radius:22px; background:linear-gradient(145deg,rgba(167,139,250,.12),rgba(34,211,238,.06)); }
    .source-settings h3 { margin:0; }
    .setting-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,190px),1fr)); gap:10px; }
    .toggle-row { display:flex; gap:8px; align-items:flex-start; padding:10px; border:1px solid var(--line); border-radius:16px; background:rgba(255,255,255,.055); color:var(--muted); line-height:1.45; }
    .api-link-row { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
    .api-link { display:inline-flex; align-items:center; padding:8px 11px; border:1px solid rgba(34,211,238,.28); border-radius:999px; color:#CFFAFE; background:rgba(34,211,238,.08); text-decoration:none; font-weight:900; }
    .poster-job-dock { margin:0 0 16px; padding:16px; border:1px solid rgba(34,211,238,.28); border-radius:24px; background:radial-gradient(circle at 0% 0%,rgba(34,211,238,.16),transparent 42%),rgba(15,23,42,.82); box-shadow:0 18px 55px rgba(0,0,0,.25); }
    .job-feed { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,180px),1fr)); gap:8px; margin-top:10px; }
    .job-event { padding:10px; border:1px solid var(--line); border-radius:16px; background:rgba(255,255,255,.06); font-size:12px; color:var(--muted); }
    .job-event b { display:block; color:var(--text); margin-bottom:3px; }
    .poster-recovery-center { display:grid; gap:10px; margin:14px 0; padding:14px; border:1px solid rgba(251,113,133,.24); border-radius:22px; background:linear-gradient(145deg,rgba(251,113,133,.10),rgba(34,211,238,.06)); }
    .missing-poster-list { display:grid; gap:8px; max-height:260px; overflow:auto; padding-right:4px; }
    .missing-poster-row { padding:10px; border:1px solid var(--line); border-radius:16px; background:rgba(255,255,255,.06); }
    .missing-poster-row b { display:block; color:var(--text); margin-bottom:4px; }
    .source-link-strip { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
    .source-link-strip a { color:#CFFAFE; text-decoration:none; border:1px solid rgba(34,211,238,.22); border-radius:999px; padding:5px 8px; background:rgba(34,211,238,.08); font-size:12px; font-weight:900; }
    .source-stat-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,120px),1fr)); gap:8px; margin-top:10px; }
    .source-stat { padding:10px; border:1px solid rgba(245,196,81,.20); border-radius:14px; background:rgba(245,196,81,.08); }
    .poster-source-theater { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,150px),1fr)); gap:8px; margin-top:12px; }
    .source-lane { position:relative; overflow:hidden; min-height:74px; padding:10px 11px; border:1px solid rgba(255,255,255,.13); border-radius:16px; background:rgba(255,255,255,.055); color:var(--muted); }
    .source-lane b { display:block; color:var(--text); margin-bottom:4px; }
    .source-lane.active { border-color:rgba(245,196,81,.65); background:linear-gradient(135deg,rgba(245,196,81,.20),rgba(34,211,238,.08)); color:var(--text); animation:sourceLanePulse 1.45s ease-in-out infinite; }
    .source-lane.found { border-color:rgba(74,222,128,.42); background:rgba(74,222,128,.10); }
    .source-lane.miss { border-color:rgba(251,113,133,.28); background:rgba(251,113,133,.08); }
    @keyframes sourceLanePulse { 0%,100% { box-shadow:0 0 0 rgba(245,196,81,0); transform:translateY(0); } 50% { box-shadow:0 0 28px rgba(245,196,81,.20); transform:translateY(-1px); } }
    .poster-load-failed { filter:saturate(.85) contrast(1.05); }
    .copy-mini { padding:8px 10px; border-radius:999px; font-size:12px; flex:0 0 auto; }
    label { display:block; color:var(--text); font-weight:800; margin:14px 0 7px; }
    input, textarea, select { width:100%; border:1px solid var(--line); border-radius:16px; padding:13px 14px; color:var(--text); background:rgba(255,255,255,.08); font:inherit; }
    input[type="checkbox"] { width:18px; height:18px; padding:0; margin:0 8px 0 0; accent-color:var(--gold); vertical-align:middle; }
    textarea { min-height:96px; resize:vertical; }
    .url-textarea { min-height:54px; resize:vertical; }
    .row { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    button { border:0; border-radius:16px; padding:12px 16px; font-weight:900; color:#101828; background:var(--gold); cursor:pointer; margin:4px 4px 4px 0; white-space:normal; }
    button.ghost { color:var(--text); background:rgba(255,255,255,.10); border:1px solid var(--line); }
    .rail-toggle-fab { position:fixed; z-index:32; right:22px; bottom:22px; left:auto; top:auto; width:52px; height:52px; padding:0; border-radius:50%; display:none; align-items:center; justify-content:center; gap:0; font-size:0; border:1px solid rgba(245,196,81,.35); color:var(--text); background:rgba(11,16,32,.84); backdrop-filter:blur(18px); box-shadow:0 18px 48px rgba(0,0,0,.35); }
    .rail-toggle-fab:before { content:"☰"; font-size:20px; line-height:1; }
    .rail-toggle-fab.visible { display:inline-flex; }
    .rail-toolbar { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:12px; }
    .rail-toolbar button { flex:0 0 auto; }
    .results-topbar { position:sticky; top:10px; z-index:12; display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; margin:-4px 0 14px; padding:12px 14px; border:1px solid rgba(245,196,81,.22); border-radius:22px; background:rgba(11,16,32,.76); backdrop-filter:blur(18px); box-shadow:0 18px 46px rgba(0,0,0,.28); }
    .stage-command-bar { border-radius:28px; padding:14px 16px; background:linear-gradient(135deg,rgba(15,23,42,.84),rgba(30,41,59,.58)); box-shadow:0 24px 80px rgba(0,0,0,.34), inset 0 1px 0 rgba(255,255,255,.10); }
    .signal-stack { display:grid; gap:5px; min-width:min(760px,100%); }
    .signal-stack .hint { display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
    .results-topbar b { font-size:18px; letter-spacing:-.02em; }
    .results-topbar .hint { line-height:1.45; }
    details { border:1px solid var(--line); border-radius:18px; padding:12px; background:rgba(255,255,255,.06); margin-top:12px; }
    summary { cursor:pointer; font-weight:900; }
    .metric-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }
    .metric { padding:16px; border-radius:20px; background:var(--panel2); border:1px solid var(--line); }
    .metric b { display:block; font-size:30px; color:var(--gold); }
    .recommend-metrics { grid-template-columns:repeat(2,minmax(0,1fr)); }
    .recommend-metrics .metric { padding:14px; }
    .metric-value { display:block; font-size:clamp(30px,8vw,42px); line-height:1; color:var(--gold); font-weight:950; font-variant-numeric:tabular-nums; white-space:nowrap; word-break:keep-all; overflow-wrap:normal; letter-spacing:-.04em; }
    .metric-label { display:block; margin-top:8px; color:var(--text); font-weight:900; line-height:1.15; word-break:keep-all; }
    .results-control-rail { position:fixed; top:20px; left:max(20px,calc((100vw - min(1880px,calc(100vw - 20px))) / 2 + 20px)); width:min(330px,calc(100vw - 40px)); height:calc(100vh - 40px); min-height:0; max-height:none; overflow:visible; padding:0; scrollbar-width:thin; }
    .results-control-inner { height:100%; overflow:auto; padding:22px; display:flex; flex-direction:column; scrollbar-width:thin; }
    .results-control-inner .image-resilience { margin-top:auto; }
    .result-compass { display:grid; gap:12px; margin:16px 0; padding:14px; border:1px solid rgba(245,196,81,.22); border-radius:22px; background:radial-gradient(circle at 0% 0%,rgba(245,196,81,.18),transparent 42%),rgba(255,255,255,.055); }
    .compass-head { display:flex; align-items:center; justify-content:space-between; gap:10px; }
    .compass-head b { font-size:18px; letter-spacing:-.03em; }
    .section-mini-map { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
    .section-mini { min-height:54px; display:grid; grid-template-columns:1fr auto; align-items:center; gap:8px; text-align:left; color:var(--text); background:rgba(255,255,255,.08); border:1px solid var(--line); padding:10px; border-radius:16px; }
    .section-mini.active { background:linear-gradient(135deg,var(--gold),#FDE68A); color:#101828; border-color:rgba(245,196,81,.8); }
    .section-mini b { font-variant-numeric:tabular-nums; white-space:nowrap; }
    .result-progress { height:8px; border-radius:999px; overflow:hidden; background:rgba(255,255,255,.10); }
    .result-progress span { display:block; height:100%; border-radius:999px; background:linear-gradient(90deg,var(--gold),var(--cyan)); transition:width .25s ease; }
    .timeline { display:grid; gap:10px; margin-top:14px; }
    .timeline-row { padding:12px; border-radius:16px; background:rgba(255,255,255,.06); border:1px solid var(--line); }
    .tabs { display:flex; gap:10px; flex-wrap:wrap; margin:18px 0; }
    .tab { color:var(--text); background:rgba(255,255,255,.08); }
    .tab.active { background:var(--gold); color:#101828; }
    .hero-showcase { margin:8px 0 22px; }
    .category-spotlight { isolation:isolate; }
    .category-spotlight:after { content:""; position:absolute; inset:auto -15% -35% 30%; height:260px; background:radial-gradient(circle,rgba(167,139,250,.24),transparent 65%); z-index:-1; }
    .cinematic-banner { position:relative; height:clamp(460px,50vw,620px); min-height:0; border:1px solid rgba(245,196,81,.28); border-radius:36px; overflow:hidden; background:#060914; box-shadow:0 38px 120px rgba(0,0,0,.50); display:grid; grid-template-rows:1fr auto auto; align-items:end; }
    .cinematic-banner:before { content:""; position:absolute; inset:0; background:linear-gradient(90deg,rgba(6,9,20,.94) 0%,rgba(6,9,20,.78) 38%,rgba(6,9,20,.28) 72%,rgba(6,9,20,.88) 100%),radial-gradient(circle at 18% 12%,rgba(245,196,81,.24),transparent 34%),radial-gradient(circle at 78% 18%,rgba(96,165,250,.22),transparent 40%); z-index:1; pointer-events:none; }
    .banner-backdrop { position:absolute; inset:0; opacity:.42; filter:blur(18px) saturate(1.35) contrast(1.06); transform:scale(1.08); }
    .banner-backdrop img { width:100%; height:100%; object-fit:cover; }
    .spotlight-lens { position:absolute; inset:0; z-index:1; pointer-events:none; background:radial-gradient(circle at 72% 30%,rgba(255,255,255,.16),transparent 18%),linear-gradient(115deg,transparent 0 45%,rgba(255,255,255,.07) 52%,transparent 62%); mix-blend-mode:screen; animation:lensSweep 9s var(--ease-premium) infinite; }
    .banner-content { position:relative; z-index:2; display:grid; grid-template-columns:minmax(0,1fr) minmax(180px,250px); gap:clamp(18px,4vw,44px); align-items:end; padding:clamp(20px,4vw,44px) clamp(24px,5vw,58px) 16px; min-height:0; }
    .banner-copy { display:grid; gap:10px; max-width:900px; min-height:0; }
    .banner-copy p { margin:0; }
    .banner-copy h2 { font-size:clamp(42px,6vw,76px); line-height:.90; letter-spacing:-.065em; margin:0; text-shadow:0 20px 60px rgba(0,0,0,.55); }
    .banner-copy .hero-copy { max-width:760px; font-size:clamp(15px,1.5vw,19px); color:#D9E4F2; }
    .banner-credits { color:#C7D2FE; line-height:1.8; }
    .banner-poster-float { justify-self:end; align-self:center; width:min(220px,22vw); aspect-ratio:2/3; border-radius:28px; overflow:hidden; background:linear-gradient(145deg,rgba(255,255,255,.10),rgba(255,255,255,.02)); box-shadow:0 34px 90px rgba(0,0,0,.62); transform:perspective(1200px) rotateY(-8deg) translateY(38px); animation:bannerFloat 6s ease-in-out infinite; padding:8px; }
    .banner-poster-float img { width:100%; height:100%; object-fit:contain; display:block; border-radius:20px; background:#050814; }
    .banner-filmstrip { position:relative; z-index:3; display:grid; grid-auto-flow:column; grid-auto-columns:minmax(120px,168px); gap:12px; overflow-x:auto; padding:0 clamp(24px,5vw,58px) 12px; scroll-snap-type:x proximity; scrollbar-width:none; }
    .banner-filmstrip::-webkit-scrollbar { display:none; }
    .banner-filmstrip .hero-dot { width:auto; height:82px; border-radius:18px; padding:0; margin:0; display:grid; grid-template-columns:52px 1fr; align-items:center; gap:10px; overflow:hidden; color:var(--muted); background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.14); text-align:left; scroll-snap-align:start; transition:transform .18s ease, border-color .18s ease, background .18s ease; }
    .banner-filmstrip .hero-dot.active { background:linear-gradient(135deg,rgba(245,196,81,.24),rgba(96,165,250,.10)); border-color:rgba(245,196,81,.70); color:var(--text); transform:translateY(-3px); }
    .hero-thumb { overflow:hidden; }
    .hero-thumb img { width:52px; height:82px; object-fit:cover; display:block; }
    .hero-dot-title { display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; font-size:13px; line-height:1.25; font-weight:900; }
    .hero-progress { height:5px; overflow:hidden; border-radius:999px; background:rgba(255,255,255,.10); }
    .hero-progress span { display:block; height:100%; border-radius:999px; background:linear-gradient(90deg,var(--gold),var(--cyan)); transition:width .25s ease; }
    .banner-controls { position:relative; z-index:3; display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; padding:0 clamp(24px,5vw,58px) clamp(18px,3vw,30px); }
    .banner-controls .hero-progress { flex:1 1 220px; min-width:160px; }
    .banner-controls .quick-actions { margin:0; }
    @keyframes bannerFloat { 0%,100% { transform:perspective(1200px) rotateY(-8deg) translateY(38px); } 50% { transform:perspective(1200px) rotateY(-2deg) translateY(24px); } }
    @keyframes lensSweep { 0%,100% { opacity:.42; transform:translateX(-2%); } 50% { opacity:.76; transform:translateX(2%); } }
    .meta-line { color:var(--muted); line-height:1.7; }
    .rail-wall { display:grid; gap:30px; }
    .compact-rail-wall { margin-top:14px; }
    .rail-collapse { border-style:dashed; border-color:rgba(96,165,250,.24); background:rgba(96,165,250,.06); }
    .rail-collapse summary { display:flex; justify-content:space-between; align-items:center; gap:10px; }
    .rail-collapse summary:after { content:"分类速览"; color:var(--cyan); font-size:12px; letter-spacing:.08em; text-transform:uppercase; }
    .media-rail { display:grid; gap:14px; }
    .rail-head { display:flex; align-items:end; justify-content:space-between; gap:14px; }
    .rail-title { font-size:24px; font-weight:950; letter-spacing:-.03em; }
    .rail-strip { display:grid; grid-auto-flow:column; grid-auto-columns:minmax(190px,220px); gap:18px; overflow-x:auto; padding:4px 4px 18px; scroll-snap-type:x proximity; }
    .rail-strip::-webkit-scrollbar { height:10px; }
    .rail-strip::-webkit-scrollbar-thumb { background:rgba(245,196,81,.32); border-radius:999px; }
    .poster-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(min(100%,170px),1fr)); gap:18px; }
    .dense-poster-grid { grid-template-columns:repeat(auto-fill,minmax(min(100%,220px),1fr)); gap:14px; }
    .cinema-wall { grid-template-columns:repeat(auto-fill,minmax(min(100%,176px),1fr)); gap:12px; align-items:start; }
    .poster-card { min-height:372px; border:1px solid var(--line); border-radius:24px; overflow:hidden; background:#111827; position:relative; box-shadow:0 20px 50px rgba(0,0,0,.28); transition:.18s ease; }
    .poster-lift { transform:translateZ(0); transition:transform .22s var(--ease-premium), border-color .22s var(--ease-premium), box-shadow .22s var(--ease-premium), filter .22s var(--ease-premium); }
    .poster-lift:hover, .poster-lift:focus-within { transform:translateY(-8px) scale(1.015); box-shadow:0 34px 88px rgba(0,0,0,.42), 0 0 0 1px rgba(245,196,81,.18); filter:saturate(1.06); }
    .compact-poster-card { min-height:0; display:grid; grid-template-rows:auto 1fr; }
    .poster-card:hover { transform:translateY(-4px); border-color:rgba(245,196,81,.45); }
    .poster { height:242px; background:linear-gradient(145deg,#1f2937,#334155); display:flex; align-items:center; justify-content:center; text-align:center; padding:0; font-weight:900; }
    .compact-poster-card .poster { height:176px; }
    .poster img { width:100%; height:100%; object-fit:cover; display:block; }
    .poster-body { padding:14px; }
    .compact-poster-card .poster-body { padding:12px; }
    .poster-body h3 { margin:10px 0 8px; line-height:1.24; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
    .badge { display:inline-flex; border:1px solid var(--line); border-radius:999px; padding:4px 8px; color:var(--muted); font-size:12px; margin:2px; }
    .poster-source-layer { position:absolute; top:9px; left:9px; right:9px; z-index:3; display:flex; justify-content:flex-start; pointer-events:none; }
    .poster-source-layer .badge { backdrop-filter:blur(12px); background:rgba(11,16,32,.72); border-color:rgba(255,255,255,.22); color:#F8FAFC; box-shadow:0 10px 28px rgba(0,0,0,.24); }
    .poster-source-layer .designed-cover { border-color:rgba(245,196,81,.40); background:rgba(245,196,81,.18); color:#FDE68A; }
    .poster-card.designed-cover { border-color:rgba(245,196,81,.22); }
    .poster-card.designed-cover .poster img { filter:saturate(.92) contrast(1.02); }
    .poster-card.real-poster .poster-source-layer { opacity:0; transition:opacity .18s ease; }
    .poster-card.real-poster:hover .poster-source-layer, .poster-card.real-poster:focus-within .poster-source-layer { opacity:1; }
    .micro-copy { color:var(--muted); font-size:13px; line-height:1.55; margin-top:8px; }
    .compact-poster-card .micro-copy { display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }
    .poster-quicklook { width:100%; margin-top:10px; padding:9px 10px; border-radius:14px; color:var(--text); background:rgba(255,255,255,.10); border:1px solid var(--line); }
    .cinema-tile { aspect-ratio:3/4; min-height:0; display:block; isolation:isolate; scroll-snap-align:start; }
    .cinema-tile .poster { height:100%; padding:0; }
    .poster-body-overlay { position:absolute; inset:auto 0 0; padding:50px 10px 10px; background:linear-gradient(180deg,rgba(11,16,32,0),rgba(11,16,32,.82) 34%,rgba(11,16,32,.96)); transform:translateY(calc(100% - 92px)); transition:transform .22s ease, background .22s ease; }
    .cinema-tile:hover .poster-body-overlay, .cinema-tile:focus-within .poster-body-overlay { transform:translateY(0); background:linear-gradient(180deg,rgba(11,16,32,.05),rgba(11,16,32,.86) 26%,rgba(11,16,32,.98)); }
    .cinema-tile .poster-body h3 { margin:6px 0 5px; font-size:15px; line-height:1.18; }
    .cinema-tile .badge { font-size:11px; padding:3px 7px; margin:1px; }
    .cinema-tile .meta-line { font-size:12px; line-height:1.35; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
    .cinema-tile .micro-copy { margin-top:6px; font-size:12px; line-height:1.42; -webkit-line-clamp:2; }
    .cinema-tile .poster-quicklook { margin-top:7px; padding:7px 8px; border-radius:12px; font-size:12px; }
    .recommendation-overview { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; padding:12px 14px; border:1px solid rgba(96,165,250,.22); border-radius:20px; background:rgba(96,165,250,.08); }
    .anime-channel-strip { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin:-2px 0 18px; padding:14px; border:1px solid rgba(167,139,250,.26); border-radius:22px; background:linear-gradient(135deg,rgba(167,139,250,.14),rgba(34,211,238,.07)); }
    .anime-channel-strip .badge { border-color:rgba(245,196,81,.30); color:#FDE68A; background:rgba(245,196,81,.08); }
    .anime-channel-strip button { flex:0 1 auto; }
    .show-more-panel { display:flex; align-items:center; justify-content:center; gap:10px; flex-wrap:wrap; padding:14px; border:1px dashed rgba(245,196,81,.32); border-radius:22px; background:rgba(245,196,81,.06); }
    .people-grid { display:grid; grid-template-columns:1fr; gap:12px; margin:14px 0; }
    .person-chip { display:inline-flex; align-items:center; gap:8px; padding:7px 10px; border:1px solid var(--line); border-radius:999px; background:rgba(255,255,255,.07); margin:3px; color:var(--text); }
    .person-chip .person-photo { width:30px; height:30px; min-width:30px; border-radius:50%; margin:0; box-shadow:none; }
    .avatar { width:30px; height:30px; display:inline-grid; place-items:center; border-radius:50%; background:linear-gradient(135deg,#F5C451,#60A5FA); color:#0B1020; font-weight:950; }
    .people-carousel { display:grid; grid-auto-flow:column; grid-auto-columns:minmax(150px,190px); gap:12px; overflow-x:auto; padding:6px 0 14px; margin:12px 0; }
    .people-spotlight-rail { grid-auto-columns:minmax(168px,224px); gap:14px; padding:8px 2px 18px; scroll-snap-type:x proximity; }
    .person-card { border:1px solid var(--line); border-radius:20px; padding:12px; background:linear-gradient(180deg,rgba(255,255,255,.10),rgba(255,255,255,.04)); color:var(--text); text-align:left; min-height:214px; position:relative; overflow:hidden; scroll-snap-align:start; }
    .person-card:before { content:""; position:absolute; inset:0; background:radial-gradient(circle at 30% 0%,rgba(245,196,81,.15),transparent 42%); pointer-events:none; }
    .person-card > * { position:relative; z-index:1; }
    .person-photo { position:relative; width:100%; height:112px; display:block; border-radius:16px; overflow:hidden; margin-bottom:10px; background:linear-gradient(135deg,rgba(245,196,81,.22),rgba(96,165,250,.20)); box-shadow:0 16px 34px rgba(0,0,0,.30); }
    .person-photo img { width:100%; height:100%; object-fit:cover; display:block; }
    .portrait-fallback { border:1px solid rgba(245,196,81,.24); background:radial-gradient(circle at 30% 20%,rgba(245,196,81,.34),transparent 34%),linear-gradient(135deg,#111827,#312E81 58%,#0F172A); }
    .portrait-source { position:absolute; left:10px; right:10px; bottom:10px; display:inline-flex; justify-content:center; padding:4px 7px; border-radius:999px; border:1px solid rgba(255,255,255,.18); background:rgba(11,16,32,.74); color:#E0F2FE; font-size:11px; line-height:1.25; backdrop-filter:blur(12px); }
    .people-photo-enriching { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; margin:0 0 12px; padding:12px 14px; border:1px solid rgba(34,211,238,.25); border-radius:18px; background:linear-gradient(135deg,rgba(34,211,238,.12),rgba(245,196,81,.07)); }
    .people-photo-enriching.loading { animation:sourceLanePulse 1.45s ease-in-out infinite; }
    .person-card .avatar { width:54px; height:54px; font-size:18px; margin-bottom:10px; }
    .person-card small { display:block; color:var(--muted); line-height:1.5; margin-top:6px; }
    .drawer-poster { width:150px; min-height:220px; border-radius:20px; overflow:hidden; background:#111827; margin:8px 0 18px; }
    .drawer-poster img { width:100%; height:100%; object-fit:cover; display:block; }
    .detail-scrim { position:fixed; inset:0; z-index:18; opacity:0; pointer-events:none; border:0; border-radius:0; margin:0; padding:0; background:radial-gradient(circle at 70% 20%,rgba(245,196,81,.12),transparent 30%),rgba(2,6,23,.56); backdrop-filter:blur(10px); transition:opacity .34s var(--ease-premium); }
    .detail-open .detail-scrim { opacity:1; pointer-events:auto; }
    .drawer { position:fixed; inset:16px 16px 16px auto; width:min(680px,calc(100vw - 32px)); background:linear-gradient(160deg,rgba(11,16,32,.96),rgba(15,23,42,.92)); border:1px solid rgba(245,196,81,.18); border-radius:34px; transform:translateX(105%) scale(.98); transform-origin:right center; transition:transform .38s var(--ease-premium), box-shadow .38s var(--ease-premium), opacity .28s ease; z-index:20; padding:26px; overflow:auto; opacity:.88; box-shadow:0 38px 140px rgba(0,0,0,.0); }
    .drawer.spring-drawer { will-change:transform, opacity; }
    .drawer.open { transform:translateX(0) scale(1); opacity:1; box-shadow:0 38px 140px rgba(0,0,0,.56), inset 0 1px 0 rgba(255,255,255,.08); }
    .detail-cinematic { position:relative; display:grid; gap:22px; min-height:100%; isolation:isolate; }
    .detail-backdrop { position:absolute; inset:-26px -26px auto -26px; height:360px; opacity:.42; filter:blur(24px) saturate(1.25); transform:scale(1.08); z-index:-2; overflow:hidden; }
    .detail-backdrop img { width:100%; height:100%; object-fit:cover; }
    .detail-backdrop:after { content:""; position:absolute; inset:0; background:linear-gradient(180deg,rgba(11,16,32,.08),#0B1020 86%); }
    .detail-hero { display:grid; grid-template-columns:170px 1fr; gap:18px; align-items:end; padding-top:28px; }
    .poster-parallax { width:170px; min-height:252px; border-radius:26px; overflow:hidden; background:#111827; box-shadow:0 30px 70px rgba(0,0,0,.46); transform:perspective(900px) rotateY(-6deg); animation:detailFloat 5.2s ease-in-out infinite; }
    .poster-parallax img { width:100%; height:100%; object-fit:cover; display:block; }
    .detail-title { font-size:clamp(34px,6vw,62px); line-height:.95; margin:8px 0; letter-spacing:-.055em; }
    .detail-orbit { display:flex; gap:8px; flex-wrap:wrap; margin:12px 0; }
    .detail-orbit .badge { border-color:rgba(245,196,81,.32); background:rgba(245,196,81,.10); color:#F8FAFC; }
    .detail-section { border:1px solid rgba(255,255,255,.12); border-radius:24px; padding:16px; background:linear-gradient(145deg,rgba(255,255,255,.10),rgba(255,255,255,.045)); box-shadow:0 18px 48px rgba(0,0,0,.22); }
    .story-timeline { display:grid; gap:10px; counter-reset:story; }
    .story-timeline li { list-style:none; position:relative; padding:12px 12px 12px 46px; border:1px solid rgba(255,255,255,.10); border-radius:18px; background:rgba(255,255,255,.055); }
    .story-timeline li:before { counter-increment:story; content:counter(story); position:absolute; left:12px; top:12px; width:24px; height:24px; display:grid; place-items:center; border-radius:50%; background:var(--gold); color:#0B1020; font-weight:950; }
    .reason-stack { display:grid; gap:10px; padding:0; margin:0; }
    .reason-stack li { list-style:none; padding:12px; border-radius:18px; background:linear-gradient(135deg,rgba(74,222,128,.13),rgba(96,165,250,.09)); border:1px solid rgba(74,222,128,.20); }
    .detail-tabs { display:flex; gap:8px; flex-wrap:wrap; position:sticky; top:-26px; z-index:2; padding:10px 0; backdrop-filter:blur(16px); }
    .detail-tab { border:1px solid var(--line); color:var(--text); background:rgba(255,255,255,.10); }
    .magnetic-person { transition:transform .18s ease, border-color .18s ease, box-shadow .18s ease; }
    .magnetic-person:hover { transform:translateY(-4px) scale(1.02); border-color:rgba(245,196,81,.55); box-shadow:0 22px 50px rgba(245,196,81,.13); }
    .related-strip { display:grid; grid-auto-flow:column; grid-auto-columns:minmax(140px,180px); gap:12px; overflow-x:auto; padding-bottom:8px; }
    .related-card { text-align:left; color:var(--text); border:1px solid var(--line); border-radius:18px; background:rgba(255,255,255,.07); padding:10px; }
    .related-card .poster { height:178px; border-radius:14px; overflow:hidden; margin-bottom:8px; }
    .spotlight-modal { position:fixed; inset:auto 24px 24px auto; width:min(420px,calc(100vw - 48px)); border:1px solid rgba(245,196,81,.28); border-radius:28px; padding:20px; background:rgba(11,16,32,.94); box-shadow:0 28px 100px rgba(0,0,0,.50); z-index:30; animation:shimmerSweep .7s ease both; }

    .batch-shuffle { position:relative; overflow:hidden; border:1px solid rgba(34,211,238,.34); color:#ECFEFF; background:linear-gradient(135deg,rgba(34,211,238,.18),rgba(167,139,250,.14)); box-shadow:0 10px 32px rgba(34,211,238,.10); transition:transform .18s var(--ease-premium), box-shadow .18s var(--ease-premium); }
    .batch-shuffle:hover { transform:translateY(-2px); box-shadow:0 18px 42px rgba(34,211,238,.18); }
    .batch-shuffle:after { content:""; position:absolute; inset:0; transform:translateX(-120%); background:linear-gradient(90deg,transparent,rgba(255,255,255,.22),transparent); transition:transform .55s var(--ease-premium); }
    .batch-shuffle:hover:after { transform:translateX(120%); }
    .detail-action-row { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
    .people-skeleton-strip { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-top:10px; }
    .people-skeleton { min-height:84px; border-radius:18px; background:linear-gradient(90deg,rgba(255,255,255,.07),rgba(255,255,255,.16),rgba(255,255,255,.07)); background-size:220% 100%; animation:skeletonShimmer 1.1s linear infinite; }
    .drawer.open .detail-section { animation:detailSectionReveal .42s var(--ease-premium) both; }
    .drawer.open .detail-section:nth-of-type(2) { animation-delay:.04s; }
    .drawer.open .detail-section:nth-of-type(3) { animation-delay:.08s; }
    .detail-tab.active { background:linear-gradient(135deg,rgba(245,196,81,.28),rgba(34,211,238,.16)); border-color:rgba(245,196,81,.44); }
    @keyframes skeletonShimmer { to { background-position:-220% 0; } }
    @keyframes detailSectionReveal { from { opacity:0; transform:translateY(12px) scale(.985); } to { opacity:1; transform:translateY(0) scale(1); } }

    @keyframes detailFloat { 0%,100% { transform:perspective(900px) rotateY(-6deg) translateY(0); } 50% { transform:perspective(900px) rotateY(0deg) translateY(-9px); } }
    @keyframes shimmerSweep { from { opacity:0; transform:translateY(18px) scale(.98); } to { opacity:1; transform:translateY(0) scale(1); } }
    .empty-state { padding:34px; border:1px dashed var(--line); border-radius:28px; text-align:center; color:var(--muted); }
    .mini-list { color:var(--muted); line-height:1.8; }
    .warn { color:var(--red); }
    @media(max-width:1180px) { .detail-open .workspace.recommendation-stage #mainPanel,.detail-open .workspace.recommendation-stage.results-rail-hidden #mainPanel { margin-right:0; } .detail-open .banner-poster-float { display:none; } }
    @media(max-width:980px) { .workspace,.workspace.recommendation-stage { grid-template-columns:1fr; } .workspace.recommendation-stage #controlPanel,.workspace.recommendation-stage #mainPanel { grid-column:auto; } .results-control-rail { position:relative; top:auto; left:auto; width:auto; height:auto; min-height:0; max-height:none; overflow:visible; } .results-control-inner { height:auto; overflow:visible; } .metric-grid,.step-rail,.hero-showcase { grid-template-columns:1fr; } .hero-track,.hero-dot-strip { grid-template-columns:1fr 1fr; } .app-shell,.results-shell { padding:16px; } }
  </style>
</head>
<body>
  <div class="ambient-orb orb-a" aria-hidden="true"></div>
  <div class="ambient-orb orb-b" aria-hidden="true"></div>
  <main class="app-shell homepage-studio" id="appShell">
    <section class="cinematic-hero">
      <div class="hero-kicker">Local-first Douban Curation</div>
      <h1>CineScope Studio</h1>
      <p class="hero-copy">豆瓣私人影视策展器：同步你的看过与想看，分析口味，用电影、电视剧、动漫构建一面真正有吸引力的推荐海报墙。</p>
      <div class="privacy-pill">本地运行，不保存 Cookie</div>
      <div class="cinema-nav"><span>电影策展</span><span>剧集避雷</span><span>动漫补齐</span><span>图片韧性</span><span>口味 DNA</span></div>
    </section>
    <nav id="stepNav" class="step-rail" aria-label="任务步骤"></nav>
    <section class="workspace" id="workspace">
      <aside class="glass-panel" id="controlPanel"></aside>
      <section class="glass-panel" id="mainPanel"></section>
    </section>
  </main>
  <button class="rail-toggle-fab" id="railToggleFab" onclick="showResultsRail()" aria-expanded="false">☰ 显示片单遥控器</button>
  <button id="detailScrim" class="detail-scrim" onclick="closeDetailDrawer()" aria-label="关闭详情浮层"></button>
  <aside class="drawer spring-drawer" id="detailDrawer"></aside>
<script>
const PREF_KEY = 'CINESCOPE_PREFS_V2';
const COOKIE_SESSION_KEY = 'CINESCOPE_SESSION_COOKIE';
const LAST_RECOMMENDATION_KEY = 'CINESCOPE_LAST_RECOMMENDATION_V4';
const OLD_RECOMMENDATION_KEYS = ['CINESCOPE_LAST_RECOMMENDATION_V1','CINESCOPE_LAST_RECOMMENDATION_V2','CINESCOPE_LAST_RECOMMENDATION_V3'];
const POSTER_SOURCE_PREF_KEY = 'CINESCOPE_POSTER_SOURCE_PREFS_V1';
const POSTER_RESCUE_VERSION = 8;
const defaultDoubanUser = 'https://www.douban.com/people/272042071/?_dtcc=1&_i=33953249Yxbr5m';
const canonicalPosterMap = __CANONICAL_POSTER_MAP__;
const canonicalPosterByTitle = __CANONICAL_POSTER_BY_TITLE__;
const canonicalPeoplePhotoMap = __CANONICAL_PEOPLE_PHOTO_MAP__;
const canonicalTitleMetadataMap = __CANONICAL_TITLE_METADATA__;
const canonicalPeoplePhotoByName = Object.entries(canonicalPeoplePhotoMap || {}).reduce((acc, [subjectId, people]) => { Object.entries(people || {}).forEach(([name, url]) => { if (name && url) { acc[name] = acc[name] || url; acc[`导演:${name}`] = acc[`导演:${name}`] || url; acc[`主演:${name}`] = acc[`主演:${name}`] || url; acc[`${subjectId}:${name}`] = acc[`${subjectId}:${name}`] || url; } }); return acc; }, {});
const curatedPlaceholderPeople = new Set(['影像作者A','类型片大师','现实主义导演','叙事工程师','镜头语言专家','高口碑演员','银幕群像核心','情绪表演者','角色弧光担当','戏剧张力担当','剧集统筹','现代剧作者','犯罪叙事导演','职业剧创作者','群像调度者','剧集群像核心','长线角色担当','台词节奏担当','情绪细节担当','反转推动者','动画监督','分镜作者','系列构成','视觉演出家','动画叙事导演','声优A','声优B','声线记忆点','角色塑造担当','群像声演']);
const stalePremiumDisplayTitleMap = {
  'Arcane':'英雄联盟：双城之战',
  'Invincible':'无敌少侠',
  'Love, Death & Robots':'爱，死亡和机器人',
  'Love Death and Robots':'爱，死亡和机器人',
  'Avatar: The Last Airbender':'降世神通：最后的气宗',
  'Avatar The Last Airbender':'降世神通：最后的气宗',
  '黑暗騎士':'黑暗骑士',
  '東京物語':'东京物语',
  '樂來越愛你':'爱乐之城',
  '新天堂樂園':'天堂电影院',
  '鬥陣俱樂部':'搏击俱乐部',
  '法蘭西特派週報':'法兰西特派',
  '幸福綠皮書':'绿皮书',
  '星際牛仔':'星际牛仔',
  '奇諾之旅':'奇诺之旅',
  '蟲師':'虫师',
  'SPY?FAMILY間諜家家酒':'间谍过家家',
  '钢之炼金术师 FULLMETAL ALCHEMIST':'钢之炼金术师FA',
  '電腦線圈':'电脑线圈',
  'SPY\u00d7FAMILY間諜家家酒':'间谍过家家',
  '燃燒烈愛':'燃烧',
  '羅生門 (電影)':'罗生门',
  '罗生门 (电影)':'罗生门',
  '飲食男女 (電影)':'饮食男女',
  '饮食男女 (电影)':'饮食男女',
  '十二怒漢 (電影)':'十二怒汉',
  '七宗罪 (電影)':'七宗罪',
  '頂尖對決':'致命魔术',
  '信号 (信息论)':'信号',
  '「法」妻':'傲骨贤妻',
  '機智醫生生活':'机智医生生活',
  '進擊的巨人 (2015年電影)':'进击的巨人',
  '乒乓 (漫畫)':'乒乓',
  '殺人回憶':'杀人回忆',
};
const GLOBAL_ANIME_CHANNELS = ['动漫 · 国创动画','动漫 · 欧美动画','动漫 · 日漫精品'];
const state = { step:1, items:[], ratedItems:[], counts:{}, completeness:{}, errors:[], diagnostics:[], recommendations:[], visibleRecommendations:[], sections:[], activeSection:'全部', heroIndex:0, heroBySection:{}, gridLimitBySection:{}, batchOffsetBySection:{}, railHidden:true, ratingsCsv:'', candidatesCsv:'', profile:null, lastCounts:{}, recovery:null, lastUserInput:'', lastUserId:'', lastCookieProvided:false, prefs:null, posterSources:null, posterJob:null, posterRescueInFlight:false, posterRescueVersion:0, filteredLowConfidence:0, peopleEnrichmentStatus:{} };
const $ = id => document.getElementById(id);
function setStageLayout(stage) { const isResults = stage === 'results'; const railHidden = isResults && state.railHidden; $('appShell')?.classList.toggle('results-shell', isResults); $('appShell')?.classList.toggle('rail-hidden-shell', railHidden); $('appShell')?.classList.toggle('figma-grade-stage', isResults); $('workspace')?.classList.toggle('recommendation-stage', isResults); $('workspace')?.classList.toggle('results-rail-hidden', railHidden); if ($('controlPanel')) $('controlPanel').className = isResults ? 'glass-panel results-control-rail' : 'glass-panel'; $('mainPanel')?.classList.toggle('drawer-safe-stage', isResults); const fab = $('railToggleFab'); if (fab) { fab.classList.toggle('visible', railHidden); fab.setAttribute('aria-expanded', String(!railHidden)); } }
function scrollToResults(anchor='railWall') { document.getElementById(anchor || 'railWall')?.scrollIntoView({ behavior:'smooth', block:'start' }); }
function toggleResultsRail(force) { state.railHidden = typeof force === 'boolean' ? force : !state.railHidden; if (state.step === 3) { persistRecommendationSnapshot(); renderRecommendations(); } else setStageLayout('flow'); }
function hideResultsRail() { toggleResultsRail(true); }
function showResultsRail() { toggleResultsRail(false); }
function esc(value) { return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
function setStatus(text) { const el = $('status'); if (el) el.textContent = text || ''; }
function safeJsonParse(value, fallback={}) { try { return value ? JSON.parse(value) : fallback; } catch (_) { return fallback; } }
function isLowConfidencePublicCandidate(r) { const source = String(r?.source || r?.item?.source || ''); const rating = r?.douban_rating ?? r?.item?.douban_rating; const tags = [...(r?.tags || []), ...(r?.item?.tags || [])]; return (source.startsWith('douban_explore:') || source.startsWith('douban_plan:')) && (rating === null || rating === undefined || rating === '' || rating === '-') && !tags.includes('\u60f3\u770b') && !tags.includes('\u770b\u8fc7'); }
function isNumberedCuratedPlaceholder(r) { const title = recTitle(r); return /^(?:\u7535\u5f71\u7b56\u5c55|\u5267\u96c6\u7b56\u5c55|\u52a8\u6f2b\u5267\u96c6\u7b56\u5c55)\d+$/.test(title); }
function normalizedPremiumDisplayTitle(title) { const key = String(title || '').trim(); return stalePremiumDisplayTitleMap[key] || key; }
function normalizeRecommendationTitle(r) {
  if (!r) return 0;
  const current = String(r.title || r.item?.title || '').trim();
  const normalized = normalizedPremiumDisplayTitle(current);
  if (!current || normalized === current) return 0;
  r.title = normalized;
  if (r.item) r.item.title = normalized;
  ['summary','short_reason'].forEach(key => { if (typeof r[key] === 'string') r[key] = r[key].split(current).join(normalized); if (r.item && typeof r.item[key] === 'string') r.item[key] = r.item[key].split(current).join(normalized); });
  if (String(r.cover || '').startsWith('data:image/svg+xml')) r.cover = '';
  if (r.item && String(r.item.cover || '').startsWith('data:image/svg+xml')) r.item.cover = '';
  return 1;
}
function hasPlaceholderPeopleList(names) { return !(names || []).length || (names || []).some(name => curatedPlaceholderPeople.has(String(name || '').trim())); }
function applyCanonicalTitleMetadata(r) {
  if (!r) return 0;
  const title = normalizedPremiumDisplayTitle(String(r.title || r.item?.title || '').trim());
  let changed = 0;
  const assignBoth = (key, value) => { if (value === undefined || value === null) return; if (JSON.stringify(r[key]) !== JSON.stringify(value)) { r[key] = value; changed = 1; } if (r.item && JSON.stringify(r.item[key]) !== JSON.stringify(value)) { r.item[key] = value; changed = 1; } };
  const canonicalOnly = canonicalPosterRawFor(r);
  if (canonicalOnly && isDesignedPoster(r)) assignBoth('cover', canonicalOnly);
  const meta = canonicalTitleMetadataMap[title];
  if (!meta) return changed;
  const currentId = String(r.douban_id || r.item?.douban_id || '').trim();
  const synthetic = !currentId || currentId.startsWith('premium-') || /subject_search/i.test(String(r.url || r.item?.url || ''));
  if (meta.douban_id && synthetic) {
    assignBoth('douban_id', String(meta.douban_id));
    assignBoth('url', `https://movie.douban.com/subject/${meta.douban_id}/`);
  }
  if (meta.year && (synthetic || !(r.year || r.item?.year))) assignBoth('year', Number(meta.year));
  if (Array.isArray(meta.genres) && (synthetic || !recArray(r,'genres').length)) assignBoth('genres', meta.genres);
  if (Array.isArray(meta.countries) && (synthetic || !recArray(r,'countries').length)) assignBoth('countries', meta.countries);
  if (Array.isArray(meta.directors) && hasPlaceholderPeopleList(recArray(r,'directors'))) assignBoth('directors', meta.directors);
  if (Array.isArray(meta.casts) && hasPlaceholderPeopleList(recArray(r,'casts'))) assignBoth('casts', meta.casts);
  if (meta.people_photos && typeof meta.people_photos === 'object') {
    r.raw = r.raw && typeof r.raw === 'object' ? r.raw : {};
    r.raw.people_photos = {...(r.raw.people_photos || {}), ...meta.people_photos};
    if (r.item) { r.item.raw = r.item.raw && typeof r.item.raw === 'object' ? r.item.raw : {}; r.item.raw.people_photos = {...(r.item.raw.people_photos || {}), ...meta.people_photos}; }
    changed = 1;
  }
  const canonical = canonicalPosterRawFor(r);
  if (canonical && (isDesignedPoster(r) || synthetic)) assignBoth('cover', canonical);
  return changed;
}
function normalizeRecommendationDisplayData() {
  let titleRepairs = 0;
  let metadataRepairs = 0;
  (state.recommendations || []).forEach(row => { titleRepairs += normalizeRecommendationTitle(row); metadataRepairs += applyCanonicalTitleMetadata(row); });
  (state.sections || []).forEach(section => (section.items || []).forEach(row => { titleRepairs += normalizeRecommendationTitle(row); metadataRepairs += applyCanonicalTitleMetadata(row); }));
  state.titleRepairs = (state.titleRepairs || 0) + titleRepairs;
  state.metadataRepairs = (state.metadataRepairs || 0) + metadataRepairs;
  return { titleRepairs, metadataRepairs };
}
function cleanupStalePlaceholderRecommendations() { const before = (state.recommendations || []).length; state.recommendations = (state.recommendations || []).filter(r => !isNumberedCuratedPlaceholder(r)); const allowed = new Set(state.recommendations.map(item => itemKey(item))); state.sections = (state.sections || []).map(section => ({...section, items:(section.items || []).filter(item => allowed.has(itemKey(item)))})).filter(section => (section.items || []).length || ['\u5168\u90e8','\u7cbe\u9009','\u7535\u5f71','\u7535\u89c6\u5267','\u52a8\u6f2b'].includes(section.name)); const removed = Math.max(0, before - state.recommendations.length); state.filteredStalePlaceholders = (state.filteredStalePlaceholders || 0) + removed; return removed; }
function cleanupLowConfidenceRecommendations() { const before = (state.recommendations || []).length; state.recommendations = (state.recommendations || []).filter(r => !isLowConfidencePublicCandidate(r)); const allowed = new Set(state.recommendations.map(item => itemKey(item))); state.sections = (state.sections || []).map(section => ({...section, items:(section.items || []).filter(item => allowed.has(itemKey(item)))})).filter(section => (section.items || []).length || ['\u5168\u90e8','\u7cbe\u9009','\u7535\u5f71','\u7535\u89c6\u5267','\u52a8\u6f2b'].includes(section.name)); const filteredLowConfidence = Math.max(0, before - state.recommendations.length); state.filteredLowConfidence = (state.filteredLowConfidence || 0) + filteredLowConfidence; return filteredLowConfidence; }
function cleanupRecommendationQuality() { const displayCleanup = normalizeRecommendationDisplayData(); return { ...displayCleanup, lowConfidence:cleanupLowConfidenceRecommendations(), stalePlaceholders:cleanupStalePlaceholderRecommendations() }; }
function cleanupOldRecommendationSnapshots() {
  OLD_RECOMMENDATION_KEYS.forEach(key => {
    try { localStorage.removeItem(key); } catch (_) {}
  });
}
function persistRecommendationSnapshot() {
  const snapshot = {
    recommendations: state.recommendations || [],
    sections: state.sections || [],
    profile: state.profile || null,
    lastCounts: state.lastCounts || {},
    activeSection: state.activeSection || '全部',
    gridLimitBySection: state.gridLimitBySection || {},
    batchOffsetBySection: state.batchOffsetBySection || {},
    heroBySection: state.heroBySection || {},
    railHidden: state.railHidden !== false,
    posterRescueVersion: state.posterRescueVersion || 0,
    savedAt: Date.now(),
  };
  try { localStorage.setItem(LAST_RECOMMENDATION_KEY, JSON.stringify(snapshot)); } catch (_) {}
}
function restoreRecommendationSnapshot() {
  const snapshot = safeJsonParse(localStorage.getItem(LAST_RECOMMENDATION_KEY), null);
  if (!snapshot || !Array.isArray(snapshot.recommendations) || !snapshot.recommendations.length) return false;
  state.recommendations = snapshot.recommendations;
  state.sections = Array.isArray(snapshot.sections) ? snapshot.sections : [];
  state.profile = snapshot.profile || null;
  state.lastCounts = snapshot.lastCounts || {};
  state.activeSection = snapshot.activeSection || '全部';
  state.gridLimitBySection = snapshot.gridLimitBySection || {};
  state.batchOffsetBySection = snapshot.batchOffsetBySection || {};
  state.heroBySection = snapshot.heroBySection || {};
  state.railHidden = snapshot.railHidden !== false;
  state.posterRescueVersion = Number(snapshot.posterRescueVersion || 0);
  const cleanup = cleanupRecommendationQuality();
  renderRecommendations();
  if (cleanup.lowConfidence || cleanup.stalePlaceholders || cleanup.titleRepairs || cleanup.metadataRepairs) persistRecommendationSnapshot();
  const notes = [];
  if (cleanup.lowConfidence) notes.push(`已移除 ${cleanup.lowConfidence} 个无评分豆瓣探索噪声`);
  if (cleanup.stalePlaceholders) notes.push(`已移除 ${cleanup.stalePlaceholders} 个旧占位标题`);
  if (cleanup.titleRepairs) notes.push(`已修正 ${cleanup.titleRepairs} 个旧快照标题`);
  if (cleanup.metadataRepairs) notes.push(`已补全 ${cleanup.metadataRepairs} 个旧快照演职员`);
  setStatus(`已恢复上次推荐片单：${state.recommendations.length} 部${notes.length ? '，' + notes.join('，') : ''}。`);
  maybeAutoRescuePosters();
  return true;
}
function tryRestoreRecommendationSnapshot() { return restoreRecommendationSnapshot(); }
function loadUserPrefs() { const prefs = safeJsonParse(localStorage.getItem(PREF_KEY), {}); state.prefs = { userInput: prefs.userInput || defaultDoubanUser, expectedCollect: prefs.expectedCollect ?? 242, expectedWish: prefs.expectedWish ?? 34, maxPages: prefs.maxPages ?? 80, includeWish: prefs.includeWish ?? true, rememberCookieSession: prefs.rememberCookieSession ?? false }; return state.prefs; }
function saveUserPrefs() { const prefs = { userInput:$('doubanUser')?.value.trim() || defaultDoubanUser, expectedCollect:Number($('expectedCollect')?.value || 242), expectedWish:Number($('expectedWish')?.value || 34), maxPages:Number($('maxPages')?.value || 80), includeWish:Boolean($('includeWish')?.checked), rememberCookieSession:Boolean($('rememberCookieSession')?.checked) }; localStorage.setItem(PREF_KEY, JSON.stringify(prefs)); state.prefs = prefs; return prefs; }
function hydrateCrawlerControls() { const prefs = loadUserPrefs(); if ($('doubanUser')) $('doubanUser').value = prefs.userInput || defaultDoubanUser; if ($('expectedCollect')) $('expectedCollect').value = prefs.expectedCollect ?? 242; if ($('expectedWish')) $('expectedWish').value = prefs.expectedWish ?? 34; if ($('maxPages')) $('maxPages').value = prefs.maxPages ?? 80; if ($('includeWish')) $('includeWish').checked = prefs.includeWish !== false; if ($('rememberCookieSession')) $('rememberCookieSession').checked = Boolean(prefs.rememberCookieSession); const rememberedCookie = normalizeCookieInput(sessionStorage.getItem(COOKIE_SESSION_KEY) || ''); if (rememberedCookie && prefs.rememberCookieSession && $('doubanCookie')) { $('doubanCookie').value = rememberedCookie; state.lastCookieProvided = true; } previewDoubanInput(); }
function persistCrawlerControls() { const prefs = saveUserPrefs(); const cookieBox = $('doubanCookie'); const cookieValue = normalizeCookieInput(cookieBox?.value || ''); if (cookieBox && cookieValue && cookieBox.value.trim() !== cookieValue) cookieBox.value = cookieValue; if (prefs.rememberCookieSession && cookieValue) sessionStorage.setItem(COOKIE_SESSION_KEY, cookieValue); else sessionStorage.removeItem(COOKIE_SESSION_KEY); return prefs; }
function clearSessionCookie() { sessionStorage.removeItem(COOKIE_SESSION_KEY); if ($('doubanCookie')) $('doubanCookie').value = ''; state.lastCookieProvided = false; previewDoubanInput(); setStatus('已清除本次浏览器会话 Cookie。'); }
function copyProxyCommand() { const text = '$env:DOUBAN_RECOMMENDER_HTTP_PROXY="http://127.0.0.1:7890"'; navigator.clipboard?.writeText(text); setStatus('代理命令已复制。'); }
function defaultPosterSources() { return { tmdb_api_key:'', omdb_api_key:'', enable_tmdb_api:true, enable_omdb:true, enable_tvmaze:true, enable_anilist:true, enable_jikan:true, enable_tmdb_html:true, enable_douban:true, enable_wikipedia:false, prefer_external_over_douban:true }; }
function loadPosterSourcePrefs() { const prefs = { ...defaultPosterSources(), ...safeJsonParse(localStorage.getItem(POSTER_SOURCE_PREF_KEY), {}) }; state.posterSources = prefs; return prefs; }
function savePosterSourcePrefs() { const prefs = { ...defaultPosterSources(), tmdb_api_key:$('tmdbApiKey')?.value.trim() || '', omdb_api_key:$('omdbApiKey')?.value.trim() || '', enable_tmdb_api:$('enableTmdbApi')?.checked !== false, enable_omdb:$('enableOmdbApi')?.checked !== false, enable_tvmaze:$('enableTvmazePoster')?.checked !== false, enable_anilist:$('enableAnilistPoster')?.checked !== false, enable_jikan:$('enableJikanPoster')?.checked !== false, enable_tmdb_html:$('enableTmdbHtml')?.checked !== false, enable_douban:$('enableDoubanPoster')?.checked !== false, enable_wikipedia:Boolean($('enableWikipediaPoster')?.checked), prefer_external_over_douban:$('preferExternalPoster')?.checked !== false }; localStorage.setItem(POSTER_SOURCE_PREF_KEY, JSON.stringify(prefs)); state.posterSources = prefs; return prefs; }
function hydratePosterSourceControls() { const prefs = loadPosterSourcePrefs(); if ($('tmdbApiKey')) $('tmdbApiKey').value = prefs.tmdb_api_key || ''; if ($('omdbApiKey')) $('omdbApiKey').value = prefs.omdb_api_key || ''; if ($('enableTmdbApi')) $('enableTmdbApi').checked = prefs.enable_tmdb_api !== false; if ($('enableOmdbApi')) $('enableOmdbApi').checked = prefs.enable_omdb !== false; if ($('enableTvmazePoster')) $('enableTvmazePoster').checked = prefs.enable_tvmaze !== false; if ($('enableAnilistPoster')) $('enableAnilistPoster').checked = prefs.enable_anilist !== false; if ($('enableJikanPoster')) $('enableJikanPoster').checked = prefs.enable_jikan !== false; if ($('enableTmdbHtml')) $('enableTmdbHtml').checked = prefs.enable_tmdb_html !== false; if ($('enableDoubanPoster')) $('enableDoubanPoster').checked = prefs.enable_douban !== false; if ($('enableWikipediaPoster')) $('enableWikipediaPoster').checked = Boolean(prefs.enable_wikipedia); if ($('preferExternalPoster')) $('preferExternalPoster').checked = prefs.prefer_external_over_douban !== false; }
function posterSourcePayload() { return { ...loadPosterSourcePrefs(), tmdb_api_key:$('tmdbApiKey')?.value.trim() || state.posterSources?.tmdb_api_key || '', omdb_api_key:$('omdbApiKey')?.value.trim() || state.posterSources?.omdb_api_key || '' }; }
function renderPosterSourcePanel(compact=false) { return `<section class="source-settings anti-overflow"><div><span class="badge">多源海报引擎</span><h3>图片源设置：TMDb / OMDb / IMDb / TVMaze / AniList / Jikan</h3><p class="hint">豆瓣 CDN 现在会触发反爬脚本，本项目会把豆瓣图自动换成 TMDb、OMDb / IMDb、TVMaze 剧集海报、AniList、Jikan / MyAnimeList 或 TMDb 公共网页图源。TMDb / OMDb Key 只保存在浏览器 localStorage，并随本次请求发送给本机后端，不写入磁盘。</p></div><div class="setting-grid"><label>TMDb API Key<input id="tmdbApiKey" type="password" oninput="savePosterSourcePrefs()" placeholder="免费注册后粘贴 v3 api key"></label><label>OMDb API Key<input id="omdbApiKey" type="password" oninput="savePosterSourcePrefs()" placeholder="可选：IMDb 海报兜底"></label></div><div class="setting-grid"><label class="toggle-row"><input id="enableTmdbApi" type="checkbox" onchange="savePosterSourcePrefs()" checked>优先 TMDb API</label><label class="toggle-row"><input id="enableOmdbApi" type="checkbox" onchange="savePosterSourcePrefs()" checked>启用 OMDb / IMDb</label><label class="toggle-row"><input id="enableTvmazePoster" type="checkbox" onchange="savePosterSourcePrefs()" checked>TVMaze 免费剧集源</label><label class="toggle-row"><input id="enableAnilistPoster" type="checkbox" onchange="savePosterSourcePrefs()" checked>AniList 免费动漫源</label><label class="toggle-row"><input id="enableJikanPoster" type="checkbox" onchange="savePosterSourcePrefs()" checked>Jikan / MyAnimeList 免费动漫源</label><label class="toggle-row"><input id="enableTmdbHtml" type="checkbox" onchange="savePosterSourcePrefs()" checked>无 Key 时用 TMDb 公共页</label><label class="toggle-row"><input id="enableDoubanPoster" type="checkbox" onchange="savePosterSourcePrefs()" checked>保留豆瓣精确搜索</label><label class="toggle-row"><input id="enableWikipediaPoster" type="checkbox" onchange="savePosterSourcePrefs()">实验性 Wikipedia</label><label class="toggle-row"><input id="preferExternalPoster" type="checkbox" onchange="savePosterSourcePrefs()" checked>优先外部可加载图源</label></div><div class="api-link-row"><a class="api-link" href="https://www.themoviedb.org/settings/api" target="_blank" rel="noreferrer">免费注册 TMDb API Key</a><a class="api-link" href="https://www.omdbapi.com/apikey.aspx" target="_blank" rel="noreferrer">免费申请 OMDb API Key</a><button class="ghost" onclick="savePosterSourcePrefs();rescuePosterImages(true)">保存并重新换源</button>${compact ? '' : '<span class="hint">没有 Key 也会自动使用内置精选图 + TVMaze 无 Key 剧集源 + AniList / Jikan 动漫源 + TMDb 公共搜索；有 Key 时电影和剧集覆盖会更好。</span>'}</div></section>`; }
function extractDoubanUserId(value) { const text = String(value || '').trim(); const match = text.match(/douban\.com\/people\/([^/?#]+)/i); if (match) return decodeURIComponent(match[1]); return text && !/[/?#]/.test(text) ? text.replace(/^@/,'') : ''; }
function normalizeCookieInput(value) {
  const text = String(value || '').trim();
  if (!text || /[\r\n]/.test(text)) return '';
  const pairs = text.split(';').map(part => part.trim()).filter(Boolean);
  if (!pairs.length) return '';
  const normalized = [];
  for (const pair of pairs) {
    const separator = pair.indexOf('=');
    if (separator <= 0) return '';
    const name = pair.slice(0, separator).trim();
    const cookieValue = pair.slice(separator + 1).trim();
    if (!/^[A-Za-z0-9!#$%&'*+\-.^_`|~]+$/.test(name) || /[\x00-\x1f\x7f]/.test(cookieValue)) return '';
    normalized.push(`${name}=${cookieValue}`);
  }
  return normalized.join('; ');
}
function normalizeCookieBox() { const box = $('doubanCookie'); if (!box) return ''; const clean = normalizeCookieInput(box.value); if (box.value.trim() !== clean) box.value = clean; return clean; }
function setCookieBoxValue(value, message='已整理可见 Cookie 字符串，并自动启用本次会话记忆。') { const clean = normalizeCookieInput(value); const box = $('doubanCookie'); if (box) box.value = clean; if ($('rememberCookieSession')) $('rememberCookieSession').checked = Boolean(clean); state.lastCookieProvided = Boolean(clean); persistCrawlerControls(); previewDoubanInput(); setStatus(clean ? message : '请输入直接的 Cookie 字符串，例如 bid=...; ck=...。'); return clean; }
function renderUserInputInsight() { const input = state.lastUserInput || ''; const userId = state.lastUserId || extractDoubanUserId(input); if (!input) return `<div class="user-input-card anti-overflow"><b>链接识别等待中</b>粘贴豆瓣主页链接或用户 ID；如果豆瓣拦截，会进入 Cookie 解锁流程，避免把登录态问题误判成普通抓取失败。</div>`; const linkLine = userId ? `链接识别成功：已识别豆瓣用户 ${esc(userId)}` : '链接识别失败：请检查豆瓣主页链接是否包含 /people/用户ID/'; const rememberCookie = Boolean($('rememberCookieSession')?.checked); const hasCookieInBox = Boolean(normalizeCookieInput($('doubanCookie')?.value || '')); const cookieLine = state.lastCookieProvided ? (rememberCookie && hasCookieInBox ? '本次浏览器会话已自动填入 Cookie；Cookie 只保存在 sessionStorage，不写入磁盘、日志、缓存或报告。' : '本次已临时携带 Cookie 请求；未勾选会话记忆时同步后输入框会清空。') : '复制的是主页链接，不是授权凭证；主页链接只能识别用户 ID。遇到 403 时，只能把你已有的 Cookie 字符串手动粘贴到上方可见输入框。'; return `<div class="user-input-card anti-overflow"><b>${linkLine}</b><span>${cookieLine}</span></div>`; }
function previewDoubanInput() { const box = $('doubanUser'); if (!box) return; state.lastUserInput = box.value.trim(); state.lastUserId = extractDoubanUserId(state.lastUserInput); const insight = $('inputInsight'); if (insight) insight.innerHTML = renderUserInputInsight(); }
function renderStepNav() { const steps = [['第一步：连接豆瓣','同步看过 / 想看，校验 242 / 34 完整度'],['第二步：确认口味','评分高、剧情好，电视剧古装避雷'],['第三步：查看推荐','电影 / 电视剧 / 动漫海报墙']]; $('stepNav').innerHTML = steps.map((s,i) => `<div class="step-card"><b>${s[0]}</b>${s[1]}</div>`).join(''); }
function renderCookieImportAssistant() { return `<div class="cookie-import-assistant anti-overflow"><b>Cookie 输入说明</b><span class="hint">手动粘贴你已有的 Cookie 字符串到上方可见输入框，例如 bid=...; ck=...。这里只处理上方可见 Cookie 输入框中的内容，不读取剪贴板、浏览器资料或其他隐藏状态。</span><div class="quick-actions"><button class="ghost" onclick="setCookieBoxValue($('doubanCookie')?.value || '', '已整理可见 Cookie 格式，并自动启用本次会话记忆。')">整理可见 Cookie 格式</button></div><span class="hint">多行文本、带字段名前缀的内容或其他说明文字都会被拒绝。</span></div>`; }
function renderCookieGuide() { return `<details><summary>Cookie 教程</summary><ol class="mini-list"><li>如果公开数据够用，Cookie 留空。</li><li>只有在你已经持有 Cookie 字符串时，才把 name=value; name=value 形式的内容手动粘贴到上方可见输入框。</li><li>不要粘贴其他字段、说明文字或多行文本。</li></ol><p class="hint">Cookie 只用于本机请求豆瓣页面，不会保存到磁盘，也不会出现在推荐报告里。</p></details>`; }
function imageResilienceGuide() { return `<details class="image-resilience" open><summary>图片韧性与 Clash / V2Ray 教程</summary><div class="resilience-card" id="imageResilienceGuide"><div class="resilience-toolbar"><b>海报加载不出来时优先这样做</b><button class="ghost copy-mini" onclick="copyProxyCommand()">复制代理命令</button></div><span class="hint">本项目会先走本地 /api/image-proxy；豆瓣 CDN 若返回反爬 HTML，会自动进入 /api/poster-jobs 多源换源，也保留兼容接口 /api/enrich-posters。当前结果缺 cover 会用内置库补位；设计封面不是图片加载失败，而是等多源换源时的安全占位。可免费注册 TMDb API Key 或 OMDb API Key，IMDb 海报通常由 OMDb 返回；电视剧会额外走 TVMaze 免费源；动漫剧集会额外走 AniList 与 Jikan / MyAnimeList 免费源。</span><div class="diagnosis-card anti-overflow"><b>图片诊断</b><span>仍然看到大字标题海报时，系统会把“豆瓣 CDN · 待换源 / 设计封面”放进海报修复现场；如果浏览器还在旧服务或旧快照，也会通过版本号自动重跑。任务会逐部显示正在搜哪部、命中哪个来源、还剩多少，并在缺图补救台给出 TVMaze、AniList、MyAnimeList、TMDb、IMDb 搜索入口，不再让你干等一条进度条。</span></div><div class="proxy-command"><code>PowerShell: $env:DOUBAN_RECOMMENDER_HTTP_PROXY="http://127.0.0.1:7890"</code></div><span class="hint">Clash 常见 Mixed Port 是 7890；V2Ray / v2rayN 开启 HTTP 代理端口后填同样格式。不要粘贴订阅地址；长命令会在框内横向滚动，不再撑破侧栏。</span></div></details>`; }
function renderCrawlerPanel() {
  setStageLayout('flow');
  $('controlPanel').innerHTML = `<h2>第一步：连接豆瓣</h2>
  <div class="control-hero"><span class="badge">Cookie 解锁 · 本地隐私</span><b>把抓取失败变成可恢复流程</b><p class="hint">匿名访问遇到 403 时，页面会直接告诉你：豆瓣要求登录态、需要 Cookie，或可以跳过同步继续用高质量片库生成推荐。</p></div>
  <div class="story-panel"><b>全站同步、口味、推荐和详情统一重做</b><p class="hint">这里不再是冷冰冰的日志区，而是“同步作战室”：目标完整度、失败原因、恢复路线和下一步动作会一起显示。</p></div>
  <label>豆瓣用户 ID 或主页链接</label><textarea id="doubanUser" class="url-textarea" rows="2" oninput="persistCrawlerControls(); previewDoubanInput()" placeholder="https://www.douban.com/people/你的ID/"></textarea><div id="inputInsight" class="inputInsight"></div>
  <label>Cookie（可选）</label><textarea id="doubanCookie" oninput="persistCrawlerControls()" onblur="normalizeCookieBox(); persistCrawlerControls(); previewDoubanInput()" placeholder="如果出现 403 / 登录跳转，手动粘贴你已有的 Cookie 字符串，例如 bid=...; ck=..."></textarea>
  <label><input id="rememberCookieSession" type="checkbox" onchange="persistCrawlerControls()"> 本次浏览器会话自动填 Cookie</label>
  <button class="ghost" onclick="clearSessionCookie()">清除会话 Cookie</button>
  <div class="row"><div><label>期望看过</label><input id="expectedCollect" type="number" oninput="persistCrawlerControls()"></div><div><label>期望想看</label><input id="expectedWish" type="number" oninput="persistCrawlerControls()"></div></div>
  <label>最多抓取页数</label><input id="maxPages" type="number" min="1" max="200" oninput="persistCrawlerControls()">
  <label><input id="includeWish" type="checkbox" onchange="persistCrawlerControls()"> 同步想看</label>
  ${renderCookieImportAssistant()}${renderCookieGuide()}${imageResilienceGuide()}
  <details><summary>没有抓取数据？粘贴 CSV 继续</summary><label>评分 CSV</label><textarea id="ratingsCsv" placeholder="title,my_rating,media_type,genres,tags">${esc(state.ratingsCsv)}</textarea><label>候选 CSV</label><textarea id="candidatesCsv" placeholder="title,media_type,douban_rating,genres,tags">${esc(state.candidatesCsv)}</textarea><button class="ghost" onclick="useCsvInputs()">使用 CSV 继续</button></details>
  <div class="quick-actions"><button onclick="syncDouban()">同步豆瓣</button><button class="ghost" onclick="continueWithoutSync()">继续用高质量片库生成推荐</button><button class="ghost" onclick="clearCache()">清空缓存</button></div><div id="status" class="hint"></div>`;
  hydrateCrawlerControls();
  renderCrawlSummary();
}
function renderSyncSuccess(recovery, counts={}) {
  const actions = (recovery.actions || ['继续确认口味','生成推荐']).map(x => `<div class="recovery-action"><b>完成路线</b>${esc(x)}</div>`).join('');
  return `<section class="sync-success-brief anti-overflow"><span class="badge">同步完成</span><h3>${esc(recovery.headline || '同步完成')}</h3><p class="sync-copy">空白分页是豆瓣列表的正常结束信号：系统已经抓到 ${esc(counts.collect_count ?? 0)} 部看过 / ${esc(counts.wish_count ?? 0)} 部想看，成功页 ${esc(counts.pages_ok ?? 0)}，失败页 ${esc(counts.pages_failed ?? 0)}。下一步可以直接确认口味并生成推荐。</p><div class="recovery-actions">${actions}</div><div class="quick-actions"><button onclick="renderTastePanel()">继续确认口味</button><button class="ghost" onclick="renderTastePanel(); setTimeout(() => recommend(), 0)">直接生成推荐</button></div></section>`;
}
function renderSyncRecovery(recovery) {
  if (!recovery || !recovery.status || recovery.status === 'idle') return '';
  if (recovery.status === 'ok' || recovery.status === 'complete') return renderSyncSuccess(recovery, state.counts || {});
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
  return `<div class="sync-command-center anti-overflow"><section class="sync-health"><div class="health-orb"><div><b>${esc(total)}</b><span>${esc(health)}</span></div></div><div><span class="badge">同步作战室</span><h2>同步诊断</h2><p class="sync-copy">目标是尽量拿到你的 242 部看过和 34 部想看；拿不到时不再只丢出 HTTP Error，而是拆解为登录态、权限、安全验证、解析结构和网络五类问题。</p><div class="metric-grid"><div class="metric"><b>${esc(collect)}</b>看过数量<div class="progress-meter"><span style="width:${Math.max(0, Math.min(100, collectPercent))}%"></span></div></div><div class="metric"><b>${esc(wish)}</b>想看数量<div class="progress-meter"><span style="width:${Math.max(0, Math.min(100, wishPercent))}%"></span></div></div><div class="metric"><b>${esc(c.pages_ok ?? 0)}</b>成功页</div><div class="metric"><b>${esc(c.pages_failed ?? 0)}</b>失败页</div></div></div></section>${renderUserInputInsight()}${renderSyncRecovery(recovery)}<div class="sync-playbook"><div class="playbook-card"><b>1. Cookie 解锁</b><span class="hint">登录豆瓣后复制请求 Cookie，只用于本机抓取。</span></div><div class="playbook-card"><b>2. 本地片库继续</b><span class="hint">不用等抓取成功，也能生成电影 / 电视剧 / 动漫推荐。</span></div><div class="playbook-card"><b>3. CSV 精准导入</b><span class="hint">如果你有导出的评分表，可直接粘贴保持最高完整度。</span></div></div><p class="hint">停止原因：${esc(c.stopped_reason || recovery.headline || '-')}</p>${errorSummary}<div id="syncTimeline" class="timeline diagnosis-grid">${diagnosis}</div></div>`;
}
function renderCrawlSummary() {
  const c = state.counts || {};
  const rows = (state.diagnostics || []).slice(0,12).map(d => `<div class="timeline-row diagnosis-card"><b>${esc(d.status)} start=${esc(d.start)}${d.http_status ? ' · HTTP ' + esc(d.http_status) : ''}</b><br>${esc(d.classification)} · ${esc(d.message)} · ${esc(d.item_count)} 条</div>`).join('');
  const errorSummary = (state.errors || []).length ? `<h3>错误摘要</h3><ul class="mini-list">${state.errors.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '';
  $('mainPanel').innerHTML = syncCommandCenter(c, rows, errorSummary);
}
function continueWithoutSync() { state.items = []; state.ratedItems = []; renderTastePanel(); setStatus('已进入本地高质量片库模式：电影 / 电视剧 / 动漫都会参与推荐。'); }
function tasteDNA() { const profile = state.profile || {}; const chips = []; (profile.top_genres || []).slice(0,5).forEach(([name, value]) => chips.push(`<div class="dna-chip"><b>${esc(name)}</b><span class="hint">偏好强度 ${esc(value)}</span></div>`)); (profile.top_directors || []).slice(0,3).forEach(([name]) => chips.push(`<div class="dna-chip"><b>${esc(name)}</b><span class="hint">导演偏好</span></div>`)); if (!chips.length) chips.push(`<div class="dna-chip"><b>剧情优先</b><span class="hint">默认按高分、叙事、人物塑造起步</span></div>`, `<div class="dna-chip"><b>剧集避雷</b><span class="hint">电视剧古装和注水剧强降权</span></div>`, `<div class="dna-chip"><b>动漫补齐</b><span class="hint">默认补足高分动漫剧集候选</span></div>`); return `<div class="taste-dna tasteDNA">${chips.join('')}</div>`; }
function renderTastePanel() {
  setStageLayout('flow');
  state.step = 2;
  renderStepNav();
  $('controlPanel').innerHTML = `<h2>第二步：确认口味</h2><div class="story-panel"><b>不要死板打标签</b><p class="hint">你可以什么都看，系统会把“高分 + 剧情好 + 叙事强 + 人物塑造”作为主轴，再把电视剧古装、注水和狗血当作软避雷。</p></div><label>一句话告诉我最近想看什么</label><textarea id="likeTerms">评分高，剧情好，叙事强，人物塑造扎实，电影/电视剧/动漫都可以</textarea><label>明确避雷</label><textarea id="dislikeTerms">电视剧古装，注水剧，低分狗血，粗制滥造</textarea><label><input id="includeMovies" type="checkbox" checked> 电影</label><label><input id="includeSeries" type="checkbox" checked> 电视剧</label><label><input id="includeAnime" type="checkbox" checked> 动漫</label><label><input id="fetchDouban" type="checkbox" checked> 从豆瓣探索候选池补充</label><label><input id="enrichDetails" type="checkbox" checked> 补全简介、海报和演职员</label><label>推荐数量</label><input id="limit" type="number" min="24" max="300" value="160"><div class="quick-actions"><button onclick="recommend()">生成推荐</button><button class="ghost" onclick="renderCrawlerPanel()">返回同步</button></div><div id="status" class="hint"></div>`;
  $('mainPanel').innerHTML = `<h2>你的资料库</h2><div class="metric-grid"><div class="metric"><b>${state.items.length || state.ratedItems.length || 0}</b>条目</div><div class="metric"><b>${esc((state.sections || []).length)}</b>推荐分区</div><div class="metric"><b>${esc(state.lastCounts.curated_candidates ?? 0)}</b>本地精选补齐</div><div class="metric"><b>3</b>电影 / 剧集 / 动漫</div></div><h3>口味 DNA</h3>${tasteDNA()}<p class="hint">系统会用高分条目学习偏好，用低分条目学习避雷，并自动排除已经看过的条目。想看条目会作为想看优先提示。</p>${renderPosterSourcePanel(false)}`;
  hydratePosterSourceControls();
}
function recTitle(r) { return r.title || r.item?.title || 'CineScope'; }
function recType(r) { return r.media_type || r.item?.media_type || ''; }
function recArray(r, key) { return Array.isArray(r[key]) ? r[key] : (Array.isArray(r.item?.[key]) ? r.item[key] : []); }
function itemKey(r) { return String(r.douban_id || r.item?.douban_id || recTitle(r)); }
function proxiedImageUrl(raw) { return /^https?:\/\//.test(raw || '') ? `/api/image-proxy?url=${encodeURIComponent(raw)}` : (raw || ''); }
function isSyntheticPremiumId(id) { id = String(id || ''); return id.startsWith('premium-'); }
function isDoubanCdnPosterRaw(raw) { return /doubanio\.com\/view\/photo|img\.doubanio\.com/i.test(String(raw || '')); }
function isDoubanCdnPoster(r) { return isDoubanCdnPosterRaw(r.cover || r.item?.cover || ''); }
function hasPotentiallyMismatchedPoster(r, raw) { const id = String(r.douban_id || r.item?.douban_id || '').trim(); return isSyntheticPremiumId(id) && /doubanio\.com\/view\/photo/.test(raw || ''); }
function canonicalPosterRawFor(r) { const id = String(r.douban_id || r.item?.douban_id || '').trim(); const title = recTitle(r); return canonicalPosterMap[id] || canonicalPosterByTitle[title] || ''; }
function canonicalPosterFor(r) { return proxiedImageUrl(canonicalPosterRawFor(r)); }
function hasCanonicalPoster(r) { return Boolean(canonicalPosterRawFor(r)); }
const knownBrokenPosterUrls = new Set([
  'https://media.themoviedb.org/t/p/w500/lYpHeSm7BcUxAbBx1ucuEH7oGAe.jpg',
]);
function imageHost(raw) { try { return new URL(raw).hostname.toLowerCase(); } catch (_) { return ''; } }
function isLikelyStaleExternalPoster(raw, canonicalRaw) {
  raw = String(raw || '').trim();
  canonicalRaw = String(canonicalRaw || '').trim();
  if (!raw || !canonicalRaw || raw === canonicalRaw) return false;
  if (knownBrokenPosterUrls.has(raw)) return true;
  const rawHost = imageHost(raw);
  const canonicalHost = imageHost(canonicalRaw);
  const rawExternal = /(?:themoviedb\.org|image\.tmdb\.org|m\.media-amazon\.com|cdn\.myanimelist\.net|s4\.anilist\.co)$/i.test(rawHost);
  const canonicalTrusted = /(?:doubanio\.com|img\d*\.doubanio\.com)$/i.test(canonicalHost);
  return Boolean(rawExternal && canonicalTrusted);
}
function posterUrl(r) { const raw = r.cover || r.item?.cover || ''; if (hasPotentiallyMismatchedPoster(r, raw)) return ''; // stale premium poster can belong to another title
 return proxiedImageUrl(raw); }
function displayPosterUrl(r) { const raw = r.cover || r.item?.cover || ''; const canonicalRaw = canonicalPosterRawFor(r); const canonical = proxiedImageUrl(canonicalRaw); if ((isDesignedPoster(r) || isDoubanCdnPosterRaw(raw) || hasPotentiallyMismatchedPoster(r, raw) || (canonicalRaw && isLikelyStaleExternalPoster(raw, canonicalRaw))) && canonical) return canonical; return posterUrl(r) || canonical; }
function isDesignedPoster(r) { const raw = String(r.cover || r.item?.cover || ''); return raw.startsWith('data:image/svg+xml'); }
function designedPosterCount(rows = state.recommendations || []) { return (rows || []).filter(r => isDesignedPoster(r) && !hasCanonicalPoster(r)).length; }
function needsPosterRescue(r) { const id = String(r.douban_id || r.item?.douban_id || '').trim(); const raw = r.cover || r.item?.cover || ''; if (isDoubanCdnPosterRaw(raw) && hasCanonicalPoster(r)) return false; return (isDesignedPoster(r) || id.startsWith('premium-') || isDoubanCdnPosterRaw(raw)) && !hasCanonicalPoster(r); }
function posterRescueCount(rows = state.recommendations || []) { return (rows || []).filter(needsPosterRescue).length; }
function externalPosterCount(rows = state.recommendations || []) { return (rows || []).filter(r => hasCanonicalPoster(r) || (!isDesignedPoster(r) && !isDoubanCdnPoster(r))).length; }
function missingPosterRows() { return (state.recommendations || []).filter(needsPosterRescue); }
function missingPosterSearchLinks(r) { const title = recTitle(r); const q = encodeURIComponent(title); const anime = recType(r) === '动漫'; const links = [`<a href="https://www.themoviedb.org/search?query=${q}" target="_blank" rel="noreferrer">TMDb</a>`, `<a href="https://www.imdb.com/find/?q=${q}" target="_blank" rel="noreferrer">IMDb</a>`]; if (recType(r) === '电视剧') links.push(`<a href="https://www.tvmaze.com/search?q=${q}" target="_blank" rel="noreferrer">TVMaze</a>`); if (anime) links.unshift(`<a href="https://anilist.co/search/anime?search=${q}" target="_blank" rel="noreferrer">AniList</a>`, `<a href="https://myanimelist.net/anime.php?q=${q}" target="_blank" rel="noreferrer">MyAnimeList</a>`); return `<div class="source-link-strip">${links.join('')}</div>`; }
function copyMissingPosterTitles() { const rows = missingPosterRows(); const text = rows.map(r => `${recTitle(r)}\\t${recType(r)}\\t${r.douban_rating || r.item?.douban_rating || ''}`).join('\\n'); navigator.clipboard?.writeText(text); setStatus(`已复制 ${rows.length} 个缺图标题，可去 TMDb / IMDb / TVMaze / AniList 手动搜索。`); }
function exportMissingPosterCsv() { const rows = missingPosterRows(); const csv = ['title,media_type,douban_rating,url'].concat(rows.map(r => [recTitle(r), recType(r), r.douban_rating || r.item?.douban_rating || '', r.url || r.item?.url || ''].map(v => `"${String(v).replace(/"/g,'""')}"`).join(','))).join('\\n'); const blob = new Blob([csv], {type:'text/csv;charset=utf-8'}); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'cinescope-missing-posters.csv'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000); setStatus(`已导出 ${rows.length} 个缺图条目。`); }
function renderPosterRecoveryCenter() { const rows = missingPosterRows(); if (!rows.length) return `<section class="poster-recovery-center"><span class="badge real-poster">缺图补救台</span><b>当前片单没有待换源海报</b><span class="hint">TMDb / OMDb / IMDb / TVMaze / AniList / Jikan 多源已覆盖当前结果。</span></section>`; const list = rows.slice(0,10).map(r => `<div class="missing-poster-row"><b>${esc(recTitle(r))}</b><span class="hint">${esc(recType(r) || '媒体')} · ${isDoubanCdnPoster(r) ? '豆瓣 CDN 待替换' : '设计封面待替换'}</span>${missingPosterSearchLinks(r)}</div>`).join(''); const more = rows.length > 10 ? `<span class="hint">还有 ${rows.length - 10} 个，先复制标题或导出 CSV 批量处理。</span>` : ''; return `<section class="poster-recovery-center"><span class="badge designed-cover">缺图补救台</span><h3>${rows.length} 个海报还在等待换源</h3><p class="hint">自动源会继续尝试；如果你愿意注册免费 API Key，优先填 TMDb。电视剧和动漫剧集不用 Key，已接入 TVMaze、AniList 与 Jikan / MyAnimeList。</p><div class="quick-actions"><button class="ghost" onclick="rescuePosterImages(true)">再次多源搜索</button><button class="ghost" onclick="copyMissingPosterTitles()">复制缺图标题</button><button class="ghost" onclick="exportMissingPosterCsv()">导出 CSV</button></div><div class="missing-poster-list">${list}</div>${more}</section>`; }
function posterSourceBadge(r) { const raw = String(r.cover || r.item?.cover || ''); const displayRaw = canonicalPosterRawFor(r) || raw; if (isDoubanCdnPosterRaw(raw) && hasCanonicalPoster(r)) return '<span class="badge real-poster">内置真实海报 · 已绕过豆瓣 CDN</span>'; if (isDesignedPoster(r) && hasCanonicalPoster(r)) return '<span class="badge real-poster">内置真实海报 · 已替换设计封面</span>'; if (isDesignedPoster(r)) return '<span class="badge designed-cover">设计封面 · 暂无精确海报</span>'; if (isDoubanCdnPosterRaw(raw)) return '<span class="badge designed-cover">豆瓣 CDN · 待换源</span>'; if (/s4\.anilist\.co|anilistcdn|anilist\.co/i.test(displayRaw)) return '<span class="badge real-poster">AniList 动漫海报</span>'; if (/cdn\.myanimelist\.net|myanimelist\.net|jikan/i.test(displayRaw)) return '<span class="badge real-poster">MyAnimeList 动漫海报</span>'; if (/static\.tvmaze\.com|tvmaze\.com/i.test(displayRaw)) return '<span class="badge real-poster">TVMaze 剧集海报</span>'; if (/m\.media-amazon\.com|imdb/i.test(displayRaw)) return '<span class="badge real-poster">OMDb / IMDb 海报</span>'; if (/themoviedb|image\.tmdb\.org/i.test(displayRaw)) return '<span class="badge real-poster">TMDb 真实海报</span>'; return '<span class="badge real-poster">真实海报</span>'; }
function posterFallback(title, mediaType) { const safeTitle = esc(title || 'CineScope'); const safeType = esc(mediaType || '私人推荐'); const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="960" viewBox="0 0 640 960"><defs><linearGradient id="g" x1="0" x2="1" y1="0" y2="1"><stop stop-color="#1E293B"/><stop offset="0.52" stop-color="#312E81"/><stop offset="1" stop-color="#0F172A"/></linearGradient><radialGradient id="r" cx="30%" cy="10%" r="70%"><stop stop-color="#F5C451" stop-opacity=".55"/><stop offset="1" stop-color="#F5C451" stop-opacity="0"/></radialGradient></defs><rect width="640" height="960" fill="url(#g)"/><rect width="640" height="960" fill="url(#r)"/><text x="52" y="120" fill="#F5C451" font-size="28" font-family="Arial" font-weight="800" letter-spacing="5">${safeType}</text><foreignObject x="52" y="230" width="536" height="430"><div xmlns="http://www.w3.org/1999/xhtml" style="font-family:Arial,Microsoft YaHei,sans-serif;color:#F8FAFC;font-size:74px;font-weight:950;line-height:1.06;letter-spacing:-3px;">${safeTitle}</div></foreignObject><text x="52" y="850" fill="#A7B0C0" font-size="24" font-family="Arial">CineScope Studio</text></svg>`; return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`; }
function handlePosterImageError(img) { const fallback = img?.dataset?.fallback || ''; if (img) { img.onerror = null; img.classList.add('poster-load-failed'); if (fallback) img.src = fallback; } if (!state.posterRescueInFlight && state.posterRescueVersion < POSTER_RESCUE_VERSION && posterRescueCount(state.recommendations)) setTimeout(() => rescuePosterImages(false), 250); }
function safePosterImg(r) { const title = recTitle(r); const type = recType(r); const fallback = posterFallback(title, type); const safeFallback = fallback.replace(/'/g, '%27'); const rawSrc = displayPosterUrl(r) || safeFallback; const src = rawSrc === fallback ? safeFallback : rawSrc; return `<img src="${esc(src)}" data-fallback="${safeFallback}" alt="${esc(title)}" referrerpolicy="no-referrer" onerror="handlePosterImageError(this)">`; }
function posterHtml(r) { return safePosterImg(r); }
function metadataLine(r) { const parts = []; if (r.year || r.item?.year) parts.push(r.year || r.item.year); if (recType(r)) parts.push(recType(r)); recArray(r,'genres').slice(0,3).forEach(x => parts.push(x)); recArray(r,'countries').slice(0,2).forEach(x => parts.push(x)); return parts.map(esc).join(' · ') || '类型信息待补全'; }
function canonicalPeoplePhotosFor(r) { const id = String(r?.douban_id || r?.item?.douban_id || '').trim(); return (id && canonicalPeoplePhotoMap[id]) ? canonicalPeoplePhotoMap[id] : {}; }
function canonicalPeoplePhotoForName(name, role='') { return canonicalPeoplePhotoByName[name] || canonicalPeoplePhotoByName[`${role}:${name}`] || ''; }
function peoplePhotoMap(r) { return { ...canonicalPeoplePhotosFor(r), ...canonicalPeoplePhotoByName, ...(r?.item?.raw?.people_photos || {}), ...(r?.raw?.people_photos || {}), ...(r?.item?.people_photos || {}), ...(r?.people_photos || {}) }; }
function visiblePeoplePhotoPayload(r) { const all = peoplePhotoMap(r); const names = new Set(peopleForItem(r).map(person => person.name)); const out = {}; names.forEach(name => { const url = all[name] || all[`导演:${name}`] || all[`主演:${name}`]; if (url) out[name] = url; }); return out; }
function personPhotoSvg(name, role) { const initials = esc(String(name || '?').trim().slice(0,2).toUpperCase()); const safeName = esc(name || '人物肖像'); const safeRole = esc(role || '演职员'); const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="360" height="420" viewBox="0 0 360 420"><defs><linearGradient id="g" x1="0" x2="1" y1="0" y2="1"><stop stop-color="#F5C451"/><stop offset=".48" stop-color="#60A5FA"/><stop offset="1" stop-color="#312E81"/></linearGradient><radialGradient id="r" cx="30%" cy="15%" r="75%"><stop stop-color="#fff" stop-opacity=".35"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient></defs><rect width="360" height="420" rx="34" fill="#0B1020"/><rect width="360" height="420" rx="34" fill="url(#g)" opacity=".82"/><rect width="360" height="420" rx="34" fill="url(#r)"/><circle cx="180" cy="150" r="64" fill="rgba(11,16,32,.72)"/><path d="M76 344c14-72 68-112 104-112s90 40 104 112" fill="rgba(11,16,32,.72)"/><text x="180" y="164" text-anchor="middle" fill="#F8FAFC" font-size="44" font-family="Arial,Microsoft YaHei,sans-serif" font-weight="900">${initials}</text><text x="28" y="56" fill="#0B1020" font-size="22" font-family="Arial,Microsoft YaHei,sans-serif" font-weight="900">${safeRole}</text><text x="28" y="386" fill="#F8FAFC" font-size="24" font-family="Arial,Microsoft YaHei,sans-serif" font-weight="800">${safeName}</text></svg>`; return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg).replace(/'/g, '%27')}`; }
function personPhotoUrl(person) { const raw = person.photo || ''; return proxiedImageUrl(raw); }
function isCuratedPlaceholderPerson(name) { return curatedPlaceholderPeople.has(String(name || '').trim()); }
function personPortraitStatus(person) { if (person.photo) return '真实资料图'; return person.placeholder ? '策展占位肖像' : '设计肖像'; }
function personPortrait(person) { const fallback = personPhotoSvg(person.name, person.role); const src = personPhotoUrl(person) || fallback; const safeFallback = fallback.replace(/'/g, '%27'); const cls = person.photo ? 'person-photo' : 'person-photo portrait-fallback'; return `<span class="${cls}" title="${esc(person.role)}人物肖像" data-status="${personPortraitStatus(person)}"><img src="${esc(src)}" alt="${esc(person.name)} 人物肖像" referrerpolicy="no-referrer" onerror="this.onerror=null;this.src='${safeFallback}'"><small class="portrait-source">人物图源 · ${personPortraitStatus(person)}</small></span>`; }
function peopleForItem(r) { const photos = peoplePhotoMap(r); const photoFor = (name, role) => photos[name] || photos[`${role}:${name}`] || photos[`导演:${name}`] || photos[`主演:${name}`] || canonicalPeoplePhotoForName(name, role) || ''; const people = []; recArray(r,'directors').slice(0,4).forEach(name => people.push({name, role:'导演', photo:photoFor(name,'导演'), placeholder:isCuratedPlaceholderPerson(name)})); recArray(r,'casts').slice(0,8).forEach(name => people.push({name, role:'主演', photo:photoFor(name,'主演'), placeholder:isCuratedPlaceholderPerson(name)})); return people; }
function peoplePhotoCountFor(r) { return peopleForItem(r).filter(person => person.photo).length; }
function needsPeopleIdentityEnrichment(r) { const people = peopleForItem(r); const id = String(r.douban_id || r.item?.douban_id || ''); const url = String(r.url || r.item?.url || ''); return people.some(person => person.placeholder) || isSyntheticPremiumId(id) || /subject_search/i.test(url); }
function needsPeoplePhotoEnrichment(r) { const key = itemKey(r); if (!key || state.peopleEnrichmentStatus[key]) return false; const people = peopleForItem(r); if (!people.length && !needsPeopleIdentityEnrichment(r)) return false; return needsPeopleIdentityEnrichment(r) || peoplePhotoCountFor(r) < Math.min(people.length, 4); }
function peopleEnrichmentBanner(r) { const key = itemKey(r); const identityNeeded = needsPeopleIdentityEnrichment(r); const status = state.peopleEnrichmentStatus[key] || (needsPeoplePhotoEnrichment(r) ? 'ready' : 'done'); const count = peoplePhotoCountFor(r); const total = peopleForItem(r).length; const title = identityNeeded ? '人物身份待绑定' : '人物图库补全'; if (status === 'done' && count >= Math.min(total, 4) && !identityNeeded) return `<div class="people-photo-enriching"><b>人物图库补全</b><span class="hint">已命中 ${count} 张导演 / 演员资料图。人物详情补图会复用本次会话 Cookie。</span></div>`; const loading = status === 'loading'; const readyHint = identityNeeded ? '当前是策展占位人物，系统会先绑定真实演职员，再补导演 / 演员资料图；绑定前会显示策展占位肖像。' : `已命中 ${count}/${total} 张，可继续自动补图；人物详情补图会复用本次会话 Cookie。`; return `<div id="peopleEnrichmentBanner" class="people-photo-enriching ${loading ? 'loading' : ''}"><b>${title}</b><span class="hint">${loading ? '正在从豆瓣详情页绑定真实演职员与人物图像。' : readyHint}</span><button class="ghost" onclick="enrichPeopleForDetail('${encodeURIComponent(key)}')">${loading ? '补图中' : (identityNeeded ? '绑定真实演职员' : '立即补图')}</button></div>`; }
function peopleCookieForRequest() { const remembered = normalizeCookieInput(sessionStorage.getItem(COOKIE_SESSION_KEY) || ''); return normalizeCookieInput($('doubanCookie')?.value || remembered); }
function recommendationPeoplePayload(r) { return { title:recTitle(r), year:r.year || r.item?.year || null, media_type:recType(r), douban_rating:r.douban_rating || r.item?.douban_rating || null, vote_count:r.vote_count || r.item?.vote_count || null, genres:recArray(r,'genres'), countries:recArray(r,'countries'), languages:recArray(r,'languages'), directors:recArray(r,'directors'), casts:recArray(r,'casts'), tags:recArray(r,'tags'), url:r.url || r.item?.url || '', douban_id:r.douban_id || r.item?.douban_id || '', cover:r.cover || r.item?.cover || '', summary:r.summary || r.item?.summary || '', source:r.source || r.item?.source || '', people_photos:visiblePeoplePhotoPayload(r), needs_identity_resolution:needsPeopleIdentityEnrichment(r) }; }
function mergePeopleEnrichment(enriched) { if (!enriched) return; const key = String(enriched.douban_id || enriched.title || ''); const photos = enriched.people_photos || {}; const apply = row => { const sameId = enriched.douban_id && String(row.douban_id || row.item?.douban_id || '') === String(enriched.douban_id); const sameTitle = recTitle(row) === enriched.title; if (!sameId && !sameTitle && itemKey(row) !== key) return row; ['summary','url','cover','source','year','douban_rating','vote_count'].forEach(field => { if (enriched[field]) row[field] = enriched[field]; }); ['directors','casts','genres','countries','languages','tags'].forEach(field => { if (Array.isArray(enriched[field]) && enriched[field].length) row[field] = enriched[field]; }); row.people_photos = {...(row.people_photos || {}), ...photos}; return row; }; state.recommendations = (state.recommendations || []).map(apply); state.visibleRecommendations = (state.visibleRecommendations || []).map(apply); state.sections = (state.sections || []).map(section => ({...section, items:(section.items || []).map(apply)})); }
async function enrichPeopleForDetail(encodedKey) { const key = decodeURIComponent(encodedKey || ''); const row = [...(state.recommendations || []), ...(state.visibleRecommendations || [])].find(item => itemKey(item) === key); if (!row || state.peopleEnrichmentStatus[key] === 'loading') return; state.peopleEnrichmentStatus[key] = 'loading'; const banner = $('peopleEnrichmentBanner'); if (banner) { banner.classList.add('loading'); banner.querySelector('.hint').textContent = '正在从豆瓣详情页绑定真实演职员与人物图像。'; } try { const res = await fetch('/api/enrich-people', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ item:recommendationPeoplePayload(row), cookie:peopleCookieForRequest() }) }); const data = await res.json(); if (!res.ok || data.error) throw new Error(data.error || '人物图库补全失败'); mergePeopleEnrichment(data.item); state.peopleEnrichmentStatus[key] = 'done'; persistRecommendationSnapshot(); if ($('detailDrawer')?.classList.contains('open')) { const refreshed = [...(state.recommendations || []), ...(state.visibleRecommendations || [])].find(item => itemKey(item) === key || recTitle(item) === recTitle(row) || (data.item?.douban_id && String(item.douban_id || item.item?.douban_id || '') === String(data.item.douban_id))); if (refreshed) openDetailObject(refreshed); else openDetailObject(data.item); } } catch (error) { state.peopleEnrichmentStatus[key] = 'failed'; setStatus('人物图库补全失败：' + (error?.message || String(error))); if (banner) { banner.classList.remove('loading'); banner.querySelector('.hint').textContent = '人物图库补全暂未完成，仍使用设计肖像兜底。'; } } }
function peopleChips(names, role, r=null) { const list = (names || []).slice(0,8); if (!list.length) return `<p class="hint">${role}资料待补全</p>`; const photos = peoplePhotoMap(r || {}); return list.map(name => { const person = {name, role, photo:photos[name] || photos[`${role}:${name}`] || canonicalPeoplePhotoForName(name, role) || '', placeholder:isCuratedPlaceholderPerson(name)}; const encoded = encodeURIComponent(name || ''); return `<button class="person-chip magnetic-person" onclick="openPersonSpotlight('${encoded}','${encodeURIComponent(role)}')">${personPortrait(person)}<span><b>${esc(name)}</b><small class="hint"> · ${esc(role)}</small></span></button>`; }).join(''); }
function peopleCarousel(r) { const people = peopleForItem(r); if (!people.length) return `<p class="hint">人物资料待补全。</p>`; return `<div class="people-carousel people-spotlight-rail">${people.map(person => { const encoded = encodeURIComponent(person.name || ''); const encodedRole = encodeURIComponent(person.role || ''); return `<button class="person-card magnetic-person" onclick="openPersonSpotlight('${encoded}','${encodedRole}')">${personPortrait(person)}<b>${esc(person.name)}</b><small>${esc(person.role)} · 点击查看 TA 参与的相关推荐</small></button>`; }).join('')}</div>`; }
function openPersonSpotlight(encodedName, encodedRole='') { const name = decodeURIComponent(encodedName || ''); const role = decodeURIComponent(encodedRole || '演职员'); if (!name) return; const matched = (state.recommendations || []).filter(item => recArray(item,'directors').includes(name) || recArray(item,'casts').includes(name)); const modal = document.createElement('section'); modal.className = 'spotlight-modal'; modal.innerHTML = `<button class="ghost" style="float:right" onclick="this.closest('.spotlight-modal')?.remove()">关闭</button><h3>${esc(name)}</h3><p class="hint">${esc(role)} · ${matched.length ? `在当前推荐里关联 ${matched.length} 部作品` : '当前作品人物；可继续通过同导演 / 同主演区域探索相近作品。'}</p><div class="quick-actions"><button onclick="filterByPerson('${encodeURIComponent(name)}')">只看 TA 的作品</button><button class="ghost" onclick="this.closest('.spotlight-modal')?.remove()">留在详情页</button></div>`; document.body.querySelectorAll('.spotlight-modal').forEach(x => x.remove()); document.body.appendChild(modal); }
function filterByPerson(encodedName) { const name = decodeURIComponent(encodedName || ''); if (!name) return; const matched = (state.recommendations || []).filter(item => recArray(item,'directors').includes(name) || recArray(item,'casts').includes(name)); if (!matched.length) return; const sectionName = `人物：${name}`; state.sections = [{name:sectionName, count:matched.length, items:matched}, ...(state.sections || []).filter(s => s.name !== sectionName)]; state.activeSection = sectionName; closeDetailDrawer(); persistRecommendationSnapshot(); renderRecommendations(); }
function animeSubchannelFor(r) { const countries = recArray(r,'countries'); if (countries.some(x => ['中国大陆','中国','中国香港','中国台湾'].includes(x))) return '动漫 · 国创动画'; if (countries.some(x => ['美国','英国','法国','加拿大','爱尔兰','西班牙'].includes(x))) return '动漫 · 欧美动画'; if (countries.includes('日本')) return '动漫 · 日漫精品'; return ''; }
function sectionItems(name) { const all = state.recommendations || []; if (name === '全部') return all; if (name === '精选') return all.slice(0,24); if (['电影','电视剧','动漫'].includes(name)) return all.filter(r => recType(r) === name); if (GLOBAL_ANIME_CHANNELS.includes(name)) return all.filter(r => recType(r) === '动漫' && animeSubchannelFor(r) === name); const found = (state.sections || []).find(s => s.name === name); return found?.items || []; }
function buildMediaRails() { const names = ['精选','电影','电视剧','动漫',...GLOBAL_ANIME_CHANNELS,'必看 Top Picks','高分剧情','想看优先']; const rails = []; const seen = new Set(); for (const name of names) { const items = sectionItems(name); if (items.length && !seen.has(name)) { rails.push({ name, items }); seen.add(name); } } for (const section of state.sections || []) { if (!seen.has(section.name) && section.items?.length) rails.push({ name:section.name, items:section.items }); } return rails; }
function renderGlobalAnimeChannels() { const total = sectionItems('动漫').length; if (!total) return ''; const buttons = GLOBAL_ANIME_CHANNELS.map(name => { const count = sectionItems(name).length; return `<button class="${state.activeSection === name ? '' : 'ghost'}" onclick="selectSection('${esc(name)}')">${esc(name)} · ${count}</button>`; }).join(''); return `<section class="anime-channel-strip"><span class="badge">全球动画剧集</span><span class="hint">国创 / 欧美 / 日漫分频道，避免动漫推荐只剩单一地区。</span>${buttons}</section>`; }
function gridBaseLimit(name) { return name === '全部' ? 48 : 36; }

function activeBatchOffset(name, total) { const raw = Number(state.batchOffsetBySection?.[name] || 0); return total ? ((raw % total) + total) % total : 0; }
function visibleBatchItems(items, name, limit) { const total = items.length; if (!total || limit >= total) return items.slice(0, limit); const offset = activeBatchOffset(name, total); const doubled = items.concat(items); return doubled.slice(offset, offset + limit); }
function shuffleSectionBatch(name) { const items = sectionItems(name); if (!items.length) return; const step = Math.max(12, Math.min(48, activeGridLimit(name, items.length))); const current = activeBatchOffset(name, items.length); state.batchOffsetBySection[name] = (current + step) % items.length; state.heroBySection[name] = state.batchOffsetBySection[name]; persistRecommendationSnapshot(); renderRecommendations(); setStatus(`${name} ??????? ${state.batchOffsetBySection[name] + 1} ????????`); requestAnimationFrame(() => scrollToResults('railWall')); }
function activeGridLimit(name, total) { const remembered = state.gridLimitBySection?.[name]; return Math.min(total, Math.max(0, remembered || gridBaseLimit(name))); }
function showMoreRecommendations(name, amount=48) { const total = sectionItems(name).length; state.gridLimitBySection[name] = Math.min(total, activeGridLimit(name, total) + amount); persistRecommendationSnapshot(); renderRecommendations(); setTimeout(() => scrollToResults('railWall'), 0); }
function showAllRecommendations(name) { state.gridLimitBySection[name] = sectionItems(name).length; persistRecommendationSnapshot(); renderRecommendations(); setTimeout(() => scrollToResults('railWall'), 0); }
function mediaCard(r, index) { const key = encodeURIComponent(itemKey(r)); const coverClass = isDesignedPoster(r) ? 'designed-cover' : 'real-poster'; return `<article class="poster-card compact-poster-card cinema-tile poster-lift ${coverClass}" tabindex="0" onclick="openDetailByKey('${key}')"><div class="poster">${safePosterImg(r)}</div><div class="poster-source-layer">${posterSourceBadge(r)}</div><div class="poster-body poster-body-overlay"><span class="badge">${esc(recType(r) || '媒体')}</span><span class="badge">豆瓣 ${esc(r.douban_rating || r.item?.douban_rating || '-')}</span><h3>${esc(recTitle(r))}</h3><div class="meta-line">${metadataLine(r)}</div><p class="micro-copy">${esc(r.summary || r.item?.summary || r.short_reason || (r.reasons || [])[0] || '质量优先策略推荐')}</p><button class="poster-quicklook" onclick="event.stopPropagation();openDetailByKey('${key}')">展开详情</button></div></article>`; }
function selectSection(name) { state.activeSection = name; persistRecommendationSnapshot(); renderRecommendations(); setTimeout(() => scrollToResults('heroShowcase'), 0); }
function renderMediaRail(name, items) { return `<section class="media-rail"><div class="rail-head"><div class="rail-title">${esc(name)}</div><button class="ghost" onclick="selectSection('${esc(name)}')">查看全部</button></div><div class="rail-strip">${items.map(mediaCard).join('')}</div></section>`; }
function spotlightPool(name) { const scoped = sectionItems(name || state.activeSection); if (scoped.length) return scoped; const featured = sectionItems('精选'); return featured.length ? featured : (state.recommendations || []); }
function heroIndexFor(name, total) { const raw = state.heroBySection[name] ?? state.heroIndex ?? 0; return total ? Math.abs(raw) % total : 0; }
function setHeroForSection(name, index) { state.heroBySection[name] = index; persistRecommendationSnapshot(); renderRecommendations(); }
function nextHeroForSection(name, delta) { const rows = spotlightPool(name); const current = heroIndexFor(name, rows.length); setHeroForSection(name, current + delta + rows.length); }
function categorySpotlight(name) { return renderHeroCarousel(name); }
function renderHeroCarousel(name = state.activeSection) {
  const rows = spotlightPool(name).slice(0,10);
  if (!rows.length) return '';
  const idx = heroIndexFor(name, rows.length);
  const r = rows[idx];
  const directors = recArray(r,'directors').slice(0,2).join('、');
  const casts = recArray(r,'casts').slice(0,4).join('、');
  const key = encodeURIComponent(itemKey(r));
  const encodedName = encodeURIComponent(name || '全部');
  const changeScript = i => `setHeroForSection(decodeURIComponent('${encodedName}'),${i});document.getElementById('heroShowcase')?.scrollIntoView({behavior:'smooth',block:'nearest'})`;
  const dots = rows.map((item,i) => `<button class="hero-dot hero-thumb ${i===idx ? 'active' : ''}" data-hero-index="${i}" aria-pressed="${i===idx ? 'true' : 'false'}" aria-label="切换到 ${esc(recTitle(item))}" onclick="${changeScript(i)}"><span>${safePosterImg(item)}</span><span class="hero-dot-title">${esc(recTitle(item))}</span></button>`).join('');
  const progress = `<div class="hero-progress" aria-hidden="true"><span style="width:${Math.round(((idx + 1) / rows.length) * 100)}%"></span></div>`;
  const reason = r.summary || r.short_reason || (r.reasons || [])[0] || '根据你的高分偏好、剧情完成度与多样性策略精选。';
  const creditLine = `${directors ? '导演：' + esc(directors) : ''}${casts ? (directors ? ' · ' : '') + '主演：' + esc(casts) : ''}`;
  return `<section class="hero-showcase cinematic-banner category-spotlight" id="heroShowcase">
    <div class="banner-backdrop">${safePosterImg(r)}</div>
    <div class="spotlight-lens" aria-hidden="true"></div>
    <div class="banner-content">
      <div class="banner-copy">
        <span class="badge">${esc(name)}焦点 · 今日最值得看</span>
        <h2>${esc(recTitle(r))}</h2>
        <div class="meta-line">${metadataLine(r)} · 豆瓣 ${esc(r.douban_rating || '-')}</div>
        <p class="hero-copy">${esc(reason)}</p>
        <p class="banner-credits">${creditLine || '演职员资料同步中 · 先按剧情与口碑质量入选'}</p>
      </div>
      <div class="banner-poster-float">${safePosterImg(r)}</div>
    </div>
    <div class="banner-filmstrip hero-dots">${dots}</div>
    <div class="banner-controls">
      ${progress}
      <div class="quick-actions"><button class="ghost" onclick="nextHeroForSection(decodeURIComponent('${encodedName}'),-1)">上一部</button><button onclick="openDetailByKey('${key}')">打开详情</button><button class="ghost" onclick="nextHeroForSection(decodeURIComponent('${encodedName}'),1)">下一部</button></div>
    </div>
  </section>`;
}
function renderHeroShowcase() { return renderHeroCarousel(state.activeSection); }
function renderResultCompass(sectionNames, total, visibleCount) { const active = state.activeSection; const progress = total ? Math.round((visibleCount / total) * 100) : 0; const map = sectionNames.map(name => { const count = sectionItems(name).length; return `<button class="section-mini ${active === name ? 'active' : ''}" onclick="selectSection('${esc(name)}');scrollToResults('heroShowcase')"><span>${esc(name)}</span><b>${count}</b></button>`; }).join(''); return `<section class="result-compass"><div class="compass-head"><span class="badge">片单遥控器</span><b>${esc(active)}</b></div><div class="result-progress" aria-label="当前分类显示进度"><span style="width:${progress}%"></span></div><p class="hint">当前显示 ${visibleCount} / ${total} 部；先给你一面高密度海报墙，后续用“再展开”逐段增加，不会一次铺成长页面。</p><div class="section-mini-map">${map}</div><div class="quick-actions"><button class="ghost" onclick="scrollToResults('heroShowcase')">回到焦点</button><button class="ghost" onclick="scrollToResults('railWall')">回到海报墙</button></div></section>`; }
function posterMergeKey(r) { return `${recTitle(r)}::${recType(r) || ''}`; }
function mergePosterRescueItems(items) {
  const repaired = new Map((items || []).map(item => [posterMergeKey(item), item]));
  const apply = row => {
    const next = repaired.get(posterMergeKey(row));
    if (!next) return row;
    ['cover','douban_id','url','year','source'].forEach(key => { if (next[key]) row[key] = next[key]; });
    if (next.item && typeof next.item === 'object') {
      row.item = row.item || {};
      ['cover','douban_id','url','year','source'].forEach(key => { if (next.item[key]) row.item[key] = next.item[key]; });
    }
    return row;
  };
  state.recommendations = (state.recommendations || []).map(apply);
  state.sections = (state.sections || []).map(section => ({...section, items:(section.items || []).map(apply)}));
}
function posterJobDockHtml() {
  const job = state.posterJob;
  if (!job) return '';
  const total = Math.max(1, Number(job.total || 0));
  const done = Math.min(total, Number(job.done || 0));
  const width = Math.max(4, Math.round(done / total * 100));
  const phase = job.state === 'done' ? '海报换源完成' : done ? `正在修复第 ${Math.min(total, done + 1)} / ${total} 部` : '正在建立多源任务';
  const sourceCopy = job.current_source || 'TMDb / OMDb / IMDb / TVMaze / AniList / Jikan';
  const latestEvents = (job.events || []).slice(-10).reverse();
  const events = latestEvents.map(event => `<div class="job-event"><b>${esc(event.title || '海报任务')}</b><span>${esc(event.status === 'found' ? '命中' : '继续搜索')} · ${esc(event.source || '多源轮询')}</span></div>`).join('');
  const sourceNames = ['TMDb API','OMDb / IMDb','TVMaze 剧集','AniList','Jikan / MyAnimeList','TMDb 公共页','Wikipedia','豆瓣精确搜索'];
  const laneHtml = sourceNames.map(name => { const matched = latestEvents.find(event => String(event.source || '').toLowerCase().includes(name.split(' ')[0].toLowerCase()) || (name.includes('IMDb') && /omdb|imdb/i.test(event.source || '')) || (name.includes('TVMaze') && /tvmaze/i.test(event.source || '')) || (name.includes('Jikan') && /jikan|myanimelist/i.test(event.source || ''))); const active = sourceCopy && ((name.includes('TVMaze') && /tvmaze/i.test(sourceCopy)) || name.toLowerCase().includes(String(sourceCopy).split('_')[0].toLowerCase()) || String(sourceCopy).toLowerCase().includes(name.split(' ')[0].toLowerCase())); const cls = matched?.status === 'found' ? 'found' : (active ? 'active' : (matched ? 'miss' : '')); const label = matched?.status === 'found' ? '实时命中' : (active ? '当前搜索' : '待命'); return `<div class="source-lane ${cls}"><b>${esc(name)}</b><span>${label}</span></div>`; }).join('');
  return `<section class="poster-job-dock" id="posterJobDock"><span class="badge">海报修复现场</span><h3>${phase}，不是干等一条进度条</h3><p class="hint">正在把豆瓣 CDN / 设计封面换成可加载的 TMDb、OMDb / IMDb、TVMaze、AniList、Jikan 或公共图源：${done} / ${total} · 命中 ${esc(job.found || 0)} · 未命中 ${esc(job.missed || 0)} · 当前搜索 ${esc(job.current_title || '准备中')}</p><div class="progress-meter"><span style="width:${width}%"></span></div><div class="source-stat-grid"><div class="source-stat"><b>${esc(sourceCopy)}</b><span class="hint">当前图源</span></div><div class="source-stat"><b>${esc(job.found || 0)}</b><span class="hint">实时命中</span></div><div class="source-stat"><b>${esc(Math.max(0, total - done))}</b><span class="hint">剩余</span></div></div><div class="poster-source-theater">${laneHtml}</div><div class="job-feed">${events || '<div class="job-event"><b>任务已启动</b><span>稍等片刻，这里会滚动显示每部作品命中的来源。</span></div>'}</div></section>`;
}
function updatePosterJobDock() { const el = $('posterJobDock'); if (el) el.outerHTML = posterJobDockHtml(); }
async function pollPosterJob(jobId, beforeRescueCount) {
  for (let i = 0; i < 180; i++) {
    await new Promise(resolve => setTimeout(resolve, 650));
    const res = await fetch(`/api/poster-jobs/${encodeURIComponent(jobId)}`);
    const job = await res.json();
    if (!res.ok || job.error) throw new Error(job.error || '海报任务状态读取失败');
    state.posterJob = job;
    if (Array.isArray(job.items)) mergePosterRescueItems(job.items);
    updatePosterJobDock();
    setStatus(`海报修复现场：${job.done || 0}/${job.total || 0} · 已找到 ${job.found || 0} · 当前 ${job.current_title || '多源搜索'}`);
    if (job.state === 'done' || job.state === 'error') {
      if (job.state === 'error') throw new Error(job.error || '海报修复任务失败');
      state.posterRescueVersion = POSTER_RESCUE_VERSION;
      persistRecommendationSnapshot();
      renderRecommendations();
      const after = posterRescueCount(state.recommendations);
      setStatus(`海报修复完成：新增 ${Math.max(0, beforeRescueCount - after)} 个可加载图源，剩余 ${after} 个待换源。`);
      return;
    }
  }
  throw new Error('海报修复任务超时');
}
async function rescuePosterImages(force=false) {
  if (state.posterRescueInFlight) return;
  const before = posterRescueCount(state.recommendations);
  const targets = posterRescueCount(state.recommendations);
  if (!targets && !force) return;
  state.posterRescueInFlight = true;
  setStatus(`正在修复海报：将用 TMDb / OMDb / IMDb / TVMaze / AniList / Jikan / 豆瓣精确搜索补 ${targets || state.recommendations.length} 个条目。`);
  try {
    const res = await fetch('/api/poster-jobs', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ items:state.recommendations || [], limit:Math.min(300, (state.recommendations || []).length || 160), poster_sources:posterSourcePayload() }) });
    const job = await res.json();
    if (!res.ok || job.error) throw new Error(job.error || '海报修复请求失败');
    state.posterJob = job;
    renderRecommendations();
    await pollPosterJob(job.job_id, before);
  } catch (error) {
    setStatus('海报修复失败：' + (error?.message || String(error)));
  } finally {
    state.posterRescueInFlight = false;
  }
}
function maybeAutoRescuePosters() {
  const count = posterRescueCount(state.recommendations);
  if (!count || state.posterRescueVersion >= POSTER_RESCUE_VERSION) return;
  setTimeout(() => rescuePosterImages(false), 500);
}
function resultsMainToolbar(targetCount, actualCount, candidateCount, visibleCount, totalCount) { const railCopy = state.railHidden ? '显示片单遥控器' : '隐藏侧栏'; const railAction = state.railHidden ? 'showResultsRail()' : 'hideResultsRail()'; const designedCount = designedPosterCount(state.recommendations); const rescueCount = posterRescueCount(state.recommendations); const externalCount = externalPosterCount(state.recommendations); const realCount = Math.max(0, (state.recommendations || []).length - designedCount); return `<div class="results-topbar stage-command-bar"><div class="signal-stack"><span class="badge">主舞台</span><b>${esc(state.activeSection)} · ${visibleCount}/${totalCount} 部</b><div class="hint">目标 ${esc(targetCount)} · 实际返回 ${esc(actualCount)} · 候选池 ${esc(candidateCount)} · 可加载外部海报 ${externalCount} · 真实海报 ${realCount} · 待换源 ${rescueCount} · 设计封面 ${designedCount}</div></div><div class="quick-actions"><button class="ghost" onclick="rescuePosterImages(true)">强制修复海报</button><button class="ghost" onclick="${railAction}" aria-expanded="${state.railHidden ? 'false' : 'true'}">${railCopy}</button></div></div>`; }
function renderRecommendations() {
  state.step = 3;
  renderStepNav();
  setStageLayout('results');
  const targetCount = state.lastCounts.target_limit ?? state.recommendations.length;
  const actualCount = state.lastCounts.returned ?? state.recommendations.length;
  const candidateCount = state.lastCounts.candidates ?? '-';
  const sectionNames = ['全部','精选','电影','电视剧','动漫', ...GLOBAL_ANIME_CHANNELS, ...(state.sections || []).map(s => s.name)].filter((x,i,a)=>x && a.indexOf(x)===i);
  const tabs = sectionNames.map(name => `<button class="tab ${state.activeSection === name ? 'active' : ''}" onclick="selectSection('${esc(name)}')">${esc(name)}</button>`).join('');
  const items = sectionItems(state.activeSection);
  const visibleLimit = activeGridLimit(state.activeSection, items.length);
  const visibleItems = visibleBatchItems(items, state.activeSection, visibleLimit);
  // Historical invariant: state.visibleRecommendations = items before batch shuffling; now it stores the active visible batch.
  state.visibleRecommendations = visibleItems;
  const showMore = items.length > visibleItems.length ? `<div class="show-more-panel"><span class="hint">当前显示 ${visibleItems.length} / ${items.length} 部</span><button onclick="showMoreRecommendations('${esc(state.activeSection)}')">再展开 ${Math.min(48, items.length - visibleItems.length)} 部</button><button class="ghost" onclick="showAllRecommendations('${esc(state.activeSection)}')">展开当前分类全部</button></div>` : '';
  const focusedGrid = items.length ? `<section class="media-rail"><div class="rail-head"><div class="rail-title">${esc(state.activeSection)} · 当前筛选</div><span class="hint">${items.length} 部</span></div><div class="recommendation-overview"><b>当前显示 ${visibleItems.length} / ${items.length} 部</b><span class="hint">不满意这一屏就换一批；海报悬停 / 聚焦即展开简介，点击进入电影级详情。</span><div class="quick-actions"><button class="batch-shuffle" onclick="shuffleSectionBatch('${esc(state.activeSection)}')">换一批</button><button class="ghost" onclick="rescuePosterImages(true)">补齐本屏海报</button></div></div><div class="poster-grid dense-poster-grid cinema-wall">${visibleItems.map(mediaCard).join('')}</div>${showMore}</section>` : '<div class="empty-state">这个分类暂时没有结果。默认候选池会自动用本地高分片单补齐电影 / 电视剧 / 动漫。</div>';
  const rails = buildMediaRails().map(rail => renderMediaRail(rail.name, rail.items.slice(0,24))).join('');
  const railDeck = rails ? `<details class="rail-collapse"><summary>展开横向频道 · 分类速览</summary><div class="rail-wall compact-rail-wall">${rails}</div></details>` : '<div class="empty-state">还没有推荐。先同步豆瓣或直接生成 quality-first 推荐。</div>';
  $('controlPanel').innerHTML = `<div class="results-control-inner"><div class="rail-toolbar"><span class="badge">辅助侧栏</span><button class="ghost" onclick="hideResultsRail()" aria-expanded="true">隐藏侧栏</button></div><h2>第三步：查看推荐</h2><p class="hint">第二步填写的是目标数量：系统会先扩展候选池，再尽量返回同等数量；因此现在明确显示“目标 / 实际返回 / 候选池”。</p><div class="metric-grid recommend-metrics"><div class="metric"><span class="metric-value">${esc(targetCount)}</span><span class="metric-label">目标</span></div><div class="metric"><span class="metric-value">${esc(actualCount)}</span><span class="metric-label">实际返回</span></div><div class="metric"><span class="metric-value">${esc(candidateCount)}</span><span class="metric-label">候选池</span></div><div class="metric"><span class="metric-value">${state.recommendations.length}</span><span class="metric-label">当前片单</span></div></div>${renderResultCompass(sectionNames, items.length, visibleItems.length)}<h3>口味 DNA</h3>${tasteDNA()}<div class="quick-actions"><button class="ghost" onclick="rescuePosterImages(true)">强制修复海报</button><button class="ghost" onclick="renderTastePanel()">调整口味</button><button class="ghost" onclick="renderCrawlerPanel()">重新同步</button></div>${renderPosterSourcePanel(true)}${renderPosterRecoveryCenter()}${imageResilienceGuide()}</div>`;
  $('mainPanel').innerHTML = `${resultsMainToolbar(targetCount, actualCount, candidateCount, visibleItems.length, items.length)}${posterJobDockHtml()}<h2>私人推荐片单</h2><div class="tabs">${tabs}</div>${renderGlobalAnimeChannels()}${categorySpotlight(state.activeSection)}<div class="rail-wall" id="railWall">${focusedGrid}${railDeck}</div>`;
  hydratePosterSourceControls();
}
function closeDetailDrawer() { $('detailDrawer')?.classList.remove('open'); document.body.classList.remove('detail-open'); }
function openDetail(index) { const r = state.visibleRecommendations[index]; if (!r) return; openDetailObject(r); }
function openDetailByKey(encodedKey) { const key = decodeURIComponent(encodedKey || ''); const all = [...(state.recommendations || []), ...(state.visibleRecommendations || [])]; const r = all.find(x => itemKey(x) === key); if (r) openDetailObject(r); }
function relatedByNames(r, field) { const names = recArray(r, field); const key = itemKey(r); if (!names.length) return []; return (state.recommendations || []).filter(item => itemKey(item) !== key && names.some(name => recArray(item, field).includes(name))).slice(0,10); }
function detailScrollTo(id, button) { document.querySelectorAll('.detail-tab').forEach(tab => tab.classList.remove('active')); button?.classList.add('active'); requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({behavior:'smooth', block:'start'})); }
function renderRelatedStrip(title, rows) { if (!rows.length) return `<p class="hint">${esc(title)}暂时没有命中，后续同步更多豆瓣资料后会自动补全。</p>`; return `<div class="related-strip">${rows.map(item => `<button class="related-card" onclick="openDetailByKey('${encodeURIComponent(itemKey(item))}')"><div class="poster">${safePosterImg(item)}</div><b>${esc(recTitle(item))}</b><small class="hint">${metadataLine(item)}</small></button>`).join('')}</div>`; }
function openDetailObject(r) {
  const drawer = $('detailDrawer');
  const title = recTitle(r);
  const summary = r.summary || r.item?.summary || '暂无官方简介，可先根据推荐理由判断是否加入片单。';
  const timelineItems = [metadataLine(r), summary, `豆瓣 ${r.douban_rating || r.item?.douban_rating || '-'} · ${recType(r) || '媒体'}`].filter(Boolean);
  const directorRelated = relatedByNames(r, 'directors');
  const castRelated = relatedByNames(r, 'casts');
  const reasons = (r.reasons || []).length ? r.reasons : ['质量优先策略推荐：综合评分、剧情完成度与用户口味相似度。'];
  document.body.classList.add('detail-open');
  drawer.classList.add('open');
  drawer.innerHTML = `<div class="detail-cinematic">
    <div class="detail-backdrop">${safePosterImg(r)}</div>
    <div class="detail-tabs"><button class="detail-tab" onclick="detailScrollTo('detailStory', this)">剧情</button><button class="detail-tab" onclick="detailScrollTo('detailPeople', this)">演职员</button><button class="detail-tab" onclick="detailScrollTo('detailReasons', this)">推荐理由</button><button class="detail-tab" onclick="detailScrollTo('detailRelated', this)">关联探索</button><button class="ghost" onclick="closeDetailDrawer()">关闭</button></div>
    <section class="detail-hero"><div class="poster-parallax">${safePosterImg(r)}</div><div><span class="badge">${esc(recType(r) || '媒体')}</span><h2 class="detail-title">${esc(title)}</h2><p class="meta-line">${metadataLine(r)} · 豆瓣 ${esc(r.douban_rating || r.item?.douban_rating || '-')}</p><div class="detail-orbit">${recArray(r,'genres').slice(0,6).map(x => `<span class="badge">${esc(x)}</span>`).join('')}<span class="badge">剧情质量优先</span><span class="badge">人物塑造</span></div><p><a href="${esc(r.url || '#')}" target="_blank" rel="noreferrer">打开豆瓣</a></p></div></section>
    <section id="detailStory" class="detail-section"><h3>剧情简介</h3><ol class="story-timeline">${timelineItems.map(x => `<li>${esc(x)}</li>`).join('')}</ol></section>
    <section id="detailPeople" class="detail-section"><h3>演职员胶片带</h3>${peopleEnrichmentBanner(r)}${peopleCarousel(r)}<div class="people-grid"><div><h3>导演</h3>${peopleChips(recArray(r,'directors'), '导演', r)}</div><div><h3>主演</h3>${peopleChips(recArray(r,'casts'), '主演', r)}</div></div></section>
    <section id="detailReasons" class="detail-section"><h3>推荐理由</h3><ul class="reason-stack">${reasons.map(x => `<li>${esc(x)}</li>`).join('')}</ul><h3>风险提示</h3><ul class="reason-stack">${(r.warnings || []).map(x => `<li class="warn">${esc(x)}</li>`).join('') || '<li class="hint">没有明显避雷信号。</li>'}</ul></section>
    <section id="detailRelated" class="detail-section"><h3>同导演</h3>${renderRelatedStrip('同导演', directorRelated)}<h3>同主演</h3>${renderRelatedStrip('同主演', castRelated)}</section>
  </div>`;
  if (needsPeoplePhotoEnrichment(r)) setTimeout(() => enrichPeopleForDetail(encodeURIComponent(itemKey(r))), 0);
}
function applySyncData(data) { const input = data.input_analysis || data.inputAnalysis || {}; if (input.user_id) state.lastUserId = input.user_id; if (typeof input.cookie_provided === 'boolean') state.lastCookieProvided = input.cookie_provided; state.items = data.items || []; state.ratedItems = state.items; state.counts = data.counts || {}; state.completeness = data.completeness || {}; state.diagnostics = data.diagnostics || []; state.errors = data.errors || []; state.recovery = data.recovery || null; renderCrawlSummary(); }
function renderNetworkFailureRecovery(message) { return `<section class="blocked-brief anti-overflow"><span class="badge">本地连接诊断</span><h3>请求没有完成，但这不是同步失败结论</h3><p class="sync-copy">系统已经识别你输入的豆瓣用户；如果这里出现网络、代理或服务端异常，先检查本机服务是否仍在运行。复制的是主页链接，不是授权凭证；真正遇到豆瓣 403 时会进入 Cookie 解锁流程。</p><div class="recovery-actions"><div class="recovery-action"><b>下一步</b>${esc(message || '检查本地服务状态后重试')}</div><div class="recovery-action"><b>仍可继续</b>可直接进入高质量片库模式，电影 / 电视剧 / 动漫都会继续生成推荐。</div></div><div class="quick-actions"><button onclick="continueWithoutSync()">继续用高质量片库生成推荐</button><button class="ghost" onclick="document.getElementById('doubanCookie')?.focus()">粘贴 Cookie 重试</button></div></section>`; }
async function syncDouban() {
  setStatus('正在同步豆瓣：先识别主页链接，再请求看过 / 想看。');
  const cookieBox = $('doubanCookie');
  const prefs = persistCrawlerControls();
  const cookieValue = normalizeCookieInput(cookieBox.value);
  cookieBox.value = cookieValue;
  state.lastUserInput = $('doubanUser').value.trim();
  state.lastUserId = extractDoubanUserId(state.lastUserInput);
  state.lastCookieProvided = Boolean(cookieValue);
  previewDoubanInput();
  renderCrawlSummary();
  const payload = { user_id_or_url:state.lastUserInput, cookie:cookieValue, max_pages:Number($('maxPages').value || 40), include_wish:$('includeWish').checked, expected_collect:Number($('expectedCollect').value || 0), expected_wish:Number($('expectedWish').value || 0) };
  if (prefs.rememberCookieSession && cookieValue) sessionStorage.setItem(COOKIE_SESSION_KEY, cookieValue);
  cookieBox.value = prefs.rememberCookieSession ? cookieValue : '';
  let res, data = {};
  try {
    res = await fetch('/api/sync-douban', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
    const raw = await res.text();
    try { data = raw ? JSON.parse(raw) : {}; } catch (error) { data = { error: raw || error.message || '服务器返回非 JSON' }; }
  } catch (error) {
    state.counts = {};
    state.completeness = {};
    state.diagnostics = [];
    state.errors = [error?.message || String(error)];
    state.recovery = { status:'network_error', headline:'本地服务或网络请求没有完成', can_continue_without_sync:true, actions:['确认本地服务窗口仍在运行后重试','继续用高质量片库生成推荐','如果豆瓣图片或页面需要代理，只配置本机 HTTP 代理端口'] };
    renderCrawlSummary();
    $('mainPanel').insertAdjacentHTML('afterbegin', renderNetworkFailureRecovery(error?.message || String(error)));
    setStatus('请求没有完成：先看右侧本地连接诊断；这不是主页链接错误。');
    return;
  }
  const response = data || {};
  if (response.input_analysis?.user_id) state.lastUserId = response.input_analysis.user_id;
  if (!res.ok || response.error) {
    if (response.recovery?.status === 'needs_cookie') {
      applySyncData(response);
      setStatus('豆瓣要求登录态：链接已识别，但主页链接不是 Cookie；把你已有的 Cookie 字符串手动粘贴到可见输入框后重试，或先继续推荐。');
      return;
    }
    state.counts = response.counts || {};
    state.completeness = response.completeness || {};
    state.diagnostics = response.diagnostics || [];
    state.errors = response.errors?.length ? response.errors : [response.error || '请求没有完成'];
    state.recovery = response.recovery || { status:'request_error', headline:'同步请求没有完成', can_continue_without_sync:true, actions:['检查输入格式','粘贴 Cookie 重试','继续用高质量片库生成推荐'] };
    renderCrawlSummary();
    $('mainPanel').insertAdjacentHTML('afterbegin', renderNetworkFailureRecovery(response.error || '请求没有完成'));
    setStatus('同步未完成：请看右侧诊断；系统不会把 403 登录态误判为链接错误。');
    return;
  }
  applySyncData(response);
  if (state.recovery?.status === 'needs_cookie') setStatus('豆瓣要求登录态：可粘贴 Cookie 重试；链接识别成功但主页链接不是 Cookie，也可继续用高质量片库生成推荐。');
  else setStatus(`同步完成：${state.items.length} 条资料已进入口味分析。`);
}
function useCsvInputs() { state.items = []; state.ratedItems = []; state.ratingsCsv = $('ratingsCsv').value; state.candidatesCsv = $('candidatesCsv').value; renderTastePanel(); }
async function clearCache() { await fetch('/api/cache', { method:'DELETE' }); localStorage.removeItem(LAST_RECOMMENDATION_KEY); $('mainPanel').innerHTML = '<div class="empty-state">本地缓存已清空，推荐快照也已清除。</div>'; }
async function recommend() {
  savePosterSourcePrefs();
  setStatus('正在生成推荐：先让 160 部片单快速上墙，海报与人物图会在后台继续修复。');
  const payload = {
    rated_items:state.items,
    ratings_csv: state.items.length ? '' : state.ratingsCsv,
    candidates_csv: state.candidatesCsv,
    like_terms:$('likeTerms').value,
    dislike_terms:$('dislikeTerms').value,
    include_movies:$('includeMovies').checked,
    include_series:$('includeSeries').checked,
    include_anime:$('includeAnime').checked,
    fetch_douban:$('fetchDouban').checked,
    enrich_details:$('enrichDetails') ? $('enrichDetails').checked : true,
    use_sample_candidates:!state.candidatesCsv,
    limit:Number($('limit').value || 160),
    poster_sources:posterSourcePayload()
  };
  const res = await fetch('/api/recommend', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
  const data = await res.json();
  if (!res.ok || data.error) {
    setStatus('推荐失败：' + (data.error || '请求失败'));
    return;
  }
  state.recommendations = data.results || [];
  state.sections = data.sections || [];
  state.profile = data.profile || null;
  state.lastCounts = data.counts || {};
  state.heroBySection = {};
  state.gridLimitBySection = {};
  state.batchOffsetBySection = {};
  state.peopleEnrichmentStatus = {};
  state.posterJob = null;
  state.posterRescueVersion = 0;
  cleanupRecommendationQuality();
  persistRecommendationSnapshot();
  renderRecommendations();
  const pending = Number(data.counts?.poster_rescue_pending || 0);
  const deferredNotes = [];
  if (data.counts?.deferred_douban_fetch) deferredNotes.push('实时豆瓣探索已延后，先用本地高质量片库上墙');
  if (data.counts?.deferred_enrichment) deferredNotes.push(`${pending} 个海报/详情补图会在后台修复台继续`);
  if (deferredNotes.length) {
    setStatus(`推荐已生成：${state.recommendations.length} 部已上墙；${deferredNotes.join('；')}，不再卡住生成流程。`);
  } else {
    setStatus(`推荐已生成：${state.recommendations.length} 部已上墙。`);
  }
  maybeAutoRescuePosters();
  setTimeout(() => scrollToResults('workspace'), 0);
}
function crawlDouban() { return syncDouban(); }
function goStep(step) { if (step === 1) renderCrawlerPanel(); if (step === 2) renderTastePanel(); if (step === 3) renderRecommendations(); }
window.__CINESCOPE_DIAGNOSTICS__ = { state, renderRecommendations, openDetailObject, closeDetailDrawer, canonicalPosterFor, peoplePhotoMap, rescuePosterImages, mergePosterRescueItems, maybeAutoRescuePosters, missingPosterRows, copyMissingPosterTitles, isCuratedPlaceholderPerson, needsPeopleIdentityEnrichment, needsPeoplePhotoEnrichment, enrichPeopleForDetail, mergePeopleEnrichment, shuffleSectionBatch, visibleBatchItems, isNumberedCuratedPlaceholder, cleanupStalePlaceholderRecommendations, stalePremiumDisplayTitleMap, normalizeRecommendationTitle, normalizeRecommendationDisplayData };
renderStepNav(); cleanupOldRecommendationSnapshots(); if (!tryRestoreRecommendationSnapshot()) renderCrawlerPanel();
</script>
</body>
</html>"""


def _canonical_poster_by_title() -> dict[str, str]:
    posters: dict[str, str] = dict(STATIC_POSTER_URLS_BY_TITLE)
    for item in curated_seed_candidates():
        if item.title and item.cover:
            posters.setdefault(item.title, item.cover)
    return posters


def _canonical_title_metadata() -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for title, metadata in TITLE_PEOPLE_METADATA.items():
        if not title or not isinstance(metadata, dict):
            continue
        compact: dict[str, object] = {}
        for key in ("douban_id", "year", "genres", "countries", "directors", "casts", "people_photos"):
            value = metadata.get(key)
            if value:
                compact[key] = value
        if compact:
            out[str(title)] = compact
    return out


INDEX_HTML = INDEX_HTML.replace(
    "__CANONICAL_POSTER_MAP__",
    json.dumps(POSTER_URLS_BY_DOUBAN_ID, ensure_ascii=False, sort_keys=True),
)
INDEX_HTML = INDEX_HTML.replace(
    "__CANONICAL_POSTER_BY_TITLE__",
    json.dumps(_canonical_poster_by_title(), ensure_ascii=False, sort_keys=True),
)
INDEX_HTML = INDEX_HTML.replace(
    "__CANONICAL_PEOPLE_PHOTO_MAP__",
    json.dumps(PEOPLE_PHOTOS_BY_DOUBAN_ID, ensure_ascii=False, sort_keys=True),
)
INDEX_HTML = INDEX_HTML.replace(
    "__CANONICAL_TITLE_METADATA__",
    json.dumps(_canonical_title_metadata(), ensure_ascii=False, sort_keys=True),
)
