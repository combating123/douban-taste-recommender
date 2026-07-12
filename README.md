# CineScope Studio：豆瓣私人影视策展器

CineScope Studio 是本地运行的影视同步、口味分析和推荐工作台。它可以同步豆瓣“看过 / 想看”，用电影、电视剧、动漫候选池生成高分剧情优先的推荐海报墙。

项目坚持本地优先：Cookie 只用于本机请求豆瓣页面，不保存 Cookie，不写入缓存，不写入报告，也不会上传到外部服务。

## 快速启动

PowerShell：

```powershell
cd C:\Users\11616\douban-taste-recommender
.\run_app.ps1
```

打开浏览器：<http://127.0.0.1:7861>

不用脚本也可以：

```powershell
cd C:\Users\11616\douban-taste-recommender
$env:PYTHONPATH = "$PWD\src"
python -m douban_recommender.web
```

### V3 默认启动、首次同步与回滚

`run_app.ps1` 会直接启动 **V3 是默认界面**，不要求设置环境变量。打开 <http://127.0.0.1:7861> 后，先进入“健康与同步”完成**首次同步**：填写豆瓣主页 URL 或用户 ID；公开数据可用时 Cookie 留空，需要登录态时只在同步页的 Cookie 输入框手动粘贴你已有的 Cookie 字符串。

Cookie 只由用户输入，且只由可见输入获得；Cookie 只保存在 sessionStorage（当前标签页）和本次本机请求内，关闭标签页即失效。应用不读取浏览器 Profile、磁盘、环境转储或任何隐藏存储，也不会将 Cookie 写入数据库、缓存、日志或报告。

V3 与显式 legacy 回滚界面都只接受可见 Cookie 输入框中手动粘贴的 Cookie 字符串；不调用剪贴板读取，不解析整段请求头。多行文本、带字段名前缀的内容或其他说明文字会被拒绝。

如需临时回到旧界面，在启动前显式设置 `CINESCOPE_UI_VERSION=legacy`：

```powershell
$env:CINESCOPE_UI_VERSION = "legacy"
.\run_app.ps1
```

移除该变量或重新打开 PowerShell 后会恢复 V3 默认界面。

### 运行与维护

- 本机 HTTP 代理只配置端口，例如 `DOUBAN_RECOMMENDER_HTTP_PROXY=http://127.0.0.1:7890`；不要使用订阅地址。
- 可选服务的 API Key 通过环境变量由对应服务配置；不要把密钥写进 URL、命令历史或报告。
- 在“健康与同步”查看媒体健康；也可请求 `GET /api/v2/media/health` 查看媒体仓库状态。
- 需要清空缓存时，可在旧界面点击“清空缓存”，或向本机服务发送 `DELETE /api/cache`；这不会写入或恢复 Cookie。

## 推荐默认策略

- 想看：评分高，剧情好，叙事强，人物塑造扎实，电影/电视剧/动漫都可以。
- 避雷：电视剧古装，注水剧，低分狗血，粗制滥造。
- 范围：电影、电视剧、动漫默认全开。
- 数量：默认生成 120 条推荐，首页优先展示精选海报墙。

## Task 9：推荐会话与文档集成

### Command Lens 是什么

推荐页的 **Command Lens** 用自然语言和可编辑条件驱动推荐会话：你可以直接写“想看高分悬疑电影”“今天先不要古装剧”，也可以手动改条件。**本地确定性排序为事实源，语言模型只做可选结构化/解释**；也就是排序、计数、换批次都由本地规则决定，模型只负责把自然语言整理成结构化 intent，或给出可选说明文案。

- Command Lens 支持 **自然语言** 输入。
- Command Lens 支持 **可编辑条件**，改完即可重新生成。
- 没有显式配置模型 endpoint 时，整套推荐完全走本地规则。

### 三个独立频道与频道边界

系统始终拆成 **三个独立频道**：**电影 / 电视剧 / 动画剧集**。

- 电影频道：独立排序、独立换批次。
- 电视剧频道：独立排序、独立换批次，**电视剧默认古装降权**。
- 动画频道：语义上是“动画剧集”而不是泛指动画内容，**动漫仅动画剧集、排除动画电影**。

这三个频道互不挤占批次；一个频道换一批，不会推进另外两个频道。

### 三种数量一定要分开看

推荐页同时展示三种数量，必须严格区分：

