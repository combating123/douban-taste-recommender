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

## Rollout Task 5：真实同步、推荐、换批与刷新验收

- 日期：2026-07-12
- V3 专用服务：`127.0.0.1:7875`
- 数据目录：`output/task5-acceptance-data`
- 最终浏览器源：`http://task5-fixed-20260712.localhost:7875`（新 loopback 子域用于绕过旧 ES module 缓存）
- 启动仍要求显式设置 `CINESCOPE_UI_VERSION=v3`；未改变默认 legacy 回滚路径。

### 公开豆瓣同步

- 输入：`https://www.douban.com/people/272042071/?_dtcc=1&_i=fixture`
- job：`e4ce2171b3194fcd9ffe479cd5eeca3b`
- 最终状态：`complete`；UI 显示“同步完成”。
- 实际实时结果：条目 `280`，看过 `244`，想看 `36`，成功页 `22`，失败页 `0`。
- 原始停止原因：`已到达空白分页`；UI 映射为“已到达列表末页”。
- 相对约 `242` 看过 / `34` 想看的历史近似基线，两项均增加 `2`；本记录采用本次公开页面的实时结果，不回填旧基线。
- 公共连接未要求登录，因此没有触发 Cookie 续跑；可见 Cookie 输入在启动前后长度均为 `0`。

### 160-target 会话与计数语义

- session：`ecbb40ee00384b0c82dcad30559df1d4`
- seed title：`douban:1291879`
- seed person：`derived:6buR5rO95piO`
- 页面同时可见：目标 `160`、实际返回 `192`、当前频道候选池、匹配、本批可见、当前批次。
- 候选池：电影 `85`、剧集 `54`、动漫 `53`；合计 `192`。
- 匹配：电影 `84`、剧集 `54`、动漫 `53`。
- 初始本批可见：三个频道均为 `24`。
- 语义保持独立：`target=160` 是请求目标，`returned=192` 是返回候选总量，`pool` 是频道候选池，`matched` 是频道匹配量，`visible` 是当前批次量。
- 动漫池共 `53` 项，全部 `media_type=动漫` 且带 `动漫剧集` 标签；未发现电影/动画片标记，因此没有动画电影混入。
- 剧集池共 `54` 项，古装标记 `0/54`，不存在古装主导。

### 连续换批

- 电影：批次 `1/2/3/4` 分别返回 `24/24/24/12` 项；第四批耗尽；各批之间重复标题 `0`。
- 剧集：批次 `1/2/3/4` 分别返回 `24/24/6/0` 项；第三批耗尽，第四批为空；耗尽前重复标题 `0`。
- 动漫：批次 `1/2/3/4` 分别返回 `24/24/5/0` 项；第三批耗尽，第四批为空；耗尽前重复标题 `0`。
- 最终撤回到动漫第 `3` 批，标题为：`天元突破红莲螺岩`、`降世神通：最后的气宗`、`爱，死亡和机器人`、`雾山五行`、`灵笼`。

### Refresh / Back 恢复与浏览器审计

1. 通过作品详情 → 口味宇宙 → “带入今晚推荐”的可见流程，将 `降世神通：最后的气宗` 加入候选托盘。
2. 在 `/tonight/anime-series` 的第 `3` 批滚动到 `scrollY=900`；页面高 `2031`，viewport 高 `720`。
3. 从页面内可见作品链接打开 `/title/douban:1938084`；离开频道后安全状态投影为 `animeBatch=3`、`animeScroll=900`、`candidateTrayCount=1`。
4. 刷新详情页后 route 仍为 `/title/douban:1938084`，且审计结果：`brokenImages=[]`、`externalImages=[]`、`overflowNodes=[]`、`focusFailures=[]`、`emptyMain=false`。
5. 浏览器返回后 route 为 `/tonight/anime-series`，页面可见目标 `160`、实际返回 `192`、本批可见 `5`、当前批次 `3`；`scrollY=900`，安全状态投影仍为 `animeBatch=3`、`animeScroll=900`、`candidateTrayCount=1`。

