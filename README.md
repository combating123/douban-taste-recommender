# 豆瓣口味影视推荐器

一个本地运行的小项目：导入你的豆瓣评分 CSV，分析你喜欢/不喜欢的影视口味，然后从候选库里推荐电影和电视剧。

项目思路：

1. **个人口味画像**：从你的高分/低分条目里提取类型、国家/地区、导演、演员、标签、关键词。
2. **豆瓣候选池**：可调用豆瓣电影公开的探索候选接口 `movie.douban.com/j/new_search_subjects` 和 Top250 页面，把豆瓣平台上已经排序过的候选内容拉下来。
3. **本地二次重排**：用你的口味画像重新打分，输出推荐理由和避雷点。

> 豆瓣内部推荐算法不是公开 API，所以本项目采用“豆瓣公开候选池 + 本地个性化重排”的方式，尽量贴近你的豆瓣口味。

## 快速运行

PowerShell：

```powershell
cd C:\Users\11616\douban-taste-recommender
.\run_app.ps1
```

或者不用脚本：

```powershell
cd C:\Users\11616\douban-taste-recommender
$env:PYTHONPATH = "$PWD\src"
python -m douban_recommender.web
```

打开浏览器：<http://127.0.0.1:7861>

## 使用方式

### 方式 A：网页界面

1. 打开本地网页。
2. 上传或粘贴你的豆瓣评分 CSV。
3. 填写“喜欢的口味”和“不喜欢的口味”。
4. 勾选“从豆瓣拉候选”。
5. 点击生成推荐。

### 方式 B：命令行生成 HTML 报告

```powershell
cd C:\Users\11616\douban-taste-recommender
$env:PYTHONPATH = "$PWD\src"
python -m douban_recommender.cli `
  --ratings sample_data\ratings_sample.csv `
  --candidates sample_data\candidates_sample.csv `
  --like "悬疑, 犯罪, 现实主义, 黑色幽默, 群像" `
  --dislike "甜宠, 狗血, 低幼, 恐怖血腥" `
  --fetch-douban `
  --limit 30 `
  --output output\recommendations.html
```

生成后打开：

```powershell
start output\recommendations.html
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

如果你的导出文件只有“标题 + 我的评分”，也能跑，但推荐会更依赖你手动填写的喜欢/不喜欢口味；字段越丰富，画像越准确。

## 项目结构

```text
douban-taste-recommender/
  src/douban_recommender/
    io.py              # CSV 读取和字段识别
    profiler.py        # 口味画像
    douban_sources.py  # 豆瓣公开候选源
    recommender.py     # 个性化打分和理由生成
    web.py             # 无依赖本地网页应用
    cli.py             # 命令行入口
    report.py          # HTML/CSV 报告导出
  sample_data/
    ratings_sample.csv
    candidates_sample.csv
  tests/
```

## 后续可扩展

- 接入你真实的豆瓣评分导出文件。
- 增加“已看排除”“想看优先”“冷门度偏好”。
- 增加更多豆瓣榜单/豆列候选源。
- 用 OpenAI API 对短评和剧情简介做语义画像。
