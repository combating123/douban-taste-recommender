from __future__ import annotations

from .models import MediaItem, normalize_title


POSTER_URLS_BY_DOUBAN_ID: dict[str, str] = {
    "27010768": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2561439800.webp",  # 寄生虫
    "26842702": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2520095279.webp",  # 燃烧
    "1293182": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2173577632.webp",  # 十二怒汉
    "1296141": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2927451337.webp",  # 控方证人
    "21937445": "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p2158166535.webp",  # 辩护人
    "24733428": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2595591069.webp",  # 心灵奇旅
    "35465232": "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p2890906384.webp",  # 漫长的季节
    "33404425": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2609064048.webp",  # 隐秘的角落
    "2373195": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2886443948.webp",  # 绝命毒师
    "25897712": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2218944919.webp",  # 风骚律师
    "1418192": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p926249640.webp",  # 火线 第一季
    "35350437": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2869925687.webp",  # 我的解放日志
    "3430169": "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p2225808366.webp",  # 钢之炼金术师FA
    "23748525": "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p2602681134.webp",  # 进击的巨人
    "1424406": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2011424828.webp",  # 星际牛仔
    "1460915": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2330163082.webp",  # 混沌武士
    "1800597": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2242716237.webp",  # 虫师
    "4925398": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p1948151693.webp",  # 命运石之门
    "26677934": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2358698477.webp",  # 灵能百分百
    "36093351": "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p2897218476.webp",  # 葬送的芙莉莲
    "35366293": "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p2880400525.webp",  # 孤独摇滚！
    "35332568": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2631090442.webp",  # 奇巧计程车
    "3060542": "https://img2.doubanio.com/view/photo/s_ratio_poster/public/p2221083211.webp",  # 夏目友人帐
    "2340927": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p1995752943.webp",  # 怪化猫
    "35633650": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2896940977.webp",  # 坠落的审判
    "35712804": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2904961420.webp",  # 白日之下
    "35208463": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2901703469.webp",  # 三大队
    "35725869": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2901057189.webp",  # 年会不能停！
    "35209683": "https://img2.doubanio.com/view/photo/s_ratio_poster/public/p2899486451.webp",  # 河边的错误
    "35206444": "https://img2.doubanio.com/view/photo/s_ratio_poster/public/p2637459961.webp",  # 模范出租车
    "30468961": "https://img2.doubanio.com/view/photo/s_ratio_poster/public/p2576977981.webp",  # 想见你
    "35881324": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2900138920.webp",  # 以爱为营
}