### Task 5 发现并按 TDD 修复的缺陷

1. 同步完成卡片只显示总条目/成功页/失败页，不能区分看过与想看；现显示看过、想看及分页结果。
2. 160-target 会话在候选生成后丢失全局 `target/returned`；现通过持久化 `candidate_counts` 并在会话创建/恢复响应中返回，Tonight 显式展示六项计数。
3. Router 离开页面时先写滚动位置，随后 store subscriber 以陈旧 `scrollByRoute` 覆盖该值；现由 router 把滚动保存事件 dispatch 到 store，再统一持久化。

### 隐私与限制

- 本次未从浏览器 profile、Cookie 数据库、磁盘 Cookie、环境转储、请求头、持久状态或 sessionStorage 读取 Cookie；也未检查 sessionStorage 来恢复 Cookie。
- Cookie 只保留在可见输入对应的同标签页会话路径；本次输入始终为空。
- 浏览器状态核对仅返回 allowlisted 投影：route、动漫批次、动漫滚动位置、候选托盘数量；未导出完整运行时状态。
- 可见图片门禁继续要求同源 `/media/*`；刷新审计的外链图片与损坏图片均为 `0`。
- 外部限制仅为：公开连接未触发登录，所以无法在不提供用户 Cookie 的前提下实测 `needs_cookie` 续跑分支；公开无 Cookie 同步本身已完整通过。

## Task 5 review fixes — final-code gate (2026-07-12)

### Review findings closed with TDD

1. **Unknown legacy recommendation target:** a deliberately downgraded legacy session now restores `candidate_counts.target_size` as JSON `null` instead of inventing `0`; its exact `returned_size` is still recomputed from the restored channel pools. The V3 store and app reducer preserve that unknown value and Tonight renders `目标 —`. A newly created/metadata-bearing session continues to render exact values (`目标 160`, `实际返回 192`).
2. **Stale departure-scroll ownership:** the router's pending departure marker is now owned by the navigation generation. A blocked, stale, or throwing navigation releases only its own marker, while an overlapping newer navigation retains ownership. The regression scenario `slow -> blocked -> real` saves the fresh `/home` scroll value `55` before the real route commits.
3. **390px Universe roster compression discovered by the fresh gate:** the first final-code pass exposed nine vertically compressed roster entries. A focused failing CSS contract was added before changing production CSS; mobile roster entries now retain a readable bounded width and scroll horizontally inside their own roster without document-level horizontal overflow.

### Dedicated final-code service and live sync

- Service: `CINESCOPE_UI_VERSION=v3` (explicit opt-in), `127.0.0.1:7875`, data directory `output/task5-acceptance-data`.
- Browser origin: `http://task5-review-final-20260712.localhost:7875`.
- Accepted recommendation session: `ecbb40ee00384b0c82dcad30559df1d4`; target `160`; returned `192`; anime batch `3`.
- Public sync profile: `https://www.douban.com/people/272042071/?_dtcc=1&_i=fixture`.
- Final sync job: `d6574a3aed8649b3a9e0be45c3ef2c45`, state `complete`.
- Actual live result: `280` items, `244` watched/collect, `36` wanted/wish, `22` successful pages, `0` failed pages; visible stop reason `已到达列表末页`. This is two more watched and two more wanted than the approximate historical `242/34` baseline, so the live values are authoritative for this gate.

### Four-viewport principal-route matrix

Principal routes: `/tonight`, `/tonight/movie`, `/tonight/series`, `/tonight/anime-series`, `/title/douban:1291879`, `/person/derived:6buR5rO95piO`, `/universe`, `/library`, `/taste`, `/health`.

