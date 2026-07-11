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
