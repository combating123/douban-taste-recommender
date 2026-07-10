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

## 推荐默认策略

- 想看：评分高，剧情好，叙事强，人物塑造扎实，电影/电视剧/动漫都可以。
- 避雷：电视剧古装，注水剧，低分狗血，粗制滥造。
- 范围：电影、电视剧、动漫默认全开。
- 数量：默认生成 120 条推荐，首页优先展示精选海报墙。

## 同步建议

如果你的豆瓣页面显示约 242 部看过、34 部想看，可以在同步面板填写：

- 期望看过：242
- 期望想看：34
- 最大页数：40

同步后查看完整度和每页诊断。如果抓取结果是 0 / 0，请先看诊断分类，再决定是否粘贴 Cookie。诊断会区分真实空页、需要登录、隐私权限、安全验证、页面有内容但解析失败等情况。

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

### 主页链接不是 Cookie

你复制的这种主页链接是正确的：

```text
https://www.douban.com/people/272042071/?_dtcc=1&_i=33953249Yxbr5m
```

应用会把它识别成用户 ID `272042071`。如果右侧提示“链接识别成功但仍需要 Cookie”，说明链接没错；只是豆瓣当前把“看过 / 想看”分页拦在登录态后面。主页链接不是 Cookie，不能替代浏览器 `Request Headers` 里的 Cookie。

遇到这种情况按页面里的 Cookie 教程复制 `Cookie:` 后面的整段内容再重试。同步请求发出后 Cookie 输入框会自动清空，项目不会把 Cookie 写入磁盘、日志、缓存或推荐报告。

## Cookie 获取教程

1. 打开浏览器并登录豆瓣。
2. 进入任意豆瓣页面，例如 `https://movie.douban.com/`。
3. 按 `F12` 打开开发者工具。
4. 选择 `Network / 网络`。
5. 刷新页面。
6. 点击任意 `movie.douban.com` 或 `www.douban.com` 请求。
7. 在右侧 `Headers / 标头` 中找到 `Request Headers`。
8. 复制其中 `Cookie: ` 后面的整段内容。
9. 粘贴到 CineScope Studio 的 Cookie 输入框。

粘贴后应用会在发起本机请求后清空输入框。Cookie 不会保存到磁盘，不会进入缓存，不会出现在推荐报告里。

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

## 测试

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