| Viewport | Rows passed | Broken images | External images | Overflow nodes | Focus failures | Empty main | Horizontal scroll | Rail / bottom nav |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1440x900 | 10/10 | 0 | 0 | 0 | 0 | 0 | 0 | rail visible / bottom hidden |
| 1280x800 | 10/10 | 0 | 0 | 0 | 0 | 0 | 0 | rail visible / bottom hidden |
| 1024x768 | 10/10 | 0 | 0 | 0 | 0 | 0 | 0 | rail visible / bottom hidden |
| 390x844 | 10/10 | 0 | 0 | 0 | 0 | 0 | 0 | rail hidden 10/10 / bottom visible 10/10 |
| **Total** | **40/40** | **0** | **0** | **0** | **0** | **0** | **0** | mobile contract passed |

The four Tonight routes produced 16 count-line rows. At `/tonight/anime-series`, all four viewports visibly showed `目标 160`, `实际返回 192`, `候选池 53`, `匹配 53`, `本批可见 5`, and `当前批次 3`, with zero count-line overflow. `/health` visibly showed the long privacy/help line `默认自动翻页到末页；安全上限 250 页。Cookie 仅保留在当前标签页会话中。`, the sync line `条目 280 · 看过 244 · 想看 36 · 成功页 22 · 失败页 0`, and `已到达列表末页` at every viewport, with zero overflow.

Machine-readable and visual evidence:

- `output/task5-acceptance/task5-review-final-evidence.json` — aggregate summary plus all 40 route/viewport rows.
- `output/task5-acceptance/final-code-gate/evidence.json` — raw final-code audit rows.
- `output/task5-acceptance/final-code-gate/<viewport>/*.png` — 40 route screenshots.
- `output/task5-acceptance/final-code-gate/focus/*-tonight-counts.png` and `*-health-sync.png` — four-view count and Health crops.
- `output/task5-acceptance/final-code-gate/focus/task5-final-counts-health-contact-sheet.png` — reviewed contact sheet.

### Privacy and remaining external limitation

The Cookie field remained visibly empty. No Cookie was read from browser/session storage, a browser profile, disk, environment dumps, request headers, or persisted state; no storage was inspected to recover one. The accepted session was loaded through a same-origin API read and an allowlisted in-memory store dispatch only. Visible images remained fail-closed to same-origin `/media/*`. Public sync did not request authentication, so the visible `needs_cookie` resume branch could not be completed without a user-supplied Cookie; no Cookie was sourced or fabricated.

## Task 5 upgrade-path re-review — explicit null precedence (2026-07-12)

### Upgrade-path contract

A previous Task 5 build could persist a same-session `candidate_counts.target_size` value of `0`. When the restored server payload explicitly says `target_size: null`, that present null is now authoritative and clears any cached numeric value. A missing `target_size` property still uses the existing safe same-session fallback, while a valid numeric server value such as `160` remains authoritative. Unknown is therefore preserved as `null` in state and `目标 —` in Tonight; it is never represented as `0`.

The integration regression persists a same-session target of `0`, restores it through the real store projection, and then applies three server shapes in order:

1. explicit `target_size: null` → all three channels become `null` and Tonight renders `目标 —`, never `目标 0`;
2. exact `target_size: 160` → state and Tonight return to exact `160`;
3. absent `target_size` after that exact response → the safe exact cached fallback remains `160`.

The RED run failed with `explicit null did not clear cached target for movie: {"target_size":0,"returned_size":192}`. The minimal implementation only adds own-property-aware precedence for the explicit null case in `app.js`.

### Recaptured final-code browser evidence

- Evidence generated: `2026-07-11T20:30:59.282Z` (`2026-07-12 04:30:59 +08:00`).
- Service: explicit-opt-in V3 on `127.0.0.1:7875`, data directory `output/task5-acceptance-data`.
- Browser origin: `http://task5-upgrade-final2-20260712.localhost:7875`.
- Exact-count matrix session: `7e5061e80be74395bb6a6b1ba876271e`, target `160`, returned `192`, anime batch `3`.
- Legacy-dash browser session: `da5be0b35dd84973b9cb5a2419709a68`; it held a cached numeric target before reload, was deliberately downgraded on the server to omit historical candidate-count metadata, restored as API `target_size: null`, and visibly rendered `目标 —` with `实际返回 192`, pool `53`, matched `53`, visible `5`, batch `3`. The automated integration regression covers the specifically reported cached-`0` predecessor state.