PEOPLE_PHOTOS_BY_DOUBAN_ID: dict[str, dict[str, str]] = {
    "27010768": {  # 寄生虫
        "奉俊昊": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fb/Bong_Joon-ho_2017.jpg/330px-Bong_Joon-ho_2017.jpg",
        "宋康昊": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/df/Song_Gangho_2016.jpg/330px-Song_Gangho_2016.jpg",
        "李善均": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6f/Lee_Seon-gun_in_Oct_2018.png/330px-Lee_Seon-gun_in_Oct_2018.png",
    },
    "1296141": {  # 控方证人
        "比利·怀尔德": "https://upload.wikimedia.org/wikipedia/commons/d/d0/Billy_Wilder.jpg",
        "泰隆·鲍华": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/73/Tyrone_Power_-_still.jpg/330px-Tyrone_Power_-_still.jpg",
        "玛琳·黛德丽": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2d/Marlene_Dietrich_in_No_Highway_%281951%29_%28Cropped%29.png/330px-Marlene_Dietrich_in_No_Highway_%281951%29_%28Cropped%29.png",
    },
    "1418192": {  # 火线 第一季
        "克拉克·约翰森": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1c/Clark_Johnson.jpg/330px-Clark_Johnson.jpg",
        "多米尼克·韦斯特": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5a/Dominic_West_%286577113511%29_%28cropped%29.jpg/330px-Dominic_West_%286577113511%29_%28cropped%29.jpg",
        "约翰·道曼": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b2/John_Doman_2013_%28cropped_2%29.jpg/330px-John_Doman_2013_%28cropped_2%29.jpg",
    },
    "2373195": {  # 绝命毒师
        "文斯·吉里根": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3d/Vince_Gilligan_at_53rd_Saturn_Awards_2026-03.jpg/330px-Vince_Gilligan_at_53rd_Saturn_Awards_2026-03.jpg",
        "布莱恩·克兰斯顿": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b1/BryanCranston-byPhilipRomano.jpg/330px-BryanCranston-byPhilipRomano.jpg",
        "亚伦·保尔": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9a/Aaron_Paul_-_AMC_The_Grove_-_Ash.jpg/330px-Aaron_Paul_-_AMC_The_Grove_-_Ash.jpg",
    },
    "25897712": {  # 风骚律师
        "文斯·吉里根": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3d/Vince_Gilligan_at_53rd_Saturn_Awards_2026-03.jpg/330px-Vince_Gilligan_at_53rd_Saturn_Awards_2026-03.jpg",
        "鲍勃·奥登科克": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/84/Bob_Odenkirk_at_53rd_Saturn_Awards_2026-02.jpg/330px-Bob_Odenkirk_at_53rd_Saturn_Awards_2026-02.jpg",
    },
    "33404425": {  # 隐秘的角落
        "辛爽": "https://p1-tt.byteimg.com/origin/tos-cn-i-qvj2lq49k0/35423efd92cc4580a817f2021d67e6ff.jpg",
        "秦昊": "https://i.mydramalist.com/pr8qE_5_c.jpg",
        "王景春": "https://media.gettyimages.com/id/1186966482/photo/san-sebastian-spain-chinese-actor-wang-jingchun-poses-during-a-portrait-session-at-maria.jpg?s=612x612&w=gi&k=20&c=qZvKvwZTEbUyk6IEPxqbQSc55U0dj3S-6BrZPfuOZnc=",
        "荣梓杉": "https://media.gettyimages.com/id/1311831746/photo/shanghai-china-actor-rong-zishan-attends-2021-signs-of-the-times-awards-on-april-10-2021-in.jpg?s=612x612&w=gi&k=20&c=laMzh9nfS8ICovqcfrWshbWjA5E3avQtrMBQ72ix3Xg=",
    },
    "35465232": {  # 漫长的季节
        "辛爽": "https://p1-tt.byteimg.com/origin/tos-cn-i-qvj2lq49k0/35423efd92cc4580a817f2021d67e6ff.jpg",
        "秦昊": "https://i.mydramalist.com/pr8qE_5_c.jpg",
    },
    "35633650": {  # 坠落的审判
        "茹斯汀·特里耶": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/ce/AnatomyOfFallPicCent011123_%281_of_8%29_%2853327939769%29_%28cropped%29.jpg/330px-AnatomyOfFallPicCent011123_%281_of_8%29_%2853327939769%29_%28cropped%29.jpg",
        "桑德拉·惠勒": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/Sandra_H%C3%BCller_at_Berlinale_2026-6.jpg/330px-Sandra_H%C3%BCller_at_Berlinale_2026-6.jpg",
    },
    "35366293": {  # 孤独摇滚！
        "斋藤圭一郎": "https://media.themoviedb.org/t/p/w500/zlRQwhbblqGQudJV4CDycOVJSDH.jpg",
        "青山吉能": "https://cdn.umamusu.wiki/Yoshino_Aoyama_Portrait.jpg",
    },
}


def apply_curated_posters(items: list[MediaItem]) -> list[MediaItem]:
    for item in items:
        subject_id = str(item.douban_id or "").strip()
        if subject_id and not item.cover:
            item.cover = POSTER_URLS_BY_DOUBAN_ID.get(subject_id, "")
    return items