| 名词 | 含义 | 你该怎么理解 |
| --- | --- | --- |
| 候选池 | 进入本地排序前/排序时可用的频道全集 | 来源可能很多，数量通常最大 |
| 条件命中 | 通过当前意图、过滤和降权后仍然可参与展示的条目数 | 这是“满足当前条件的可用库存” |
| 当前批次 | 当前屏幕这一批实际拿出来的条目 | 这是你此刻看到或准备切到的一屏 |

请不要把 `limit`、展示数、库存数混成一个概念。**`limit=160` 仅在未提供自定义候选时作为候选回填目标**；它**不是推荐会话上限、频道库存上限或当前批次数量**。`batch_size=24` 才控制当前页或当前屏幕的一批展示量；每个频道的 `pool_size` 由实际候选决定。提供自定义 candidates（`candidate_items` 或 `candidates_csv`）时不会按 `limit` 回填，**自定义 candidates 可使 `pool_size` 超过或不同于 `limit`**。**每频道独立换一批/上一批/耗尽恢复**：电影、电视剧、动画剧集都有各自的前进、回退与耗尽后恢复逻辑。

每个频道的 `batch_size` 会 clamp 到 `1..24`：传入大于 24 的值（如 `batch_size=30`）最多只会展示 24 条，而不是 30 条。较短的默认批次更适合视觉货架。

## 同步建议

如果你的豆瓣页面显示约 242 部看过、34 部想看，可以在同步面板填写：

- 期望看过：242
- 期望想看：34
- 最大页数：40

同步后查看完整度和每页诊断。如果抓取结果是 0 / 0，请先看诊断分类，再决定是否粘贴 Cookie。诊断会区分真实空页、需要登录、隐私权限、安全验证、页面有内容但解析失败等情况。

新版同步任务默认采用“自动抓取到末页”：空白分页、连续失败或明确登录拦截才会停止，250 页只是防止异常循环的高位安全阀，不是推荐数量限制。任务接口为：

- `POST /api/v2/sync/jobs`
- `GET /api/v2/sync/jobs/<job-id>`
- `POST /api/v2/sync/jobs/<job-id>/resume`

部分分页失败时可以从失败位置继续，已经成功的条目会作为种子保留。

## 使用方式

### 方式 A：网页界面

1. 打开本地网页。
2. 在“第一步：连接豆瓣”里输入豆瓣用户 ID 或主页链接。
3. Cookie 是可选项；公开数据够用时不用填。
4. 如需兜底，可以展开“没有抓取数据？粘贴 CSV”。
5. 在“第二步：确认口味”里保留默认高分剧情策略，或改成你当前想看的方向。
6. 在“第三步：查看推荐”里浏览海报墙，打开详情看推荐理由和避雷提示。

如果暂时不想直接抓取豆瓣数据，可以粘贴评分 CSV 和粘贴候选 CSV。网页端会优先使用粘贴候选 CSV；如果已经粘贴候选 CSV，就不会重复加入本地示例候选。

### 方式 B：命令行生成 HTML 报告

```powershell
cd C:\Users\11616\douban-taste-recommender
$env:PYTHONPATH = "$PWD\src"
python -m douban_recommender.cli `
  --ratings sample_data\ratings_sample.csv `
  --candidates sample_data\candidates_sample.csv `
  --like "评分高, 剧情好, 叙事强" `
  --dislike "电视剧古装, 注水剧" `
  --limit 30 `
  --output output\recommendations.html
```

## 推荐反馈作用域

反馈是 append-only 事件流，可以 **可撤销**，但不会偷偷重写旧记录。撤销会追加 undo 事件，而不是就地改历史。

| 反馈动作 | 推荐作用域 | 是否进入稳定口味 | 说明 |
| --- | --- | --- | --- |
| `want` / `watched` / `permanent` | permanent | 是 | 长期强化“想看/已看”偏好 |
| `not-tonight` / `tonight-candidate` / `session-only` | session-only | 否 | 只影响当前推荐会话，**session-only 不写入稳定口味** |
| `less` / `more` / `permanent-avoid` | permanent | 是 | 长期弱化/强化或永久避雷 |

为了方便核对，可以直接按这三组短语理解：want / watched / permanent；not-tonight / tonight-candidate / session-only；less / more / permanent-avoid。

接口事件名以 API 为准：`more` 对应 `more-like-this`，`less` 对应 `less-like-this`。`not-tonight`、`tonight-candidate` 只在当前 session 生效；页面刷新或新建会话后不会被当成稳定口味继承。

