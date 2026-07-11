# CineScope V3 四视口视觉验收

- 日期：2026-07-11（计划文件沿用 2026-07-10 命名）
- 服务：V3，绑定 127.0.0.1:7862，数据目录 output/acceptance-data
- 最终浏览器源：http://acceptance-20260711.localhost:7862（同一 127/8 loopback 服务；用于绕过旧静态模块缓存）
- 证据源：output/acceptance/evidence.json
- 最终结果：40 个 route/viewport 组合，40 个 audit 通过，40 张最终截图；另保留 10 张 1440px 焦点样式修复前截图。

## 固定验收会话

- sessionId: 49c2e02bea0c4664baa6d122d89767ab
- titleId: douban:1291879
- personId: derived:6buR5rO95piO
- 该会话由 window.__CINESCOPE_SEED_ACCEPTANCE__() 创建一次；四个视口复用相同 ID。
- 样本会话当前没有可插入 DOM 的 ready 本地图片，因此页面使用设计型 CSS fallback；没有以损坏或外链 img 隐藏缺口。真实媒体覆盖率在 Rollout Task 6 独立记录。

## 启动与采集

~~~powershell
$env:CINESCOPE_UI_VERSION='v3'
$env:CINESCOPE_DATA_DIR="$PWD\output\acceptance-data"
$env:PYTHONPATH="$PWD\src"
python -m douban_recommender.web --host 127.0.0.1 --port 7862 --no-browser
~~~

每页等待 route commit、aria-busy=0、图片完成与非空内容，再运行本地 audit helper 并保存 viewport PNG。390px 额外要求 desktop rail 隐藏、bottom nav 可见、document/body 无横向滚动。

## 真实浏览器发现与 TDD 修复