The same ten principal routes were recaptured at `1440x900`, `1280x800`, `1024x768`, and `390x844`. All 40 rows use final viewport screenshots and passed:

```text
row_count=40
pass_count=40
failure_count=0
broken_images=0
external_images=0
overflow_nodes=0
focus_failures=0
empty_main_rows=0
horizontal_scroll_rows=0
mobile_rail_hidden_rows=10
mobile_bottom_nav_visible_rows=10
tonight_rows=16
viewport_screenshots=40
```

At `/tonight/anime-series`, all four viewports again exposed the exact six-value line: `目标 160`, `实际返回 192`, `候选池 53`, `匹配 53`, `本批可见 5`, `当前批次 3`. The 390px Universe roster retained nine entries with a minimum entry width of `288px`, no document-level horizontal scroll, and no overflow finding.

Evidence paths:

- `output/task5-acceptance/task5-upgrade-path-final-evidence.json`
- `output/task5-acceptance/upgrade-path-final-code-gate/evidence.json`
- `output/task5-acceptance/upgrade-path-final-code-gate/<viewport>/*.png` — 40 final viewport screenshots
- `output/task5-acceptance/upgrade-path-final-code-gate/focus/<viewport>-tonight-counts.png` — four exact-count crops
- `output/task5-acceptance/upgrade-path-final-code-gate/focus/legacy-target-dash-final.png` — focused authoritative-null crop
- `output/task5-acceptance/upgrade-path-final-code-gate/focus/upgrade-path-counts-contact-sheet.png` — reviewed exact/legacy contact sheet

No new public sync was started for this upgrade-only re-review; the previously recorded `280 / 244 / 36 / 22 / 0` live result and its provenance remain unchanged. No Cookie was entered, sourced, or inspected. Browser Cookie/profile/storage data was not read, and no missing media was fabricated.

## Rollout Task 6 — performance and media coverage gate (2026-07-12)

### Service, fixture, and static contracts

- V3 remained explicit opt-in: `CINESCOPE_UI_VERSION=v3`; the default legacy rollback path was not changed.
- Dedicated service: `127.0.0.1:7886`; dedicated data directory: `output/task6-acceptance-data`.
- The Task 6 database was a byte-identical copy of `output/task5-acceptance-data/cinescope.db` at startup; both SHA-256 values were `28952d34cdbe43af03b3e1cec1d6b79d8bf9c172022699c15aca4466827f2700`.
- Accepted session `ecbb40ee00384b0c82dcad30559df1d4` was reused through a same-origin API read and the allowlisted reducer/persistence write path. The automation did not inspect Cookie data, an existing browser profile, any pre-existing local/session storage value, or source secrets; it wrote only the allowlisted UI-state projection needed for full-document reload restoration.
- Detail fixture: `/title/douban:1291879` (`罗生门`).
- `tests/test_performance_contract.py` added five dedicated static/scope contracts. They all passed on their first run (`5 passed`), characterizing behavior already present at the required base commit: `MAX_INITIAL_CARDS=9`, `casts.slice(0, 8)` with directors, priority-0 portrait prefetch, decoded same-origin `/media/*` insertion, and exact diagnostics scopes. There was therefore no invented RED and no production behavior change.

### Warm-cache full-document reload measurements at 1440×900

Measurement used a fresh Task 6 Chrome profile with cache enabled. `Page.addScriptToEvaluateOnNewDocument` installed buffered `PerformanceObserver` collectors for `largest-contentful-paint` and `longtask` before priming or measuring. Each route was primed once, then measured through three `Page.reload` full-document reloads; every measured `PerformanceNavigationTiming.type` was `reload`. DOM readiness was checked separately and was not substituted for LCP.