def apply_curated_people_photos(items: list[MediaItem]) -> list[MediaItem]:
    for item in items:
        subject_id = str(item.douban_id or "").strip()
        photo_map = PEOPLE_PHOTOS_BY_DOUBAN_ID.get(subject_id, {})
        if not photo_map:
            continue
        if not isinstance(item.raw, dict):
            item.raw = {}
        existing = item.raw.get("people_photos")
        merged = dict(existing) if isinstance(existing, dict) else {}
        for name, url in photo_map.items():
            if name and url and not merged.get(name):
                merged[name] = url
        if merged:
            item.raw["people_photos"] = merged
    return items


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
        cover=POSTER_URLS_BY_DOUBAN_ID.get(douban_id, ""),
        summary=summary,
        source="curated_seed",
        raw={"people_photos": dict(PEOPLE_PHOTOS_BY_DOUBAN_ID[douban_id])} if douban_id in PEOPLE_PHOTOS_BY_DOUBAN_ID else {},
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
        _item("钢之炼金术师 FULLMETAL ALCHEMIST", "动漫", 9.5, "3430169", ["动画", "剧情", "冒险"], ["日本"], ["入江泰浩"], ["朴璐美", "钉宫理惠"], ["动漫剧集", "热血", "成长", "世界观"], "长篇少年漫改里少见的高完成度：主线清晰、群像完整，主题和冒险推进都很扎实。", 2009),
        _item("进击的巨人", "动漫", 8.9, "23748525", ["动画", "剧情", "动作"], ["日本"], ["荒木哲郎"], ["梶裕贵", "石川由依", "井上麻里奈"], ["动漫剧集", "悬疑", "末世", "强情节"], "从生存压迫到世界真相层层展开，悬念、动作和人物立场变化都很有推进力。", 2013),
        _item("星际牛仔", "动漫", 9.6, "1424406", ["动画", "剧情", "科幻"], ["日本"], ["渡边信一郎"], ["山寺宏一", "石冢运升", "林原惠美"], ["动漫剧集", "科幻", "公路片", "爵士"], "单元剧、爵士乐和太空西部片气质融合得极漂亮，每集都有电影感。", 1998),
        _item("混沌武士", "动漫", 9.5, "1460915", ["动画", "动作", "冒险"], ["日本"], ["渡边信一郎"], ["中井和哉", "川澄绫子", "佐藤银平"], ["动漫剧集", "公路片", "风格化", "动作"], "江户、嘻哈和浪人公路片混搭，形式锋利但人物关系很稳。", 2004),
        _item("虫师", "动漫", 9.4, "1800597", ["动画", "剧情", "奇幻"], ["日本"], ["长滨博史"], ["中野裕斗", "土井美加"], ["动漫剧集", "治愈", "物哀", "单元剧"], "静谧、克制、带自然哲思的单元剧，适合想看高级叙事余味的人。", 2005),
        _item("命运石之门", "动漫", 9.3, "4925398", ["动画", "科幻", "悬疑"], ["日本"], ["佐藤卓哉", "滨崎博嗣"], ["宫野真守", "今井麻美", "花泽香菜"], ["动漫剧集", "时间循环", "悬疑", "人物"], "前期铺垫和后期回收很强，时间线机制与人物情感绑定得紧。", 2011),
        _item("灵能百分百", "动漫", 9.4, "26677934", ["动画", "剧情", "奇幻"], ["日本"], ["立川让"], ["伊藤节生", "樱井孝宏", "大塚明夫"], ["动漫剧集", "成长", "喜剧", "情绪表达"], "爆炸作画背后是非常温柔的成长叙事，热血但不空。", 2016),
        _item("葬送的芙莉莲", "动漫", 9.4, "36093351", ["动画", "剧情", "奇幻"], ["日本"], ["斋藤圭一郎"], ["种崎敦美", "冈本信彦", "东地宏树"], ["动漫剧集", "奇幻", "旅途", "物哀"], "把冒险后日谈拍成关于时间、记忆和关系的长线剧集，节奏舒展但情绪精准。", 2023),
        _item("孤独摇滚！", "动漫", 9.1, "35366293", ["动画", "喜剧", "音乐"], ["日本"], ["斋藤圭一郎"], ["青山吉能", "铃代纱弓", "水野朔"], ["动漫剧集", "音乐", "喜剧", "社恐"], "视觉演出极有创造力，把社恐、乐队和青春喜剧拍得鲜活又真诚。", 2022),
        _item("奇巧计程车", "动漫", 9.4, "35332568", ["动画", "剧情", "悬疑"], ["日本"], ["木下麦"], ["花江夏树", "饭田里穗", "木村良平"], ["动漫剧集", "悬疑", "群像", "黑色幽默"], "动物外壳下是结构精密的都市群像悬疑，线索回收很漂亮。", 2021),
        _item("夏目友人帐", "动漫", 9.4, "3060542", ["动画", "剧情", "奇幻"], ["日本"], ["大森贵弘"], ["神谷浩史", "井上和彦"], ["动漫剧集", "治愈", "妖怪", "情感"], "温柔但不甜腻的长期陪伴型剧集，单元故事和情绪累积都很耐看。", 2008),
        _item("怪化猫", "动漫", 9.4, "2340927", ["动画", "悬疑", "奇幻"], ["日本"], ["中村健治"], ["樱井孝宏", "田中理惠"], ["动漫剧集", "怪谈", "视觉风格", "悬疑"], "浮世绘美术、怪谈结构和心理揭示结合得很先锋，短小但密度很高。", 2007),
    ]


def backfill_missing_media_types(
    candidates: list[MediaItem],
    include_movies: bool = True,
    include_series: bool = True,
    include_anime: bool = True,
    minimum_per_type: int = 12,
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
        return apply_curated_people_photos(apply_curated_posters(list(candidates)))

    seen = {item.douban_id or normalize_title(item.title) for item in candidates if item.title or item.douban_id}
    out = list(candidates)
    for item in curated_seed_candidates():
        key = item.douban_id or normalize_title(item.title)
        if item.media_type in requested and counts.get(item.media_type, 0) < minimum_per_type and key not in seen:
            out.append(item)
            seen.add(key)
            counts[item.media_type] = counts.get(item.media_type, 0) + 1
    return apply_curated_people_photos(apply_curated_posters(out))