1. **验收种子安全 ID 路由**：真实本地 HTTP fixture 证明安全的 douban:... / derived:... ID 若经 encodeURIComponent 会与当前 API path contract 不一致。保留 safeId（拒绝斜杠、query/hash、.、..）后使用原始安全 segment；可执行 HTTP 测试断言 raw GET path。
2. **程序化 route focus 造成巨大默认 outline 与孤立断行**：1440px 的 Tonight、Title、Person 等页面出现浏览器默认 focus ring 穿过巨型标题，Tonight 末尾仅 1–2 字孤立换行。修复为 route focus target 无默认视觉 outline、标题 balance/正常断词、Tonight 字号和宽度重整、1200px 下 intro 改为纵向；同时压紧 rail controls。修复前证据位于 output/acceptance/1440x900/*-before-focus-fix.png。
3. **390px 顶部 288px 空白**：max-width:960px 的 .shell-status { flex:1 1 18rem } 在 720px 纵向 top bar 中继续生效，使状态栏高度达到 288px。新增失败测试后，在 mobile rule 重置为 flex:0 1 auto；最终所有 390px 页面 top bar 约 94.4px、状态栏约 17.3px。

## 汇总联系表

- output/acceptance/contact-sheets/1440x900.png
- output/acceptance/contact-sheets/1280x800.png
- output/acceptance/contact-sheets/1024x768.png
- output/acceptance/contact-sheets/390x844.png

## 逐页证据

| 视口 | Route | 截图 | Audit / 布局证据 | 观察与最终状态 |
|---|---|---|---|---|
| 1440x900 | /tonight | output/acceptance/1440x900/tonight.png | viewport=1440×900; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 程序化 focus/标题断行修复后复验；PASS |
| 1440x900 | /tonight/movie | output/acceptance/1440x900/tonight-movie.png | viewport=1440×900; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 程序化 focus/标题断行修复后复验；PASS |
| 1440x900 | /tonight/series | output/acceptance/1440x900/tonight-series.png | viewport=1440×900; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 程序化 focus/标题断行修复后复验；PASS |
| 1440x900 | /tonight/anime-series | output/acceptance/1440x900/tonight-anime-series.png | viewport=1440×900; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 程序化 focus/标题断行修复后复验；PASS |
| 1440x900 | /title/douban:1291879 | output/acceptance/1440x900/title-douban-1291879.png | viewport=1440×900; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 程序化 focus/标题断行修复后复验；PASS |
| 1440x900 | /person/derived:6buR5rO95piO | output/acceptance/1440x900/person-derived-6buR5rO95piO.png | viewport=1440×900; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 程序化 focus/标题断行修复后复验；PASS |
| 1440x900 | /universe | output/acceptance/1440x900/universe.png | viewport=1440×900; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 程序化 focus/标题断行修复后复验；PASS |
| 1440x900 | /library | output/acceptance/1440x900/library.png | viewport=1440×900; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 程序化 focus/标题断行修复后复验；PASS |
| 1440x900 | /taste | output/acceptance/1440x900/taste.png | viewport=1440×900; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 程序化 focus/标题断行修复后复验；PASS |
| 1440x900 | /health | output/acceptance/1440x900/health.png | viewport=1440×900; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 程序化 focus/标题断行修复后复验；PASS |
| 1280x800 | /tonight | output/acceptance/1280x800/tonight.png | viewport=1280×800; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 未发现新增视觉缺陷；PASS |
| 1280x800 | /tonight/movie | output/acceptance/1280x800/tonight-movie.png | viewport=1280×800; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 未发现新增视觉缺陷；PASS |
| 1280x800 | /tonight/series | output/acceptance/1280x800/tonight-series.png | viewport=1280×800; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 未发现新增视觉缺陷；PASS |
| 1280x800 | /tonight/anime-series | output/acceptance/1280x800/tonight-anime-series.png | viewport=1280×800; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 未发现新增视觉缺陷；PASS |
| 1280x800 | /title/douban:1291879 | output/acceptance/1280x800/title-douban-1291879.png | viewport=1280×800; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 未发现新增视觉缺陷；PASS |
| 1280x800 | /person/derived:6buR5rO95piO | output/acceptance/1280x800/person-derived-6buR5rO95piO.png | viewport=1280×800; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 未发现新增视觉缺陷；PASS |
| 1280x800 | /universe | output/acceptance/1280x800/universe.png | viewport=1280×800; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 未发现新增视觉缺陷；PASS |
| 1280x800 | /library | output/acceptance/1280x800/library.png | viewport=1280×800; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 未发现新增视觉缺陷；PASS |
| 1280x800 | /taste | output/acceptance/1280x800/taste.png | viewport=1280×800; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 未发现新增视觉缺陷；PASS |
| 1280x800 | /health | output/acceptance/1280x800/health.png | viewport=1280×800; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 未发现新增视觉缺陷；PASS |
| 1024x768 | /tonight | output/acceptance/1024x768/tonight.png | viewport=1024×768; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 未发现新增视觉缺陷；PASS |
| 1024x768 | /tonight/movie | output/acceptance/1024x768/tonight-movie.png | viewport=1024×768; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 未发现新增视觉缺陷；PASS |
| 1024x768 | /tonight/series | output/acceptance/1024x768/tonight-series.png | viewport=1024×768; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 未发现新增视觉缺陷；PASS |
| 1024x768 | /tonight/anime-series | output/acceptance/1024x768/tonight-anime-series.png | viewport=1024×768; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 未发现新增视觉缺陷；PASS |
| 1024x768 | /title/douban:1291879 | output/acceptance/1024x768/title-douban-1291879.png | viewport=1024×768; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 未发现新增视觉缺陷；PASS |
| 1024x768 | /person/derived:6buR5rO95piO | output/acceptance/1024x768/person-derived-6buR5rO95piO.png | viewport=1024×768; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 未发现新增视觉缺陷；PASS |
| 1024x768 | /universe | output/acceptance/1024x768/universe.png | viewport=1024×768; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 未发现新增视觉缺陷；PASS |
| 1024x768 | /library | output/acceptance/1024x768/library.png | viewport=1024×768; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 未发现新增视觉缺陷；PASS |
| 1024x768 | /taste | output/acceptance/1024x768/taste.png | viewport=1024×768; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 未发现新增视觉缺陷；PASS |
| 1024x768 | /health | output/acceptance/1024x768/health.png | viewport=1024×768; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 未发现新增视觉缺陷；PASS |
| 390x844 | /tonight | output/acceptance/390x844/tonight.png | viewport=390×844; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=false; bottom=true | 移动 top-bar flex-basis 修复后复验；PASS |
| 390x844 | /tonight/movie | output/acceptance/390x844/tonight-movie.png | viewport=390×844; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=false; bottom=true | 移动 top-bar flex-basis 修复后复验；PASS |
| 390x844 | /tonight/series | output/acceptance/390x844/tonight-series.png | viewport=390×844; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=false; bottom=true | 移动 top-bar flex-basis 修复后复验；PASS |
| 390x844 | /tonight/anime-series | output/acceptance/390x844/tonight-anime-series.png | viewport=390×844; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=false; bottom=true | 移动 top-bar flex-basis 修复后复验；PASS |
| 390x844 | /title/douban:1291879 | output/acceptance/390x844/title-douban-1291879.png | viewport=390×844; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=false; bottom=true | 移动 top-bar flex-basis 修复后复验；PASS |
| 390x844 | /person/derived:6buR5rO95piO | output/acceptance/390x844/person-derived-6buR5rO95piO.png | viewport=390×844; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=false; bottom=true | 移动 top-bar flex-basis 修复后复验；PASS |
| 390x844 | /universe | output/acceptance/390x844/universe.png | viewport=390×844; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=false; bottom=true | 移动 top-bar flex-basis 修复后复验；PASS |
| 390x844 | /library | output/acceptance/390x844/library.png | viewport=390×844; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=false; bottom=true | 移动 top-bar flex-basis 修复后复验；PASS |
| 390x844 | /taste | output/acceptance/390x844/taste.png | viewport=390×844; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=false; bottom=true | 移动 top-bar flex-basis 修复后复验；PASS |
| 390x844 | /health | output/acceptance/390x844/health.png | viewport=390×844; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=false; bottom=true | 移动 top-bar flex-basis 修复后复验；PASS |

## 门禁结论

- brokenImages=[]：40/40
- externalImages=[]：40/40
- overflowNodes=[]：40/40
- focusFailures=[]：40/40
- emptyMain=false：40/40
- 页面横向滚动：0/40
- 390px desktop rail 可见：0/10；bottom nav 可见：10/10
- Canary identity mismatch：本 Task 未观察到；最终媒体身份/覆盖门禁由 Task 6 结合 diagnostics 复核。