| Route | Warm LCP runs (ms) | Warm DCL runs (ms) | Same-origin `/media/*` transfer bytes | `/media/*` encoded body bytes | Long tasks / maximum | Gate |
|---|---|---|---:|---:|---|---|
| `/tonight` | `44 / 32 / 32` (max `44`) | `14.1 / 14.0 / 14.5` (max `14.5`) | `0 / 0 / 0` | `0 / 0 / 0` | `0 / 0 ms` | PASS |
| `/title/douban:1291879` | `32 / 36 / 24` (max `36`) | `14.4 / 15.2 / 13.2` (max `15.2`) | `0 / 0 / 0` | `0 / 0 / 0` | `0 / 0 ms` | PASS |

- Gate: every warm LCP was `<=2500 ms`; no observed long task exceeded `200 ms`.
- The `/tonight` LCP candidate was the final Tonight intro heading. The detail reload LCP candidate was the initial shell heading; the final detail DOM was independently required to settle before evidence capture. The recorded values are observer LCP values, not DOM-ready proxies.
- Zero `/media/*` requests and zero bytes reflect the fixture's actual zero ready media assets; they are not a claim that real media was compressed or hidden.
- Since all measured gates passed, Task 6 made no production performance change and triggered no RED/GREEN optimization cycle.

### Rendered browser media coverage and designed fallbacks

Scope: one representative settled warm reload from each audited route for coverage, plus all six measured reloads for browser failure totals. A “missing image element failure” means a rendered media frame marked `ready` without an `<img>`, or a frame still marked `loading` after settle. A designed CSS fallback is reported separately and is not treated as a failure.

| Route / kind | Rendered occurrences | Real decoded `<img>` | Designed fallback | Real coverage |
|---|---:|---:|---:|---:|
| `/tonight` posters | 15 | 0 | 15 | 0% |
| Detail posters | 9 | 0 | 9 | 0% |
| Detail portraits | 4 | 0 | 4 | 0% |
| Detail backdrop | 1 | 0 | 1 | 0% |
| **Combined posters** | **24** | **0** | **24** | **0%** |
| **Combined portraits** | **4** | **0** | **4** | **0%** |

- All poster, portrait, and backdrop fallback status labels were exactly `本地素材缺失`.
- `/tonight` designed poster labels (15 occurrences; 14 unique labels because the hero repeats one shelf title): `天元突破红莲螺岩 · 作品海报`, `完美的日子 · 作品海报`, `怪物 · 作品海报`, `教父 · 作品海报`, `杀人回忆 · 作品海报`, `消失的爱人 · 作品海报`, `灵笼 · 作品海报`, `爱，死亡和机器人 · 作品海报`, `美丽人生 · 作品海报`, `花样年华 · 作品海报`, `重庆森林 · 作品海报`, `降世神通：最后的气宗 · 作品海报`, `降临 · 作品海报`, `雾山五行 · 作品海报`.
- Detail designed poster labels: `七武士 · 作品海报`, `信号 · 作品海报`, `奇巧计程车 · 作品海报`, `控方证人 · 作品海报`, `河边的错误 · 作品海报`, `漫长的季节 · 作品海报`, `罗生门 · 作品海报`, `致命魔术 · 作品海报`, `隐秘的角落 · 作品海报`.
- Detail designed portrait labels: `三船敏郎 · 人物肖像`, `京町子 · 人物肖像`, `志村乔 · 人物肖像`, `黑泽明 · 人物肖像`; designed backdrop label: `罗生门 · 作品背景`.
- Across all six measured reloads: broken visible images `0`, external/non-`/media/*` visible images `0`, pending visible images `0`, and missing-image-element failures `0`. The built-in browser audit also reported broken images `0` and external images `0` on every run.
- The insertion contract remains unchanged: a visible `<img>` must be same-origin `/media/*` and only replaces its fallback after load, `decode()`, and `naturalWidth > 0`.

### Diagnostics scopes and identity canary

The post-measurement `/api/v2/diagnostics` response reported:

- Stored media totals: `assets_total=0`, `bytes=0`.
- Bounded recent-batch poster audit: `total=256`, `ready=0`, `degraded=0`, `ambiguous=0`, `missing=256`.
- Audit window scope: `recent_recommendation_batches`; ordering `created_at_desc_then_id_desc`; `batch_limit=32`; `row_limit=256`; `selected_batches=32`; `rows_audited=256`; `truncated=true`.
- Wrong-identity count: `0`, with exact scope `global_historical_identity_rejected_hard_conflicts`.
- Attribution limit: `recommendation_media_identity_attribution=unavailable_without_stable_foreign_key`. The wrong-identity value is a global historical hard-conflict canary and is not attributed to the visible session. The bounded media totals are likewise a recent-batch window, not a visible-page-only total.

The required zero browser failures and zero wrong-identity canaries passed. Real poster and portrait coverage remained zero and is reported directly rather than disguised by the designed fallbacks.

### Machine-readable evidence

- `output/task6-acceptance/service.json` — dedicated service, data copy hashes, and zero copied media files.
- `output/task6-acceptance/fixture.json` — accepted session and detail fixture summary.
- `output/task6-acceptance/performance.json` — raw observer entries, navigation timing, resource timing, CDP media events, per-run browser media audits, and gates.
- `output/task6-acceptance/diagnostics.json` — raw post-measurement diagnostics response.
- `output/task6-acceptance/acceptance-summary.json` — aggregate metrics, coverage, failures, and exact scope statements.
- `output/task6-acceptance/evidence-validation.json` — machine validation of all required gates and non-fabrication assertions.
- `output/task6-acceptance/measure-performance.mjs` — the exact CDP measurement harness used for the final evidence.

## Task 6 review closure — route-specific meaningful paint (2026-07-12)

The original Task 6 detail LCP entries were valid browser LCP entries but identified only the generic initial `#shell-title`. They did not, by themselves, timestamp the first meaningful detail paint. Fresh evidence therefore retains standard LCP while adding a route-specific pre-navigation observer; the standard detail LCP is no longer used alone to claim meaningful detail readiness.

### Pre-navigation method

The CDP harness still installs through `Page.addScriptToEvaluateOnNewDocument` before prime or measured navigation. In the same injected source it now:

1. watches for the intended committed route root and keeps a frame-level detector active while CSS entry animation progresses;
2. requires the exact final route, non-empty intended content, positive rendered geometry, matching route identity, required copy/sections, and route-specific content children;
3. records `routeCommitMs` at the first valid visible route-root commit;
4. revalidates the route after two `requestAnimationFrame` callbacks and records `routeContentPaintMs` as the meaningful painted-route proxy;
5. records `routeSettleMs` only when the same proof remains valid, `document.readyState=complete`, no element is `aria-busy=true`, no media frame remains `loading`, and route-root opacity is at least `0.99`.

Route proofs:

- Tonight: root `.tonight-page`; identity `.tonight-intro__title` = `今晚，只看值得开始的。`; required copy includes `目标 160` and `实际返回 192`; required route structures are present; `.title-card` count is `14`; final route is `/tonight`.
- Detail: root `.detail-page`; identity `.detail-hero__title` = `罗生门`; required copy includes `罗生门`, `演职人员`, and `本地关联`; `#overview`, `#people`, and `#relations` are present; `.person-card` count is `4`; final route is `/title/douban:1291879`.
- Every paint proof records the exact selector, text/identity proof, required-text and required-selector results, final route, content count, computed style, and bounding rect. Tonight rects were `1266.625×2017.703125`; detail rects were `1266.625×3079.984375`, all with positive visible geometry.

### Fresh warm-cache full-reload evidence

Each route was primed once and then measured through three cache-enabled `Page.reload` full-document reloads at `1440×900`. All measured navigation types were `reload`.