## V2 推荐 / 反馈 / Catalog API

下面这些接口都使用 **schema_version: 2**；POST body 必须显式带 `schema_version: 2`。参数不合法通常返回 **400**，资源不存在通常返回 **404**。

### 推荐会话 API

- `POST /api/v2/recommend/sessions`：创建推荐会话。
- `GET /api/v2/recommend/sessions/<session-id>`：恢复整个会话与三个频道状态。
- `POST /api/v2/recommend/sessions/<session-id>/batch`：某一频道换一批。
- `POST /api/v2/recommend/sessions/<session-id>/previous`：某一频道上一批。

最小 body 示例：

```json
{
  "schema_version": 2,
  "profile_key": "default",
  "rated_items": [],
  "candidates_csv": "title,media_type\n示例片,电影",
  "include_movies": true,
  "include_series": true,
  "include_anime": true,
  "fetch_douban": false,
  "use_sample_candidates": false,
  "like_terms": "评分高，剧情好，叙事强",
  "dislike_terms": "电视剧古装，注水剧",
  "batch_size": 24,
  "limit": 160
}
```

响应里可重点看每个频道的：`pool_size`、`matched_size`、`visible_size`、`batch`。这正对应上面的 **候选池 / 条件命中 / 当前批次**。

### 反馈 API

- `POST /api/v2/feedback`：记录反馈事件。
- `POST /api/v2/feedback/<event-id>/undo`：撤销某个反馈事件。

最小 body 示例：

```json
{
  "schema_version": 2,
  "profile_key": "default",
  "session_id": "session-1",
  "event_type": "not-tonight",
  "scope": "session",
  "item_key": "douban:1292052"
}
```

### Catalog API

- `GET /api/v2/library?state=watched&limit=20`
- `GET /api/v2/taste`
- `GET /api/v2/titles/<title-id>`
- `GET /api/v2/people/<person-id>`
- `GET /api/v2/universe?focus=<item-key>&limit=9`

Catalog API 也统一返回 `schema_version: 2`。

## 可选 OpenAI-compatible / Ollama 模型

语言模型是可选增强层，不是事实源。**仅显式 endpoint 才联网**；如果你没有配置 endpoint，或者配置后请求失败，系统会 **失败回退本地规则**。

- 默认本地候选 endpoint 探测值：`http://127.0.0.1:11434/v1/chat/completions`
- 兼容合法的 `http://127.0.0.1:11434/v1/responses`
- 也兼容标准 OpenAI-compatible chat/completions 协议
- **API key 不回显**，不会出现在响应体、错误文案或推荐结果里

PowerShell 示例：

```powershell
$env:PYTHONPATH = "$PWD\src"
python -c "from douban_recommender.language_adapter import detect_local_endpoint; print(detect_local_endpoint())"
```

如果你自己接服务端，请确保 endpoint 是干净的 HTTP/HTTPS 地址；不要带 query、fragment、用户名密码，也不要把密钥拼进 URL。

## CSV 字段支持

评分 CSV 不要求固定表头，程序会自动识别常见字段：

- 标题：`title` / `标题` / `片名` / `名称`
- 我的评分：`my_rating` / `我的评分` / `个人评分` / `星级` / `评分`
- 豆瓣评分：`douban_rating` / `豆瓣评分` / `平均评分`
- 类型标签：`genres` / `类型` / `分类` / `风格`
- 国家地区：`countries` / `国家/地区` / `地区` / `制片国家/地区`
- 导演：`directors` / `导演`
- 演员：`casts` / `主演` / `演员`
- 标签：`tags` / `标签` / `我的标签`
- 链接：`url` / `链接` / `豆瓣链接`
- 简介/短评：`summary` / `简介` / `短评` / `评论`

如果你的导出文件只有“标题 + 我的评分”，也能跑，但推荐会更依赖默认策略和你手动填写的口味说明。

## 直接抓取豆瓣数据

现在可以不借助外部导出工具，直接在本地网页里抓取豆瓣数据：

1. 启动应用：`.\run_app.ps1`
2. 打开 <http://127.0.0.1:7861>
3. 输入豆瓣用户 ID 或主页链接。
4. 如果公开数据够用，Cookie 可以留空。
5. 如果抓不到完整评分，再粘贴 Cookie 后重试。

Cookie 只用于本机请求豆瓣页面，不会保存到磁盘，不会写入报告，也不会上传到外部服务。

