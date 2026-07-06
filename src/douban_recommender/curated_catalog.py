from __future__ import annotations

from .models import MediaItem, normalize_title


def _item(
    title: str,
    media_type: str,
    rating: float,
    douban_id: str,
    genres: list[str],
    countries: list[str],
    directors: list[str],
    casts: list[str],
    tags: list[str],
    summary: str,
    year: int | None = None,
) -> MediaItem:
    return MediaItem(
        title=title,
        media_type=media_type,
        douban_rating=rating,
        year=year,
        genres=genres,
        countries=countries,
        directors=directors,
        casts=casts,
        tags=tags,
        url=f"https://movie.douban.com/subject/{douban_id}/",
        douban_id=douban_id,
        summary=summary,
        source="curated_seed",
    )


def curated_seed_candidates() -> list[MediaItem]:
    """Local-first high-quality seed pool used when public Douban discovery is blocked.

    The list intentionally contains no user data, no cookies, and no paid API dependency. It
    is a safety net so the app still has enough movie / series / anime candidates when Douban
    returns a security-check page or when the default sample CSV lacks a category.
    """

    return [
        _item("寄生虫", "电影", 8.8, "27010768", ["剧情", "犯罪"], ["韩国"], ["奉俊昊"], ["宋康昊", "李善均", "曹汝贞"], ["社会", "阶层", "黑色幽默"], "类型融合极强的社会寓言，叙事节奏和人物反转都很稳。", 2019),
        _item("燃烧", "电影", 8.1, "26842702", ["剧情", "悬疑"], ["韩国"], ["李沧东"], ["刘亚仁", "史蒂文·元", "全钟瑞"], ["文学改编", "暧昧", "心理"], "慢热但后劲极强的悬疑心理片，适合偏爱叙事余味的人。", 2018),
        _item("十二怒汉", "电影", 9.4, "1293182", ["剧情"], ["美国"], ["西德尼·吕美特"], ["亨利·方达", "马丁·鲍尔萨姆"], ["法庭", "群像", "经典"], "单一空间里完成高密度人物和观点碰撞，剧情张力极强。", 1957),
        _item("控方证人", "电影", 9.6, "1296141", ["剧情", "悬疑", "犯罪"], ["美国"], ["比利·怀尔德"], ["泰隆·鲍华", "玛琳·黛德丽"], ["法庭", "反转", "经典"], "经典法庭悬疑，反转精密、节奏干净。", 1957),
        _item("辩护人", "电影", 9.2, "21937445", ["剧情"], ["韩国"], ["杨宇硕"], ["宋康昊", "金英爱", "吴达洙"], ["现实主义", "法庭", "社会"], "情绪、人物和社会议题结合紧密，适合高分剧情取向。", 2013),
        _item("心灵奇旅", "电影", 8.7, "24733428", ["动画", "音乐", "奇幻"], ["美国"], ["彼特·道格特"], ["杰米·福克斯", "蒂娜·菲"], ["治愈", "人生", "音乐"], "用轻盈形式讨论人生意义，视觉和情绪都很成熟。", 2020),
        _item("漫长的季节", "电视剧", 9.4, "35465232", ["剧情", "悬疑", "犯罪"], ["中国大陆"], ["辛爽"], ["范伟", "秦昊", "陈明昊"], ["现实主义", "群像", "时间叙事"], "国产现实主义悬疑剧代表，人物弧光和结构都很强。", 2023),
        _item("隐秘的角落", "电视剧", 8.8, "33404425", ["剧情", "悬疑", "犯罪"], ["中国大陆"], ["辛爽"], ["秦昊", "王景春", "荣梓杉"], ["家庭", "犯罪", "心理"], "家庭、童年和犯罪阴影交织，短剧体量紧凑不注水。", 2020),
        _item("绝命毒师", "电视剧", 9.1, "2373195", ["剧情", "犯罪"], ["美国"], ["文斯·吉里根"], ["布莱恩·克兰斯顿", "亚伦·保尔"], ["人物弧光", "犯罪", "美剧"], "人物堕落曲线极完整，适合重剧情和人物塑造偏好。", 2008),
        _item("风骚律师", "电视剧", 9.3, "25897712", ["剧情", "犯罪"], ["美国"], ["文斯·吉里根"], ["鲍勃·奥登科克", "蕾亚·塞洪"], ["律政", "人物", "慢热"], "前传剧中少见的高完成度人物悲剧，慢热但扎实。", 2015),
        _item("火线 第一季", "电视剧", 9.4, "1418192", ["剧情", "犯罪"], ["美国"], ["克拉克·约翰森"], ["多米尼克·韦斯特", "约翰·道曼"], ["社会", "群像", "现实主义"], "城市系统、警匪和社会结构交织的顶级群像剧。", 2002),
        _item("我的解放日志", "电视剧", 9.0, "35350437", ["剧情"], ["韩国"], ["金锡允"], ["李民基", "金智媛", "孙锡久"], ["生活流", "治愈", "人物"], "慢热生活流群像，靠人物状态和台词打动人。", 2022),
        _item("千与千寻", "动漫", 9.4, "1291561", ["动画", "奇幻", "冒险"], ["日本"], ["宫崎骏"], ["柊瑠美", "入野自由"], ["成长", "想象力", "经典"], "世界观、情绪和成长主题高度统一的动画经典。", 2001),
        _item("机器人总动员", "动漫", 9.3, "2131459", ["动画", "科幻", "冒险"], ["美国"], ["安德鲁·斯坦顿"], ["本·贝尔特", "艾丽莎·奈特"], ["科幻", "环保", "爱情"], "几乎不用台词也能完成强叙事和情绪表达。", 2008),
        _item("疯狂动物城", "动漫", 9.2, "25662329", ["动画", "喜剧", "冒险"], ["美国"], ["拜伦·霍华德"], ["金妮弗·古德温", "杰森·贝特曼"], ["社会寓言", "喜剧", "悬疑"], "商业娱乐和社会寓言结合得很漂亮。", 2016),
        _item("寻梦环游记", "动漫", 9.1, "20495023", ["动画", "音乐", "奇幻"], ["美国"], ["李·昂克里奇"], ["安东尼·冈萨雷斯", "盖尔·加西亚·贝纳尔"], ["家庭", "音乐", "治愈"], "情绪完成度极高，音乐、家庭和死亡主题自然融合。", 2017),
        _item("头脑特工队", "动漫", 8.8, "10533913", ["动画", "喜剧", "冒险"], ["美国"], ["彼特·道格特"], ["艾米·波勒", "菲利丝·史密斯"], ["心理", "成长", "创意"], "把抽象情绪具象成叙事机制，概念和情感都成立。", 2015),
        _item("你的名字。", "动漫", 8.5, "26683290", ["动画", "爱情", "奇幻"], ["日本"], ["新海诚"], ["神木隆之介", "上白石萌音"], ["时间", "青春", "奇幻"], "视听冲击强，时间结构和青春情绪结合紧密。", 2016),
        _item("红辣椒", "动漫", 9.1, "1865703", ["动画", "科幻", "悬疑"], ["日本"], ["今敏"], ["林原惠美", "古谷彻"], ["梦境", "心理", "想象力"], "梦境、现实和身份交错，形式感和叙事密度都高。", 2006),
        _item("攻壳机动队", "动漫", 9.0, "1291936", ["动画", "科幻", "动作"], ["日本"], ["押井守"], ["田中敦子", "大塚明夫"], ["赛博朋克", "哲学", "科幻"], "赛博朋克经典，对身份、意识和技术的表达很先锋。", 1995),
        _item("天空之城", "动漫", 9.2, "1291583", ["动画", "奇幻", "冒险"], ["日本"], ["宫崎骏"], ["田中真弓", "横泽启子"], ["冒险", "蒸汽朋克", "经典"], "冒险感、音乐和世界观都很完整的宫崎骏代表作。", 1986),
        _item("龙猫", "动漫", 9.2, "1291560", ["动画", "家庭", "奇幻"], ["日本"], ["宫崎骏"], ["日高法子", "坂本千夏"], ["童年", "治愈", "自然"], "极简故事里有强烈情绪记忆点，治愈但不低幼。", 1988),
    ]


def backfill_missing_media_types(
    candidates: list[MediaItem],
    include_movies: bool = True,
    include_series: bool = True,
    include_anime: bool = True,
    minimum_per_type: int = 10,
) -> list[MediaItem]:
    requested = set()
    if include_movies:
        requested.add("电影")
    if include_series:
        requested.add("电视剧")
    if include_anime:
        requested.add("动漫")

    counts = {media_type: len([item for item in candidates if item.media_type == media_type]) for media_type in requested}
    if all(counts.get(media_type, 0) >= minimum_per_type for media_type in requested):
        return list(candidates)

    seen = {item.douban_id or normalize_title(item.title) for item in candidates if item.title or item.douban_id}
    out = list(candidates)
    for item in curated_seed_candidates():
        key = item.douban_id or normalize_title(item.title)
        if item.media_type in requested and counts.get(item.media_type, 0) < minimum_per_type and key not in seen:
            out.append(item)
            seen.add(key)
            counts[item.media_type] = counts.get(item.media_type, 0) + 1
    return out