| Route / metric | Raw runs (ms) | Min | Median | Max | Gate |
|---|---|---:|---:|---:|---|
| `/tonight` standard LCP | `32 / 32 / 32` | 32.0 | 32.0 | 32.0 | PASS |
| `/tonight` route commit | `67.6 / 61.5 / 74.1` | 61.5 | 67.6 | 74.1 | proof present |
| `/tonight` route-content paint | `71.7 / 64.2 / 80.2` | 64.2 | 71.7 | 80.2 | PASS |
| `/tonight` route settle | `71.7 / 64.3 / 80.4` | 64.3 | 71.7 | 80.4 | PASS |
| Detail standard LCP | `24 / 36 / 32` | 24.0 | 32.0 | 36.0 | browser LCP retained |
| Detail route commit | `78.4 / 99.9 / 86.8` | 78.4 | 86.8 | 99.9 | proof present |
| Detail route-content paint | `94.3 / 116.0 / 103.0` | 94.3 | 103.0 | 116.0 | PASS |
| Detail route settle | `317.6 / 339.1 / 325.8` | 317.6 | 325.8 | 339.1 | PASS |

- Meaningful route-content paint gate: every run `<=2500 ms`.
- Route settle gate: every run `<=2500 ms`.
- Existing long-task gate: six runs, maximum `0 ms`, therefore no task above `200 ms`.
- Standard LCP gate remains passing, but all three detail LCP candidates remain `H1#shell-title`; no detail LCP candidate was fabricated or relabeled.
- Detail paint proofs captured the first visible entry-animation frames at opacity about `0.074`; settle proofs were separately delayed until opacity about `0.992`, with document complete, no busy state, and zero loading media frames.
- The new methodology passed without exposing a production bottleneck, so no production regression or implementation change was made.

### Unchanged coverage and scopes

- Same-origin `/media/*` requests, transfer bytes, and encoded body bytes remained `0`; the fixture still has zero ready media assets.
- Real coverage remains posters `0/24`, portraits `0/4`, backdrop `0/1`; all are honestly reported designed CSS fallbacks.
- Browser broken/external/pending/missing-image-element failures remain `0` across all six runs.
- Diagnostics remain `assets_total=0`, `bytes=0`; bounded recent-batch poster audit `0 ready / 256 missing`; wrong-identity canary `0` with scope `global_historical_identity_rejected_hard_conflicts` and no visible-session attribution.
- `output/task6-acceptance/evidence-validation.json` schema 2 contains 25 passing checks, including required route selector/identity/timestamps/geometry, ordering, content-paint and settle budgets, honest shell LCP retention, raw summary statistics, zero media fabrication, and exact diagnostics scopes.

## Rollout Task 8 — final verification and completion evidence (2026-07-12)

### Bound source and isolated services

- Final code under test: `847a70b4a447fa9d26b17b5e5be1326dc65e218c` (`feat: make cinescope v3 the default experience`).
- Default V3 ran on `127.0.0.1:7891` with `CINESCOPE_UI_VERSION` absent, dedicated data directory `output/task8-acceptance-data`, and the V3 asset shell present. This directly verifies the default switch rather than an explicit V3 opt-in.
- Rollback ran separately on `127.0.0.1:7892` with `CINESCOPE_UI_VERSION=legacy`. Port `7860` was not touched. Both Task 8 ports were released at shutdown.
- Fixed resources: session `ecbb40ee00384b0c82dcad30559df1d4`, title `douban:1291879`, person `derived:6buR5rO95piO`.

### Automated and hygiene gates

```text
python -m unittest discover -s tests -v
Ran 601 tests in 86.615s
OK
```

- Recursive JavaScript syntax validation covered all `23` files under `src/douban_recommender/ui/js/**/*.js`; every `node --check` exited successfully.
- `git diff --check` passed before documentation work and again after this section was added.
- The required source/test/README/acceptance placeholder scan returned zero matches, so there was no unintended placeholder to classify.
- Raw logs: `output/task8-acceptance/unittest-final.log`, `output/task8-acceptance/node-check.log`, and `output/task8-acceptance/hygiene.log`.

### Fresh final-code browser smoke

The Codex in-app browser collected a new source-bound matrix; prior Task 4–6 JSON was not counted as final-code smoke. Each route settled with the intended route, non-empty main content, no `aria-busy=true`, and a viewport screenshot.

