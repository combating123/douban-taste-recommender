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
