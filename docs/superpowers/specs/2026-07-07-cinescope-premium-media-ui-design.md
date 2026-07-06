# CineScope Premium Media UI Design

## 背景

当前 CineScope Studio 已能同步豆瓣、生成推荐、展示海报墙，但截图暴露出三个体验短板：

1. 豆瓣图片存在防盗链或失效时，推荐卡片会出现破图，视觉质量下降。
2. 推荐卡片和详情抽屉的信息密度不足，导演、演员、类型、年份、地区、剧情简介不够突出。
3. 推荐分区仍像普通标签列表，缺少世界级电影网站常见的沉浸式入口、横向胶片带、焦点 Hero、分类浏览。

## 设计参考

- Letterboxd：电影详情页强调 Synopsis、Cast、Crew、Details、Genres 与用户评论氛围。
- IMDb：标题页强调海报、剧情简介、导演、演员、年份、评分和可识别的元数据层级。
- MUBI：浏览页强调类型、国家、导演/演员维度和策展感。
- Netflix / 流媒体首页：使用 Hero 焦点内容、横向分类轨道、卡片 hover / focus 后展开信息。

## 目标体验

把推荐结果从“卡片列表”升级成“私人影视宇宙”：

- 顶部显示 `今日最值得看` Hero 焦点推荐，可轮播精选条目。
- 推荐结果分为 `精选`、`电影`、`电视剧`、`动漫`、`高分剧情`、`想看优先` 等轨道。
- 每张海报卡必须稳定可看：真实海报可用就显示；加载失败时自动切换为本地标题海报。
- 卡片下方直接露出类型、年份、豆瓣评分、导演/主演、短简介。
- 详情抽屉扩展为“媒体详情页”：封面、剧情简介、类型、导演、主演、推荐理由、风险提示、外链。
- 演员/导演没有照片时，用高级 initials avatar 占位；先保证信息结构完整，再考虑真实人物头像源。

## 数据策略

- `Recommendation.to_dict()` 保持原始字段输出，同时前端用 `directors`、`casts`、`genres`、`countries`、`year`、`summary` 渲染详情。
- 新增前端 helper：
  - `posterUrl(rec)`：优先返回封面 URL。
  - `posterFallback(title, mediaType)`：生成 SVG data URL 标题海报。
  - `safePosterImg(...)`：图片失败自动切换 SVG fallback。
  - `peopleAvatars(names, role)`：导演/演员 initials avatar。
  - `sectionItems(name)`：稳定生成分类轨道。
- 后端不保存 Cookie，不保存任何敏感数据。
- 不引入外部商业 API key，避免用户额外配置。

## UI 结构

推荐页由三层组成：

1. `heroShowcase`：沉浸式焦点推荐，显示大标题、评分、类型、导演/主演、剧情、理由、按钮。
2. `railWall`：横向分类轨道，每个轨道包含横向滚动卡片，类似流媒体首页。
3. `detailDrawer`：右侧详情抽屉，包含海报、元数据、剧情、导演/演员头像、推荐理由和避雷。

## 验收标准

- HTML 包含 `heroShowcase`、`railWall`、`media-rail`、`person-chip`、`posterFallback`、`onerror`。
- 推荐页必须有 `电影`、`电视剧`、`动漫` 三个分类入口。
- 海报加载失败时不能显示浏览器破图图标。
- 详情抽屉必须显示简介、类型、导演、演员、推荐理由、风险提示。
- 全量单元测试通过。
- Web smoke 可访问并包含 CineScope Studio 与新 UI 标记。