### Cookie 边界与主页链接

- **Cookie 只由可见输入获得**；程序不会主动抓浏览器登录态。
- Cookie **仅 sessionStorage/请求内存** 使用，且 sessionStorage 仅限当前标签页；同步请求发出后输入框与当前标签页会话都会保留该值，离开同步面板时只清空可见输入框。
- Cookie **不落盘不读取浏览器 Profile**，不会扫描密码、历史记录或浏览器用户资料目录。
- **主页 URL 不是 Cookie**；主页链接只用于解析用户 ID。
- **本地 HTTP 代理端口允许，不接收订阅地址**；支持 `http://127.0.0.1:<port>` 这种本机代理，不接受机场订阅 URL。

### 主页链接不是 Cookie

你复制的这种主页链接是正确的：

```text
https://www.douban.com/people/272042071/?_dtcc=1&_i=33953249Yxbr5m
```

应用会把它识别成用户 ID `272042071`。如果右侧提示“链接识别成功但仍需要 Cookie”，说明链接没错；只是豆瓣当前把“看过 / 想看”分页拦在登录态后面。主页链接不是 Cookie，不能替代你手动粘贴到同步页 Cookie 输入框中的 Cookie 字符串。

遇到这种情况，将你已有的 Cookie 字符串手动粘贴到同步页的 Cookie 输入框后重试。同步请求发出后，Cookie 会继续保留在当前同步面板的输入框和当前标签页的 sessionStorage 中，以便恢复未完成任务；离开或销毁同步面板时，可见输入框会清空，返回同步页时会从同一标签页的 sessionStorage 恢复，关闭标签页后该会话值失效。Cookie 只由可见输入获得；项目不会将 Cookie 写入数据库、磁盘、缓存、日志或报告，也不读取浏览器 Profile、请求头或任何隐藏存储。

## Cookie 获取教程

1. 启动 V3 并打开“健康与同步”。
2. 在可见的“Cookie（可选，当前标签页）”输入框中手动粘贴你已有的 Cookie 字符串。
3. 点击“开始自动同步”。
4. 需要继续未完成任务时，在同一个标签页返回同步页；输入框会从当前标签页 sessionStorage 恢复，可直接继续。

粘贴后 Cookie 只用于本机请求豆瓣页面；它只由可见输入获得，不会保存到磁盘，不会进入缓存，也不会出现在推荐报告里。

新版界面中 Cookie 只保存在当前标签页 sessionStorage，并且只在当前浏览器标签会话和本机同步请求内使用；关闭该标签后会话值失效。后端 SQLite、媒体缓存、任务响应和日志均不保存或回显 Cookie。

## 本地数据目录与可信媒体仓库

CineScope 的新版持久数据使用 SQLite 和内容哈希媒体仓库。可以用环境变量指定目录：

```powershell
$env:CINESCOPE_DATA_DIR = "D:\CineScopeData"
$env:PYTHONPATH = "$PWD\src"
python -m douban_recommender.web
```

未设置 `CINESCOPE_DATA_DIR` 时，Windows 默认使用 `%LOCALAPPDATA%\CineScope`。其中只保存非敏感片库、推荐会话、同步任务、身份映射和已经验证的媒体文件。

外部海报、背景和人物照片会先经过标题/年份/类型/人物身份校验，再校验 MIME、图片魔数、像素解码和尺寸。通过后按 SHA-256 保存，浏览器最终只读取 `/media/<hash>` 形式的本地资源。**本地媒体 `/media/*`、外链不交付、设计兜底、演员/导演图片状态与修复任务** 是新版媒体链路的核心原则：

- 前端最终消费的是本地 `/media/*` 资源，不直接把外部图片链接交付给浏览器。
- 校验失败、文件缺失或身份不确定时，返回 `designed-fallback` / `missing` 之类状态并显示**设计兜底**。
- 演员/导演人物图会暴露 `media_status`，你可以据此判断当前是 ready、missing 还是 designed-fallback。
- 媒体与人物图修复走后台任务，不会把外链直接塞回最终交付层。

媒体任务与健康状态：

- `POST /api/v2/media/jobs`
- `GET /api/v2/media/jobs/<job-id>`
- `GET /api/v2/media/health`

`/api/image-proxy` 继续作为旧界面的兼容接口；新版界面的最终目标是只消费经过验证的本地 `/media/` 资源。

## 海报加载、Clash / V2Ray 代理教程