| Viewport | Route | Audit | Navigation contract |
|---|---|---|---|
| `1440×900` | `/tonight` | PASS | desktop rail visible; bottom nav hidden |
| `1440×900` | `/tonight/anime-series` | PASS | desktop rail visible; bottom nav hidden |
| `1440×900` | `/title/douban:1291879` | PASS | desktop rail visible; bottom nav hidden |
| `1440×900` | `/person/derived:6buR5rO95piO` | PASS | desktop rail visible; bottom nav hidden |
| `1440×900` | `/health` | PASS | desktop rail visible; bottom nav hidden |
| `390×844` | `/tonight` | PASS | desktop rail hidden; bottom nav visible |
| `390×844` | `/tonight/anime-series` | PASS | desktop rail hidden; bottom nav visible |
| `390×844` | `/title/douban:1291879` | PASS | desktop rail hidden; bottom nav visible |
| `390×844` | `/person/derived:6buR5rO95piO` | PASS | desktop rail hidden; bottom nav visible |
| `390×844` | `/health` | PASS | desktop rail hidden; bottom nav visible |

For all `10/10` rows, `window.__CINESCOPE_AUDIT__()` returned empty `brokenImages`, `externalImages`, `overflowNodes`, and `focusFailures`; `emptyMain=false`; the document had no horizontal scrolling.

On `/tonight/anime-series`, visible input `更偏温暖、节奏舒缓` was submitted through **按原因换一批**. The page changed from batch `3` with five visible titles to batch `4` with status `下一批已就绪。` and an empty exhausted batch, proving a real server-backed transition rather than a visual-only change.

Refresh restoration used the visible route flow: the page was scrolled, navigated to Health through the rail, returned with browser Back, and then full-document reloaded. The route remained `/tonight/anime-series`; batch `4` remained active; all three shelf count/item projections were identical before and after reload; the route-max scroll position restored exactly at `738px` both before and after the full reload. The initial attempted `867px` position was clamped by the rendered page maximum and is not reported as a failed restoration.

No Cookie was entered. Visible Cookie fields stayed empty. The run did not read browser Cookie data, profiles, local/session storage, disk Cookie files, environment dumps, request headers, or hidden storage. The fixed session was prepared by writing a source-derived allowlisted UI-state projection; no browser storage value was read.

### Legacy rollback and data integrity

The legacy root loaded with title `CineScope Studio：豆瓣私人影视策展器`, heading `CineScope Studio`, non-empty content, and no V3 asset reference. Its visible Cookie textarea remained empty.

```text
SHA-256 before legacy: a31e07221893da3c1e18b33c7d26a67f5517906040b91c9cf011162680897670
SHA-256 after legacy:  a31e07221893da3c1e18b33c7d26a67f5517906040b91c9cf011162680897670
```

The hashes are identical, proving that selecting the legacy UI did not change `output/task8-acceptance-data/cinescope.db`.

### Performance/media provenance and evidence paths

Task 8 does not relabel historical timing as a fresh measurement. The retained performance and media conclusion comes from Task 6 commits `3e53e07061fd2213fc8f67580f6ab114c1186313` and `c427f4a535a0b913b34f5a5418a06afb80de2607`, recorded in `output/task6-acceptance/verification.json`. Its warm-cache route-content paint and settle gates passed. Real media coverage remains honestly unchanged: posters `0/24`, portraits `0/4`, backdrop `0/1`; designed CSS fallbacks are not counted as broken images and are not described as real media.

- Final machine evidence: `output/task8-acceptance/final-evidence.json`.
- Fresh route rows and restoration details: `output/task8-acceptance/browser-evidence.json`.
- Fresh screenshots: `output/task8-acceptance/screenshots/1440x900`, `output/task8-acceptance/screenshots/390x844`, and `output/task8-acceptance/screenshots/legacy`.
- Historical-only provenance is enumerated under `old_evidence_provenance` in the final machine evidence; those older JSON files are not substitutes for the Task 8 smoke matrix.