页面会优先通过本地 `/api/image-proxy` 代理加载海报；如果豆瓣 CDN 返回反爬 HTML 或图片域名被网络拦截，系统会把这些条目送进“海报修复现场”，逐部尝试多源换源，而不是只显示一条无聊进度条。

当前海报源顺序：

1. 内置精选海报映射（避免高频条目缺图）。
2. TMDb API（可选，免费注册后填 v3 API Key）。
3. OMDb / IMDb 海报（可选，免费申请 API Key）。
4. TVMaze 免费剧集源（无需 Key，优先用于电视剧 / 欧美剧海报）。
5. AniList 免费动漫源（无需 Key，优先用于动漫剧集）。
6. Jikan / MyAnimeList 免费动漫源（无需 Key，动漫兜底）。
7. TMDb 公共搜索页。
8. 豆瓣精确搜索和实验性 Wikipedia 图源。

免费 API 入口：

- TMDb：<https://www.themoviedb.org/settings/api>
- OMDb：<https://www.omdbapi.com/apikey.aspx>

如果仍有设计封面，第三步页面会出现“缺图补救台”，可以：

- 再次多源搜索；
- 复制缺图标题；
- 导出缺图 CSV；
- 直接打开 TMDb / IMDb / TVMaze / AniList / MyAnimeList 搜索入口手动核对。

如果你的网络需要 Clash、V2Ray 或 v2rayN，请只配置本机 HTTP 代理端口，不要粘贴订阅地址。订阅地址属于敏感配置，不需要也不应该写入项目、日志、缓存或页面输入框。

PowerShell 示例：

```powershell
cd C:\Users\11616\douban-taste-recommender
$env:PYTHONPATH = "$PWD\src"
$env:DOUBAN_RECOMMENDER_HTTP_PROXY = "http://127.0.0.1:7890"
python -m douban_recommender.web
```

- Clash 常见 Mixed Port：`http://127.0.0.1:7890`
- V2Ray / v2rayN：开启 HTTP 代理或 mixed port 后填同样格式
- 不要粘贴订阅地址；项目只读取本机代理端口环境变量
- 也兼容常见环境变量：`HTTPS_PROXY`、`HTTP_PROXY`、`ALL_PROXY`

## 隐私与缓存

本地缓存目录：`output/cache/`。

缓存内容只包含非敏感数据，例如同步到的条目、同步诊断、候选池和推荐结果。Cookie 字段会被移除或脱敏。你可以在页面里点击“清空缓存”。

新版 SQLite 与可信媒体目录由 `CINESCOPE_DATA_DIR` 控制。代理只允许 `http://127.0.0.1:<port>` 形式的本地端口；不要粘贴代理订阅地址。

## 测试

README 针对本次推荐会话文档集成，至少应保证以下命令可直接运行：

```powershell
cd C:\Users\11616\douban-taste-recommender
$env:PYTHONPATH="$PWD\src"
$env:PYTHONDONTWRITEBYTECODE="1"
python -m unittest tests.test_readme tests.test_recommendation_api_v2 tests.test_catalog_api_v2 tests.test_language_adapter -v
python -m unittest discover -s tests -v
git diff --check
rg -n "Cookie.*(print|log)|api_key.*response" src tests
```

标准测试入口：

```powershell
cd C:\Users\11616\douban-taste-recommender
$env:PYTHONPATH="$PWD\src"
$env:PYTHONDONTWRITEBYTECODE="1"
python -m unittest discover -s tests -v
```

## 项目结构

```text
douban-taste-recommender/
  src/douban_recommender/
    crawler.py            # 豆瓣同步、解析和诊断
    database.py           # SQLite schema 与持久状态
    runtime_paths.py      # 用户数据目录解析
    sync_service.py       # 可恢复的后台同步任务
    identity_service.py   # 作品 / 人物跨源身份校验
    media/                # 图片验证、哈希仓库、来源适配和任务编排
    media_api.py          # /api/v2/media 与 /media 本地交付
    storage.py            # 本地非敏感缓存
    candidate_planner.py  # 电影 / 电视剧 / 动漫候选规划
    douban_sources.py     # 豆瓣公开候选源
    profiler.py           # 口味画像
    recommender.py        # 个性化打分、分区和理由生成
    web.py                # 本地 API 服务
    web_ui.py             # CineScope Studio 单页界面
    cli.py                # 命令行入口
  tests/
```
