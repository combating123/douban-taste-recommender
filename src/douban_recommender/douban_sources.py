from __future__ import annotations

import html
import io
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
from dataclasses import dataclass, field
from typing import Iterable

from .candidate_planner import CandidateQuery
from .curated_catalog import is_curated_placeholder_person
from .io import extract_douban_id, parse_list
from .models import MediaItem, normalize_title
from .profiler import KNOWN_GENRES, TasteProfile

DOUBAN_EXPLORE_ENDPOINT = "https://movie.douban.com/j/new_search_subjects"
DOUBAN_SUBJECT_SUGGEST_ENDPOINT = "https://movie.douban.com/j/subject_suggest"
DOUBAN_REXXAR_SUBJECT_ENDPOINT = "https://m.douban.com/rexxar/api/v2/subject"
DOUBAN_REXXAR_SEARCH_ENDPOINT = "https://m.douban.com/rexxar/api/v2/search/subjects"
DOUBAN_REXXAR_MOVIE_ENDPOINT = "https://m.douban.com/rexxar/api/v2/movie"
DOUBAN_REXXAR_TV_ENDPOINT = "https://m.douban.com/rexxar/api/v2/tv"
THEMOVIEDB_SEARCH_ENDPOINT = "https://www.themoviedb.org/search"
TMDB_API_SEARCH_ENDPOINT = "https://api.themoviedb.org/3/search"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
OMDB_API_ENDPOINT = "https://www.omdbapi.com/"
IMDB_SUGGESTION_ENDPOINT = "https://v2.sg.media-imdb.com/suggestion"
IMDB_GRAPHQL_ENDPOINT = "https://api.graphql.imdb.com/"
TVMAZE_SHOW_SEARCH_ENDPOINT = "https://api.tvmaze.com/singlesearch/shows"
SUMMARY_TRANSLATION_VERSION = 2
WIKIPEDIA_API_ENDPOINT = "https://zh.wikipedia.org/w/api.php"
ANILIST_GRAPHQL_ENDPOINT = "https://graphql.anilist.co"
JIKAN_ANIME_SEARCH_ENDPOINT = "https://api.jikan.moe/v4/anime"
PEOPLE_PLACEHOLDER_IMAGE_MARKERS = (
    "personage-default",
    "celebrity-default",
    "default-avatar",
    "default_portrait",
)
POSTER_SEARCH_ALIASES: dict[str, list[str]] = {
    "社交网络": ["The Social Network"],
    "教父": ["The Godfather"],
    "七武士": ["Seven Samurai"],
    "切尔诺贝利": ["Chernobyl"],
    "白色强人": ["Big White Duel"],
    "火线 第一季": ["The Wire"],
    "奇巧计程车": ["Odd Taxi"],
    "模范出租车": ["Taxi Driver"],
    "十二怒汉": ["12 Angry Men"],
    "暗黑": ["Dark"],
    "我在他乡挺好的": ["Remembrance of Things Past"],
    "重版出来！": ["Sleepeeer Hit!"],
    "无间道": ["Infernal Affairs"],
    "甜蜜蜜": ["Comrades: Almost a Love Story"],
    "七宗罪": ["Se7en"],
    "冰血暴": ["Fargo"],
    "平原上的摩西": ["Why Try to Change Me Now"],
    "男亲女爱": ["War of the Genders"],
    "楚门的世界": ["The Truman Show"],
    "心跳漏一拍": ["Heartstopper"],
    "摇曳露营": ["Laid-Back Camp", "Yuru Camp"],
    "迷宫饭": ["Delicious in Dungeon"],
    "花牌情缘": ["Chihayafuru"],
    "紫罗兰永恒花园": ["Violet Evergarden"],
    "来自深渊": ["Made in Abyss"],
    "葬送的芙莉莲": ["Frieren: Beyond Journey's End"],
    "攻壳机动队 SAC": ["Ghost in the Shell: Stand Alone Complex"],
    "新世纪福音战士": ["Neon Genesis Evangelion"],
    "四月是你的谎言": ["Your Lie in April"],
    "吹响！上低音号": ["Sound! Euphonium"],
    "少女终末旅行": ["Girls' Last Tour"],
    "86 -不存在的战区-": ["86 EIGHTY-SIX"],
    "轻音少女": ["K-On!"],
    "比宇宙更远的地方": ["A Place Further Than the Universe", "Sora yori mo Tooi Basho"],
    "钢之炼金术师 FULLMETAL ALCHEMIST": ["Fullmetal Alchemist: Brotherhood", "Hagane no Renkinjutsushi: FULLMETAL ALCHEMIST"],
    "链锯人": ["Chainsaw Man"],
    "只有我不在的街道": ["ERASED"],
    "心理神探": ["Mindhunter"],
    "早间新闻": ["The Morning Show"],
    "安多": ["Andor"],
    "火线 第一季": ["The Wire"],
    "绝命毒师": ["Breaking Bad"],
    "风骚律师": ["Better Call Saul"],
    "牯岭街少年杀人事件": ["A Brighter Summer Day"],
    "老友记": ["Friends"],
    "去他妈的世界": ["The End of the F***ing World"],
    "去他*的世界": ["去他妈的世界", "The End of the F***ing World"],
    "人生切割术": ["Severance"],
    "王冠": ["The Crown"],
    "浴血黑帮": ["Peaky Blinders"],
    "万物生灵": ["All Creatures Great and Small"],
    "伦敦生活": ["Fleabag"],
    "办公室": ["The Office"],
    "真探": ["True Detective"],
    "傲骨贤妻": ["The Good Wife"],
    "9号秘事": ["Inside No. 9"],
    "纸牌屋": ["House of Cards"],
    "成瘾剂量": ["Dopesick"],
    "怪奇物语": ["Stranger Things"],
    "瑞克和莫蒂": ["Rick and Morty"],
    "马男波杰克": ["BoJack Horseman"],
    "探险活宝": ["Adventure Time"],
    "花园墙外": ["Over the Garden Wall"],
    "恶魔城": ["Castlevania"],
    "科拉传奇": ["The Legend of Korra"],
    "电脑线圈": ["Dennou Coil"],
    "昭和元禄落语心中": ["Showa Genroku Rakugo Shinju"],
    "心理测量者": ["PSYCHO-PASS"],
    "蓝眼武士": ["Blue Eye Samurai"],
    "3月的狮子": ["3-gatsu no Lion", "March comes in like a lion"],
    "少女歌剧 Revue Starlight": ["Shoujo Kageki Revue Starlight", "Revue Starlight"],
    "末日三问": ["Shuumatsu Nani Shitemasu ka", "WorldEnd"],
    "赛马娘 Road to the Top": ["Uma Musume Pretty Derby Road to the Top"],
    "Fate/stay night UBW": ["Fate/stay night: Unlimited Blade Works"],
    "PSYCHO-PASS 心理测量者": ["PSYCHO-PASS"],
}


STATIC_POSTER_URLS_BY_TITLE: dict[str, str] = {
    "社交网络": "https://media.themoviedb.org/t/p/w500/tAAXqX7nTMPJtXCJUVC03EuiTK0.jpg",
    "教父": "https://media.themoviedb.org/t/p/w500/y03tzUKvkRCYwJ5NWys4W4bnS9m.jpg",
    "七武士": "https://media.themoviedb.org/t/p/w500/trW7LvPSPzLzXjmuc05KNWYw0yf.jpg",
    "切尔诺贝利": "https://media.themoviedb.org/t/p/w500/2kjMfJSwwQqOq4o4idiZxbNxoYz.jpg",
    "白色强人": "https://media.themoviedb.org/t/p/w500/s4b6BfSPL81OzrgRoxyVe1AIiou.jpg",
    "火线 第一季": "https://media.themoviedb.org/t/p/w500/p9t6Jjt93opEwZ1wrvv03hdqhWh.jpg",
    "海街日记": "https://media.themoviedb.org/t/p/w500/cd78ie8CrDkLpXVP4R1N6Gy8IrD.jpg",
    "小偷家族": "https://media.themoviedb.org/t/p/w500/1B1LB0x9hb2RyKOghZwjKVEkfw6.jpg",
    "奇巧计程车": "https://media.themoviedb.org/t/p/w500/zMv1e9Nrq2yHfzmqmBIKf0XH4Gp.jpg",
    "模范出租车": "https://media.themoviedb.org/t/p/w500/iZLJRYS02AtXQhdVanXXiG7KpDl.jpg",
    "十二怒汉": "https://media.themoviedb.org/t/p/w500/9dCMeoXagMuIBe4eCuY4xyj0a9x.jpg",
    "暗黑": "https://media.themoviedb.org/t/p/w500/qQTf4L3HLnz4L6wMCGPhqdRPGUB.jpg",
    "我在他乡挺好的": "https://media.themoviedb.org/t/p/w500/s3n3f1FGqsuztzanZm2PFi9ZZvI.jpg",
    "重版出来！": "https://media.themoviedb.org/t/p/w500/r8QFWG11IJehj0Xt7oBOcVVLPbP.jpg",
    "无间道": "https://media.themoviedb.org/t/p/w500/zRZhWomkYnIwf8nfWMZIKgJ7j32.jpg",
    "甜蜜蜜": "https://media.themoviedb.org/t/p/w500/5zI3WI1qg5fuHxHVJNdGAo8Etr1.jpg",
    "七宗罪": "https://media.themoviedb.org/t/p/w500/e7J95YHcmLtyUtB1yojY76xQO90.jpg",
    "冰血暴": "https://media.themoviedb.org/t/p/w500/ck4OUAw65awqGc9ZYpbKAHUOqST.jpg",
    "平原上的摩西": "https://media.themoviedb.org/t/p/w500/aRByCc2xes5JvojMrPcrZRLVW77.jpg",
    "男亲女爱": "https://media.themoviedb.org/t/p/w500/aOnBdZbIhISlYFkvVCp8NLZ9qyL.jpg",
    "楚门的世界": "https://media.themoviedb.org/t/p/w500/b63DcASndfrQCGHx8Yc84ELH6iL.jpg",
    "心跳漏一拍": "https://media.themoviedb.org/t/p/w500/7eoUOODzupvoGHaB10HprIByGY1.jpg",
    "心理神探": "https://media.themoviedb.org/t/p/w500/4ggYACVMVPKqJEaILT5eISgqJey.jpg",
    "早间新闻": "https://media.themoviedb.org/t/p/w500/cfQiG7vE5yCqftnhNXu64f3qYLa.jpg",
    "安多": "https://media.themoviedb.org/t/p/w500/idHVYuWs8cB3eBtX2gd3yDYiF8Y.jpg",
    "地久天长": "https://media.themoviedb.org/t/p/w500/6JpqLXfLhBSRcL3f686WU0JZ4ft.jpg",
    "素媛": "https://media.themoviedb.org/t/p/w500/bnpEj2PGKzaeQfkhi9JRC4wkyRZ.jpg",
    "无人区": "https://media.themoviedb.org/t/p/w500/9aLI1tqUM5gWozSU16jg5tfh0BH.jpg",
    "完美的日子": "https://media.themoviedb.org/t/p/w500/uMlh117K3bsmH2QSi8cuwqXFErE.jpg",
    "罗生门": "https://media.themoviedb.org/t/p/w500/7S5ut0iDmuevbGc0hDBxFJLthEd.jpg",
    "继承之战": "https://media.themoviedb.org/t/p/w500/tgImKD6CdMWAyCT8AVEx0eelfBD.jpg",
    "生活大爆炸": "https://media.themoviedb.org/t/p/w500/9vVZDfKs5Iq8VuSKuyCZTIumdwa.jpg",
    "我的事说来话长": "https://media.themoviedb.org/t/p/w500/1BenyZWPQdGmYYJQc0WwKHtXohg.jpg",
    "牯岭街少年杀人事件": "https://media.themoviedb.org/t/p/w500/g5gMOcn0vFUITufKSxxL2WCyBIU.jpg",
    "花牌情缘": "https://media.themoviedb.org/t/p/w500/nUfL7xK5DjViiQAwHiRYlb6VMTE.jpg",
    "迷宫饭": "https://media.themoviedb.org/t/p/w500/xBQK95axIdaOmfsJE7PM5bnioym.jpg",
    "摇曳露营": "https://media.themoviedb.org/t/p/w500/cDWn009t5VTNBXAliflpm1RdNLO.jpg",
    "魔法少女小圆": "https://media.themoviedb.org/t/p/w500/9Leopb4OB9j9FkP5JNHRZZlPPdg.jpg",
    "紫罗兰永恒花园": "https://media.themoviedb.org/t/p/w500/55Psg9yxczJ0l5xgF3AVT8oidmq.jpg",
    "吹响！上低音号": "https://media.themoviedb.org/t/p/w500/zbtVKv6accSl0vKbjklgTXPpcC5.jpg",
    "来自深渊": "https://media.themoviedb.org/t/p/w500/mvsqo90yoawfkPvibQXkXeWEEoz.jpg",
    "葬送的芙莉莲": "https://media.themoviedb.org/t/p/w500/1TtrtRIwXz5BB0gXEl8zgBypl9c.jpg",
    "钢之炼金术师 FULLMETAL ALCHEMIST": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx5114-nSWCgQlmOMtj.jpg",
    "钢之炼金术师FA": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx5114-nSWCgQlmOMtj.jpg",
    "海盗战记": "https://cdn.myanimelist.net/images/anime/1500/103005l.jpg",
    "奇诺之旅": "https://cdn.myanimelist.net/images/anime/1763/95397l.jpg",
    "电脑线圈": "https://cdn.myanimelist.net/images/anime/5/12844l.jpg",
    "科拉传奇": "https://static.tvmaze.com/uploads/images/original_untouched/260/650489.jpg",
    "比宇宙更远的地方": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx99426-ti5BL69Ip3kZ.png",
    "去他妈的世界": "https://static.tvmaze.com/uploads/images/original_untouched/348/870850.jpg",
    "人生切割术": "https://static.tvmaze.com/uploads/images/original_untouched/548/1371406.jpg",
    "3月的狮子": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx21366-0wrYK0kjKeFn.jpg",
    "少女歌剧 Revue Starlight": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx98658-Xz8uliDO7dzZ.png",
    "末日三问": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx21860-lSIbYJtEbAXu.jpg",
    "赛马娘 Road to the Top": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx148370-db0LjJfaOCg9.jpg",
    "Fate/stay night UBW": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx19603-ycT0pyEgDVQu.jpg",
    "PSYCHO-PASS 心理测量者": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx13601-i42VFuHpqEOJ.jpg",
}


STATIC_POSTER_IDS_BY_TITLE: dict[str, str] = {
    "社交网络": "tmdb-movie-37799",
    "教父": "tmdb-movie-238",
    "七武士": "tmdb-movie-346",
    "切尔诺贝利": "tmdb-tv-87108",
    "白色强人": "tmdb-tv-90207",
    "火线 第一季": "tmdb-tv-1438",
    "海街日记": "tmdb-movie-315846",
    "小偷家族": "tmdb-movie-505192",
    "奇巧计程车": "tmdb-tv-116727",
    "模范出租车": "tmdb-tv-119769",
    "十二怒汉": "tmdb-movie-389",
    "暗黑": "tmdb-tv-70523",
    "我在他乡挺好的": "tmdb-tv-129417",
    "重版出来！": "tmdb-tv-67504",
    "无间道": "tmdb-movie-10775",
    "甜蜜蜜": "tmdb-movie-37185",
    "七宗罪": "tmdb-movie-807",
    "冰血暴": "tmdb-tv-60622",
    "平原上的摩西": "tmdb-tv-136440",
    "男亲女爱": "tmdb-tv-6262",
    "楚门的世界": "tmdb-movie-37165",
    "心跳漏一拍": "tmdb-tv-124834",
    "心理神探": "tmdb-tv-67744",
    "早间新闻": "tmdb-tv-90282",
    "安多": "tmdb-tv-83867",
    "钢之炼金术师 FULLMETAL ALCHEMIST": "anilist-5114",
    "比宇宙更远的地方": "anilist-99426",
    "去他妈的世界": "tvmaze-28866",
    "人生切割术": "tvmaze-44933",
    "3月的狮子": "anilist-21366",
    "少女歌剧 Revue Starlight": "anilist-98658",
    "末日三问": "anilist-21860",
    "赛马娘 Road to the Top": "anilist-148370",
    "Fate/stay night UBW": "anilist-19603",
    "PSYCHO-PASS 心理测量者": "anilist-13601",
}


POSTER_SEARCH_ALIASES.update({
    "记忆碎片": ["Memento"],
    "驾驶我的车": ["Drive My Car"],
    "兹山鱼谱": ["The Book of Fish"],
    "我们的父辈": ["Generation War", "Unsere Mütter, unsere Väter"],
    "爱，死亡和机器人": ["Love Death and Robots", "Love, Death & Robots"],
    "雾山五行": ["Fog Hill of Five Elements"],
    "中国奇谭": ["Yao Chinese Folktales", "Yao-Chinese Folktales", "Chinese Folktales"],
    "命运石之门": ["Steins Gate", "Steins;Gate"],
    "少女终末旅行": ["Girls Last Tour", "Girls' Last Tour"],
    "怪化猫": ["Mononoke"],
    "伍六七": ["Scissor Seven", "Wu Liuqi"],
    "去他*的世界": ["The End of the F***ing World"],
    "黑镜": ["Black Mirror"],
    "怪奇物语": ["Stranger Things"],
})

STATIC_POSTER_URLS_BY_TITLE.update({
    "记忆碎片": "https://m.media-amazon.com/images/M/MV5BMGQ3Y2Q4NjktN2E4Ny00Y2Q2LTliZDUtZTNiNjRhY2I0NGIyXkEyXkFqcGc@._V1_.jpg",
    "驾驶我的车": "https://m.media-amazon.com/images/M/MV5BOGE5ZWRhYjYtNzVkMS00ZGU3LTg2MTMtODYyMmJlMDMyZjU0XkEyXkFqcGc@._V1_.jpg",
    "兹山鱼谱": "https://m.media-amazon.com/images/M/MV5BNWYyMDkxY2ItNmRmMC00Y2ZmLTkwZGYtNDJiYmZhOGUzOGY0XkEyXkFqcGc@._V1_.jpg",
    "我们的父辈": "https://static.tvmaze.com/uploads/images/original_untouched/7/17646.jpg",
    "爱，死亡和机器人": "https://static.tvmaze.com/uploads/images/original_untouched/501/1253559.jpg",
    "雾山五行": "https://m.media-amazon.com/images/M/MV5BMTZmNmNmYmQtNTIxMi00MjJjLWE5N2UtODZhMmZhOGExOGQyXkEyXkFqcGc@._V1_.jpg",
    "中国奇谭": "https://m.media-amazon.com/images/M/MV5BODNhN2E5YjQtMTBlOC00NmIzLWI1ZmEtNGE4NjkzODhlM2Q2XkEyXkFqcGc@._V1_.jpg",
    "命运石之门": "https://cdn.myanimelist.net/images/anime/1935/127974l.jpg",
    "少女终末旅行": "https://cdn.myanimelist.net/images/anime/12/88321l.jpg",
    "怪化猫": "https://cdn.myanimelist.net/images/anime/3/20713l.jpg",
    "伍六七": "https://m.media-amazon.com/images/M/MV5BNDdhYTU2OTUtNjRiOS00MjQxLThlNzctZWEyY2Q3YTA2M2ZmXkEyXkFqcGc@._V1_.jpg",
})

STATIC_POSTER_IDS_BY_TITLE.update({
    "记忆碎片": "imdb-tt0209144",
    "驾驶我的车": "imdb-tt14039582",
    "兹山鱼谱": "imdb-tt14371900",
    "我们的父辈": "tvmaze-1224",
    "爱，死亡和机器人": "tvmaze-40329",
    "雾山五行": "imdb-tt12953630",
    "中国奇谭": "imdb-tt26007176",
    "命运石之门": "mal-9253",
    "少女终末旅行": "mal-35838",
    "怪化猫": "mal-2246",
    "伍六七": "imdb-tt10384610",
})

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Referer": "https://movie.douban.com/explore",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
}


@dataclass
class PosterSourceConfig:
    tmdb_api_key: str = ""
    omdb_api_key: str = ""
    enable_douban: bool = True
    enable_tmdb_html: bool = True
    enable_tmdb_api: bool = True
    enable_omdb: bool = True
    enable_tvmaze: bool = True
    enable_anilist: bool = True
    enable_jikan: bool = True
    enable_wikipedia: bool = False
    prefer_external_over_douban: bool = True


def _coerce_bool(value: object, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def poster_source_config_from_dict(data: dict | None) -> PosterSourceConfig:
    data = data or {}
    return PosterSourceConfig(
        tmdb_api_key=str(data.get("tmdb_api_key") or data.get("tmdbApiKey") or "").strip(),
        omdb_api_key=str(data.get("omdb_api_key") or data.get("omdbApiKey") or "").strip(),
        enable_douban=_coerce_bool(data.get("enable_douban", data.get("enableDouban")), True),
        enable_tmdb_html=_coerce_bool(data.get("enable_tmdb_html", data.get("enableTmdbHtml")), True),
        enable_tmdb_api=_coerce_bool(data.get("enable_tmdb_api", data.get("enableTmdbApi")), True),
        enable_omdb=_coerce_bool(data.get("enable_omdb", data.get("enableOmdb")), True),
        enable_tvmaze=_coerce_bool(data.get("enable_tvmaze", data.get("enableTvmaze")), True),
        enable_anilist=_coerce_bool(data.get("enable_anilist", data.get("enableAnilist")), True),
        enable_jikan=_coerce_bool(data.get("enable_jikan", data.get("enableJikan")), True),
        enable_wikipedia=_coerce_bool(data.get("enable_wikipedia", data.get("enableWikipedia")), False),
        prefer_external_over_douban=_coerce_bool(
            data.get("prefer_external_over_douban", data.get("preferExternalOverDouban")),
            True,
        ),
    )


@dataclass
class CandidateFetchReport:
    items: list[MediaItem] = field(default_factory=list)
    successful_queries: int = 0
    failed_queries: int = 0
    errors: list[str] = field(default_factory=list)


def fetch_candidates_from_plan(
    plan: list[CandidateQuery],
    fetcher=None,
    sleep_seconds: float = 0.15,
    max_consecutive_failures: int = 10,
) -> CandidateFetchReport:
    fetch = fetcher or fetch_explore
    report = CandidateFetchReport()
    seen: set[str] = set()
    consecutive_failures = 0
    for query in plan:
        try:
            rows = fetch(tags=query.tags, sort=query.sort, start=query.start, limit=query.limit)
            report.successful_queries += 1
            consecutive_failures = 0
        except Exception as exc:
            report.failed_queries += 1
            report.errors.append(f"{query.channel} {query.tags} start={query.start}: {exc}")
            rows = []
            consecutive_failures += 1
        for row in rows:
            if not row.media_type or row.media_type == "电影":
                row.media_type = query.media_type
            row.source = row.source or f"douban_plan:{query.channel}:{query.tags}"
            key = row.douban_id or row.title
            if key and key not in seen:
                report.items.append(row)
                seen.add(key)
        if sleep_seconds:
            time.sleep(sleep_seconds)
        if max_consecutive_failures and consecutive_failures >= max_consecutive_failures and not report.items:
            report.errors.append(f"已提前停止：连续 {consecutive_failures} 个豆瓣候选查询失败，改用本地精选候选池。")
            break
    return report


def fetch_douban_candidates(
    profile: TasteProfile,
    include_movies: bool = True,
    include_series: bool = True,
    per_query: int = 20,
    max_queries: int = 14,
    sorts: Iterable[str] = ("U", "R"),
    sleep_seconds: float = 0.15,
) -> list[MediaItem]:
    queries = build_queries(profile, include_movies=include_movies, include_series=include_series, max_queries=max_queries)
    candidates: list[MediaItem] = []
    seen: set[str] = set()
    for tags in queries:
        for sort in sorts:
            try:
                rows = fetch_explore(tags=tags, sort=sort, start=0, limit=per_query)
            except Exception:
                rows = []
            for row in rows:
                key = row.douban_id or row.title
                if key and key not in seen:
                    candidates.append(row)
                    seen.add(key)
            if sleep_seconds:
                time.sleep(sleep_seconds)
    if include_movies:
        try:
            for row in fetch_top250(max_pages=2):
                key = row.douban_id or row.title
                if key and key not in seen:
                    candidates.append(row)
                    seen.add(key)
        except Exception:
            pass
    return candidates


def build_queries(profile: TasteProfile, include_movies: bool = True, include_series: bool = True, max_queries: int = 14) -> list[str]:
    bases: list[str] = []
    if include_movies:
        bases.append("电影")
    if include_series:
        bases.append("电视剧")

    terms: list[str] = []
    for value, _ in profile.top_positive("genre", 10):
        if value and value not in terms:
            terms.append(value)
    for value, _ in profile.top_positive("tag", 10):
        if value in KNOWN_GENRES and value not in terms:
            terms.append(value)
    for term in profile.manual_likes:
        if term and term not in terms:
            terms.append(term)

    fallback = ["剧情", "悬疑", "犯罪", "喜剧", "科幻", "纪录片", "动画"]
    for term in fallback:
        if term not in terms:
            terms.append(term)

    queries: list[str] = []
    for base in bases:
        queries.append(base)
        for term in terms[:6]:
            queries.append(f"{base},{term}")
        if len(terms) >= 2:
            queries.append(f"{base},{terms[0]},{terms[1]}")
        if len(terms) >= 3:
            queries.append(f"{base},{terms[0]},{terms[2]}")
    out: list[str] = []
    seen: set[str] = set()
    for q in queries:
        if q not in seen:
            out.append(q)
            seen.add(q)
        if len(out) >= max_queries:
            break
    return out


def fetch_explore(tags: str, sort: str = "U", start: int = 0, limit: int = 20, fetcher=None) -> list[MediaItem]:
    params = {
        "sort": sort,
        "range": "0,10",
        "tags": tags,
        "start": start,
    }
    url = DOUBAN_EXPLORE_ENDPOINT + "?" + urllib.parse.urlencode(params)
    fetch = fetcher or http_get
    payload = fetch(url)
    data = json.loads(payload.decode("utf-8"))
    if data.get("msg") and not data.get("data"):
        raise RuntimeError(f"豆瓣探索接口返回风控或错误：{data.get('msg')}")
    tag_list = parse_list(tags)
    media_type = "电视剧" if any(t in {"电视剧", "美剧", "英剧", "日剧", "韩剧", "国产剧", "港剧", "台剧"} for t in tag_list) else "电影"
    query_tags = [t for t in tag_list if t not in {"电影", "电视剧"}]
    out: list[MediaItem] = []
    for row in data.get("data", [])[:limit]:
        rate = parse_float(row.get("rate"))
        out.append(MediaItem(
            title=row.get("title") or "",
            douban_rating=rate,
            media_type=media_type,
            genres=[t for t in query_tags if t in KNOWN_GENRES],
            tags=query_tags,
            directors=[str(x) for x in row.get("directors") or []],
            casts=[str(x) for x in row.get("casts") or []],
            url=(row.get("url") or "").replace("\\/", "/"),
            douban_id=str(row.get("id") or extract_douban_id(row.get("url") or "")),
            cover=(row.get("cover") or "").replace("\\/", "/"),
            source=f"douban_explore:{tags}:sort={sort}",
            raw=row,
        ))
    return out


def parse_subject_suggestions(payload: bytes | str, expected_title: str = "") -> list[MediaItem]:
    """Parse Douban subject_suggest rows, keeping only exact-title poster matches when requested."""

    text = payload.decode("utf-8", errors="ignore") if isinstance(payload, bytes) else str(payload or "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []

    expected_key = normalize_title(expected_title) if expected_title else ""
    out: list[MediaItem] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        title = clean_html(str(row.get("title") or ""))
        if not title:
            continue
        if expected_key and normalize_title(title) != expected_key:
            continue
        cover = html.unescape(str(row.get("img") or row.get("cover") or "")).replace("\\/", "/").strip()
        url = html.unescape(str(row.get("url") or "")).replace("\\/", "/").strip()
        if "?" in url:
            url = url.split("?", 1)[0]
        subject_id = str(row.get("id") or extract_douban_id(url) or "").strip()
        raw_type = str(row.get("type") or "").lower()
        media_type = "\u7535\u89c6\u5267" if raw_type in {"tv", "series"} or row.get("episode") else "\u7535\u5f71"
        year = None
        year_match = re.search(r"\d{4}", str(row.get("year") or ""))
        if year_match:
            try:
                year = int(year_match.group(0))
            except ValueError:
                year = None
        out.append(MediaItem(
            title=title,
            media_type=media_type,
            year=year,
            url=url,
            douban_id=subject_id,
            cover=cover,
            source="douban_subject_suggest",
            raw=row,
        ))
    return out


def _extract_js_object_assignment(page_html: str, marker: str) -> str:
    start = (page_html or "").find(marker)
    if start < 0:
        return ""
    brace_start = page_html.find("{", start)
    if brace_start < 0:
        return ""
    depth = 0
    in_string = False
    quote_char = ""
    escape = False
    for index in range(brace_start, len(page_html)):
        char = page_html[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote_char:
                in_string = False
            continue
        if char in {"'", '"'}:
            in_string = True
            quote_char = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return page_html[brace_start:index + 1]
    return ""


def _primary_search_title(value: str) -> str:
    text = clean_html(value).replace("\u200e", "").strip()
    text = re.sub(r"\s*\(\d{4}\)\s*$", "", text).strip()
    if not text:
        return ""
    return text.split()[0].strip()


def _normalized_title_identity_key(value: object) -> str:
    text = unicodedata.normalize("NFKC", clean_html(str(value or ""))).casefold()
    normalized = normalize_title(text.replace("\u200e", ""))
    return "".join(character for character in normalized if character.isalnum())


def _title_matches_expected(candidate_title: str, expected_title: str) -> bool:
    if not expected_title:
        return True
    candidate = clean_html(candidate_title).replace("\u200e", "").strip()
    expected = clean_html(expected_title).replace("\u200e", "").strip()
    candidate = re.sub(r"\s*\((?:19|20)\d{2}\)\s*$", "", candidate).strip()
    expected = re.sub(r"\s*\((?:19|20)\d{2}\)\s*$", "", expected).strip()
    candidate_key = _normalized_title_identity_key(candidate)
    expected_key = _normalized_title_identity_key(expected)
    if candidate_key and candidate_key == expected_key:
        return True
    if re.search(r"[\u3400-\u9fff]", expected):
        return normalize_title(_primary_search_title(candidate)) == normalize_title(expected)
    return False


def parse_subject_search_html(page_html: str, expected_title: str = "") -> list[MediaItem]:
    """Parse the static window.__DATA__ payload from Douban movie search pages."""

    payload = _extract_js_object_assignment(page_html or "", "window.__DATA__")
    if not payload:
        return []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    rows = data.get("items", []) if isinstance(data, dict) else []
    out: list[MediaItem] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("tpl_name") != "search_subject":
            continue
        raw_title = str(row.get("title") or "")
        if not _title_matches_expected(raw_title, expected_title):
            continue
        title = expected_title or _primary_search_title(raw_title)
        cover = html.unescape(str(row.get("cover_url") or row.get("cover") or "")).replace("\\/", "/").strip()
        url = html.unescape(str(row.get("url") or "")).replace("\\/", "/").strip()
        subject_id = str(row.get("id") or extract_douban_id(url) or "").strip()
        labels = " ".join(str(label.get("text") or "") for label in row.get("labels", []) if isinstance(label, dict))
        more_url = str(row.get("more_url") or "")
        media_type = "\u7535\u89c6\u5267" if "剧集" in labels or "is_tv:'1'" in more_url or 'is_tv:"1"' in more_url else "\u7535\u5f71"
        year = None
        year_match = re.search(r"\((\d{4})\)", raw_title) or re.search(r"\b(\d{4})\b", str(row.get("abstract") or ""))
        if year_match:
            try:
                year = int(year_match.group(1))
            except ValueError:
                year = None
        rating = None
        rating_data = row.get("rating")
        if isinstance(rating_data, dict):
            rating = parse_float(rating_data.get("value"))
        out.append(MediaItem(
            title=title,
            media_type=media_type,
            douban_rating=rating,
            year=year,
            url=url,
            douban_id=subject_id,
            cover=cover,
            source="douban_subject_search",
            raw=row,
        ))
    return out


def _tmdb_media_type(raw_type: str, expected_media_type: str = "") -> str:
    expected = str(expected_media_type or "").strip()
    if expected in {"电视剧", "动漫"}:
        return expected
    value = str(raw_type or "").lower()
    if value == "tv":
        return "电视剧"
    return "电影"


def _tmdb_high_resolution_image_url(value: str) -> str:
    url = html.unescape(str(value or "")).strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    if url.startswith("/t/p/"):
        url = "https://media.themoviedb.org" + url
    match = re.search(r"https://media\.themoviedb\.org/t/p/[^\"'\s,<>]+/([^/\"'\s,<>]+\.(?:jpg|jpeg|png|webp))", url, re.I)
    if match:
        return "https://media.themoviedb.org/t/p/w500/" + match.group(1)
    return url


def _extract_first_url_from_srcset(srcset: str) -> str:
    value = html.unescape(str(srcset or ""))
    candidates = re.findall(r"https?://[^\s,]+", value)
    if not candidates:
        candidates = re.findall(r"/t/p/[^\s,]+", value)
    return candidates[-1] if candidates else ""


def parse_themoviedb_search_html(
    page_html: str,
    expected_title: str = "",
    expected_media_type: str = "",
    expected_year: int | None = None,
) -> list[MediaItem]:
    """Parse public TMDb search HTML as a poster fallback when Douban image search is blocked.

    Only exact normalized title matches are accepted. This gives the UI a real poster source
    without reintroducing the earlier wrong-poster problem.
    """

    text = str(page_html or "")
    expected_key = normalize_title(expected_title) if expected_title else ""
    cards = re.split(r'<div[^>]+class="[^"]*\bcomp:media-card\b[^"]*"[^>]*>', text)
    out: list[MediaItem] = []
    for card in cards[1:]:
        card = card[: card.find('<div class="comp:media-card"')] if '<div class="comp:media-card"' in card else card
        media_match = re.search(r'data-media-type="([^"]+)"', card)
        raw_media_type = media_match.group(1) if media_match else ""
        if expected_media_type == "电影" and raw_media_type and raw_media_type != "movie":
            continue
        if expected_media_type in {"电视剧", "动漫"} and raw_media_type and raw_media_type != "tv":
            continue
        h2_match = re.search(r"<h2[^>]*>(.*?)</h2>", card, re.S | re.I)
        span_titles = []
        if h2_match:
            span_titles = [clean_html(part) for part in re.findall(r"<span[^>]*>(.*?)</span>", h2_match.group(1), re.S | re.I)]
        img_alt_match = re.search(r'<img[^>]+alt="([^"]*)"', card, re.S | re.I)
        alt_title = clean_html(html.unescape(img_alt_match.group(1))) if img_alt_match else ""
        title = next((part for part in span_titles if part and not part.startswith("(")), "") or alt_title
        if not title:
            continue
        if expected_key and normalize_title(title) != expected_key:
            continue
        year = None
        year_match = re.search(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", clean_html(card))
        if year_match:
            try:
                year = int(year_match.group(1))
            except ValueError:
                year = None
        if expected_year and (year is None or abs(int(expected_year) - year) > 1):
            continue
        srcset_match = re.search(r'<img[^>]+srcset="([^"]+)"', card, re.S | re.I)
        src_match = re.search(r'<img[^>]+src="([^"]+)"', card, re.S | re.I)
        cover = _tmdb_high_resolution_image_url(
            _extract_first_url_from_srcset(srcset_match.group(1) if srcset_match else "")
            or (src_match.group(1) if src_match else "")
        )
        if not cover:
            continue
        href_match = re.search(r'href="(/(movie|tv)/(\d+)[^"]*)"', card, re.S | re.I)
        tmdb_id = f"tmdb-{href_match.group(2)}-{href_match.group(3)}" if href_match else ""
        tmdb_url = "https://www.themoviedb.org" + html.unescape(href_match.group(1)) if href_match else ""
        out.append(MediaItem(
            title=expected_title or title,
            media_type=_tmdb_media_type(raw_media_type, expected_media_type),
            year=year,
            url=tmdb_url,
            douban_id=tmdb_id,
            cover=cover,
            source="themoviedb_search",
            raw={},
        ))
    return out


def fetch_themoviedb_suggestions(
    title: str,
    media_type: str = "",
    fetcher=None,
    timeout: int = 6,
    expected_year: int | None = None,
) -> list[MediaItem]:
    safe_title = str(title or "").strip()
    if not safe_title:
        return []
    aliases = POSTER_SEARCH_ALIASES.get(safe_title, [])
    queries = [safe_title] + [alias for alias in aliases if alias and alias != safe_title]
    fetch = fetcher or http_get
    for query in queries:
        url = THEMOVIEDB_SEARCH_ENDPOINT + "?" + urllib.parse.urlencode({"query": query})
        if fetcher is None:
            headers = dict(DEFAULT_HEADERS)
            headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            headers["Accept-Language"] = "zh-CN,zh;q=0.9,en;q=0.8"
            headers["Referer"] = "https://www.themoviedb.org/"
            request = urllib.request.Request(url, headers=headers)
            with build_url_opener().open(request, timeout=timeout) as response:
                payload = response.read()
        else:
            try:
                payload = fetch(url, accept_json=False)
            except TypeError:
                payload = fetch(url)
        text = payload.decode("utf-8", errors="ignore") if isinstance(payload, bytes) else str(payload or "")
        expected = query if query != safe_title else safe_title
        suggestions = parse_themoviedb_search_html(
            text,
            expected_title=expected,
            expected_media_type=media_type,
            expected_year=expected_year,
        )
        if not suggestions and query != safe_title:
            suggestions = parse_themoviedb_search_html(
                text,
                expected_title=safe_title,
                expected_media_type=media_type,
                expected_year=expected_year,
            )
        if suggestions:
            if query != safe_title:
                for item in suggestions:
                    item.title = safe_title
            return suggestions
    return []


def _tmdb_schema_payloads(page_html: str) -> list[dict]:
    payloads: list[dict] = []
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        str(page_html or ""),
        flags=re.S | re.I,
    ):
        raw = re.sub(r"^\s*/\*\s*<!\[CDATA\[\s*\*/", "", match.group(1).strip())
        raw = re.sub(r"/\*\s*\]\]>\s*\*/\s*$", "", raw).strip()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        values = value if isinstance(value, list) else [value]
        payloads.extend(row for row in values if isinstance(row, dict))
    return payloads


def _tmdb_public_image_url(value: object, size: str = "w1280") -> str:
    url = html.unescape(str(value or "")).replace("\\/", "/").strip()
    if url.startswith("//"):
        url = "https:" + url
    if url.startswith("/t/p/"):
        url = "https://media.themoviedb.org" + url
    match = re.search(
        r"https://(?:media\.themoviedb\.org|image\.tmdb\.org)/t/p/[^\"'\s,<>]+/([^/\"'\s,<>]+\.(?:jpg|jpeg|png|webp))",
        url,
        flags=re.I,
    )
    return f"https://media.themoviedb.org/t/p/{size}/{match.group(1)}" if match else ""


def parse_themoviedb_backdrop_html(page_html: bytes | str, limit: int = 8) -> list[str]:
    text = page_html.decode("utf-8", errors="ignore") if isinstance(page_html, bytes) else str(page_html or "")
    out: list[str] = []
    for markup in re.findall(r"<img\b[^>]*>", text, flags=re.S | re.I):
        class_name = first_match(r'\bclass=["\']([^"\']*)["\']', markup).lower()
        if "backdrop" not in class_name:
            continue
        source = (
            first_match(r'\bsrc=["\']([^"\']+)["\']', markup)
            or _extract_first_url_from_srcset(first_match(r'\bsrcset=["\']([^"\']+)["\']', markup))
        )
        url = _tmdb_public_image_url(source, "w1280")
        if url and url not in out:
            out.append(url)
        if len(out) >= max(0, int(limit)):
            break
    return out


def _tmdb_duration_minutes(value: object) -> int | None:
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?", str(value or "").strip(), flags=re.I)
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    total = hours * 60 + minutes
    return total or None


def _tmdb_directors(page_html: str) -> list[str]:
    out: list[str] = []
    for block in re.findall(r'<li[^>]+class=["\'][^"\']*\bprofile\b[^"\']*["\'][^>]*>.*?</li>', page_html, flags=re.S | re.I):
        role = clean_html(first_match(r'<p[^>]+class=["\'][^"\']*\bcharacter\b[^"\']*["\'][^>]*>(.*?)</p>', block))
        role_key = role.casefold()
        if role_key not in {"director", "directing", "导演", "creator", "series creator", "original series creator", "原创作者"}:
            continue
        name = clean_html(first_match(r"<a\b[^>]*>(.*?)</a>", block))
        if name and name not in out:
            out.append(name)
    return out


def _tmdb_people_cards(block_html: str, limit: int = 16) -> tuple[list[str], dict[str, str]]:
    names: list[str] = []
    photos: dict[str, str] = {}
    for block in re.findall(r"<li\b[^>]*>.*?</li>", str(block_html or ""), flags=re.S | re.I):
        name = clean_html(
            first_match(
                r'<p\b[^>]*>\s*<a\b[^>]+href=["\']/person/[^"\']+["\'][^>]*>(.*?)</a>',
                block,
            )
        )
        if not name:
            continue
        if name not in names:
            names.append(name)
        image_markup = first_match(r"(<img\b[^>]*>)", block)
        source = (
            _extract_first_url_from_srcset(first_match(r'\bsrcset=["\']([^"\']+)["\']', image_markup))
            or first_match(r'\bsrc=["\']([^"\']+)["\']', image_markup)
        )
        photo = _tmdb_high_resolution_image_url(source)
        if photo:
            photos.setdefault(name, photo)
        if len(names) >= max(1, int(limit)):
            break
    return names, photos


def _tmdb_top_billed_people(page_html: str, limit: int = 16) -> tuple[list[str], dict[str, str]]:
    match = re.search(
        r'id=["\']cast_scroller["\'][^>]*>\s*(<ol\b.*?</ol>)',
        str(page_html or ""),
        flags=re.S | re.I,
    )
    return _tmdb_people_cards(match.group(1), limit=limit) if match else ([], {})


def _tmdb_directing_crew(page_html: str, limit: int = 8) -> tuple[list[str], dict[str, str]]:
    text = str(page_html or "")
    names: list[str] = []
    photos: dict[str, str] = {}
    accepted_roles = {"director", "directing", "导演"}
    for heading in re.finditer(r"<h4\b[^>]*>(.*?)</h4>", text, flags=re.S | re.I):
        if clean_html(heading.group(1)).casefold() not in accepted_roles:
            continue
        list_match = re.search(r"<ol\b[^>]*>(.*?)</ol>", text[heading.end():], flags=re.S | re.I)
        if not list_match:
            continue
        for person_block in re.findall(r"<li\b[^>]*>.*?</li>", list_match.group(1), flags=re.S | re.I):
            role = clean_html(
                first_match(
                    r'<p\b[^>]+class=["\'][^"\']*\bepisode_count_crew\b[^"\']*["\'][^>]*>(.*?)</p>',
                    person_block,
                )
            ).strip()
            if role != "导演" and not re.fullmatch(r"Director(?:\s*\([^)]*\))?", role, flags=re.I):
                continue
            rows, row_photos = _tmdb_people_cards(person_block, limit=1)
            for name in rows:
                if name not in names:
                    names.append(name)
            photos.update({name: url for name, url in row_photos.items() if name not in photos})
            if len(names) >= max(1, int(limit)):
                break
        if names:
            break
    return names[: max(1, int(limit))], photos


def parse_themoviedb_detail_html(
    page_html: bytes | str,
    expected_title: str = "",
    expected_media_type: str = "",
    source_url: str = "",
    expected_year: int | None = None,
) -> list[MediaItem]:
    """Parse exact-title public TMDb detail metadata without requiring an API key."""
    text = page_html.decode("utf-8", errors="ignore") if isinstance(page_html, bytes) else str(page_html or "")
    schema = next(
        (
            row
            for row in _tmdb_schema_payloads(text)
            if str(row.get("@type") or "").casefold() in {"movie", "tvseries", "tvshow"}
        ),
        {},
    )
    title = clean_html(
        str(schema.get("name") or "")
        or first_match(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', text)
    )
    expected = str(expected_title or "").strip()
    if not title or (expected and normalize_title(title) != normalize_title(expected)):
        return []

    raw_type = str(schema.get("@type") or "").casefold()
    inferred_type = "电视剧" if raw_type in {"tvseries", "tvshow"} else "电影"
    media_type = str(expected_media_type or inferred_type).strip() or inferred_type
    if expected_media_type == "电影" and inferred_type != "电影":
        return []
    if expected_media_type in {"电视剧", "动漫"} and inferred_type != "电视剧":
        return []

    summary = clean_html(
        str(schema.get("description") or "")
        or first_match(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', text)
        or first_match(r'<div[^>]+class=["\'][^"\']*\boverview\b[^"\']*["\'][^>]*>.*?<p[^>]*>(.*?)</p>', text)
    )
    genres = [str(value).strip() for value in schema.get("genre", []) if str(value).strip()] if isinstance(schema.get("genre"), list) else []
    countries: list[str] = []
    country_rows = schema.get("countryOfOrigin") if isinstance(schema.get("countryOfOrigin"), list) else []
    for row in country_rows:
        name = str(row.get("name") or "").strip() if isinstance(row, dict) else str(row or "").strip()
        if name and name not in countries:
            countries.append(name)

    release_date = ""
    released = schema.get("releasedEvent") if isinstance(schema.get("releasedEvent"), list) else []
    for row in released:
        if isinstance(row, dict) and str(row.get("startDate") or "").strip():
            release_date = str(row["startDate"]).strip()
            break
    if not release_date:
        release_date = str(schema.get("startDate") or schema.get("dateCreated") or "").strip()
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", release_date or first_match(r'<span[^>]+class=["\'][^"\']*\brelease_date\b[^"\']*["\'][^>]*>(.*?)</span>', text))
    year = int(year_match.group(1)) if year_match else None
    if expected_year and (year is None or abs(int(expected_year) - year) > 1):
        return []

    og_images = [html.unescape(value).strip() for value in re.findall(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', text, flags=re.I)]
    cover = _tmdb_high_resolution_image_url(og_images[0] if og_images else schema.get("image"))
    stills: list[str] = []
    for value in og_images[1:]:
        url = _tmdb_public_image_url(value, "w1280")
        if url and url not in stills:
            stills.append(url)

    duration = _tmdb_duration_minutes(schema.get("duration"))
    casts, people_photos = _tmdb_top_billed_people(text)
    raw: dict[str, object] = {}
    if stills:
        raw["stills"] = stills
    if duration:
        raw["duration"] = duration
    if release_date:
        raw["release_date"] = release_date
    if people_photos:
        raw["people_photos"] = people_photos
    aggregate_rating = schema.get("aggregateRating") if isinstance(schema.get("aggregateRating"), dict) else {}
    rating_value = parse_float(aggregate_rating.get("ratingValue"))
    if rating_value is not None and rating_value > 0:
        raw["ratings"] = {"tmdb": rating_value}
    try:
        rating_count = int(str(aggregate_rating.get("ratingCount") or "").replace(",", ""))
    except (TypeError, ValueError):
        rating_count = 0
    if rating_count > 0:
        raw["rating_votes"] = {"tmdb": rating_count}
    match = re.search(r"/(movie|tv)/(\d+)", str(source_url or ""))
    provider_id = f"tmdb-{match.group(1)}-{match.group(2)}" if match else ""
    return [MediaItem(
        title=expected or title,
        media_type=media_type,
        year=year,
        genres=genres,
        countries=countries,
        directors=_tmdb_directors(text),
        casts=casts,
        url=str(source_url or "").strip(),
        douban_id=provider_id,
        cover=cover,
        summary=summary,
        source="themoviedb_detail",
        raw=raw,
    )]


def fetch_themoviedb_metadata_suggestions(
    title: str,
    media_type: str = "",
    fetcher=None,
    timeout: int = 8,
    expected_year: int | None = None,
) -> list[MediaItem]:
    safe_title = str(title or "").strip()
    if not safe_title:
        return []
    search_results = fetch_themoviedb_suggestions(
        safe_title,
        media_type=media_type,
        fetcher=fetcher,
        timeout=timeout,
        expected_year=expected_year,
    )
    if not search_results and expected_year:
        search_results = fetch_themoviedb_suggestions(
            safe_title,
            media_type=media_type,
            fetcher=fetcher,
            timeout=timeout,
            expected_year=None,
        )
    fetch = fetcher or http_get
    for search_result in search_results:
        detail_url = str(search_result.url or "").strip()
        if not detail_url:
            continue
        localized_url = detail_url + ("&" if "?" in detail_url else "?") + "language=zh-CN"
        try:
            try:
                payload = fetch(localized_url, accept_json=False)
            except TypeError:
                payload = fetch(localized_url)
        except Exception:
            continue
        details = parse_themoviedb_detail_html(
            payload,
            expected_title=safe_title,
            expected_media_type=media_type,
            source_url=detail_url,
            expected_year=expected_year,
        )
        if not details:
            continue
        detail = details[0]
        if not detail.cover:
            detail.cover = search_result.cover
        match = re.search(r"/(movie|tv)/(\d+)", detail_url)
        if match:
            cast_url = f"https://www.themoviedb.org/{match.group(1)}/{match.group(2)}/cast?language=zh-CN"
            try:
                try:
                    cast_payload = fetch(cast_url, accept_json=False)
                except TypeError:
                    cast_payload = fetch(cast_url)
                cast_text = (
                    cast_payload.decode("utf-8", errors="ignore")
                    if isinstance(cast_payload, bytes)
                    else str(cast_payload or "")
                )
                crew_directors, crew_photos = _tmdb_directing_crew(cast_text)
            except Exception:
                crew_directors, crew_photos = [], {}
            if crew_directors:
                detail.directors = list(dict.fromkeys([*crew_directors, *detail.directors]))
            if crew_photos:
                current_photos = detail.raw.get("people_photos") if isinstance(detail.raw.get("people_photos"), dict) else {}
                detail.raw["people_photos"] = {**current_photos, **crew_photos}
            media_panel_url = (
                f"https://www.themoviedb.org/{match.group(1)}/{match.group(2)}"
                "/remote/media_panel/backdrops?translate=false&language=zh-CN&item_count=8"
            )
            try:
                try:
                    backdrop_payload = fetch(media_panel_url, accept_json=False)
                except TypeError:
                    backdrop_payload = fetch(media_panel_url)
                extra_stills = parse_themoviedb_backdrop_html(backdrop_payload, limit=8)
            except Exception:
                extra_stills = []
            existing = detail.raw.get("stills") if isinstance(detail.raw.get("stills"), list) else []
            detail.raw["stills"] = list(dict.fromkeys([*existing, *extra_stills]))[:8]
        return [detail]
    return []


def _tmdb_api_media_kinds(media_type: str = "") -> list[str]:
    if media_type == "电影":
        return ["movie"]
    if media_type in {"电视剧", "动漫"}:
        return ["tv"]
    return ["movie", "tv"]


def _tmdb_api_title(row: dict, media_kind: str = "") -> str:
    if media_kind == "tv" or row.get("media_type") == "tv":
        return str(row.get("name") or row.get("original_name") or "").strip()
    return str(row.get("title") or row.get("original_title") or row.get("name") or "").strip()


def _tmdb_api_year(row: dict) -> int | None:
    date_value = str(row.get("release_date") or row.get("first_air_date") or "")
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", date_value)
    if not year_match:
        return None
    try:
        return int(year_match.group(1))
    except ValueError:
        return None


def parse_tmdb_api_results(payload: bytes | str | dict, expected_title: str = "", expected_media_type: str = "", media_kind: str = "") -> list[MediaItem]:
    if isinstance(payload, dict):
        data = payload
    else:
        text = payload.decode("utf-8", errors="ignore") if isinstance(payload, bytes) else str(payload or "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
    rows = data.get("results", []) if isinstance(data, dict) else []
    expected_key = normalize_title(expected_title) if expected_title else ""
    out: list[MediaItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("media_type") or media_kind or "").strip() or ("tv" if row.get("name") else "movie")
        if kind not in {"movie", "tv"}:
            continue
        if expected_media_type == "电影" and kind != "movie":
            continue
        if expected_media_type in {"电视剧", "动漫"} and kind != "tv":
            continue
        poster_path = str(row.get("poster_path") or "").strip()
        if not poster_path or poster_path == "None":
            continue
        candidate_titles = [
            _tmdb_api_title(row, kind),
            str(row.get("original_title") or ""),
            str(row.get("original_name") or ""),
        ]
        if expected_key and not any(normalize_title(title) == expected_key for title in candidate_titles if title):
            continue
        if not poster_path.startswith("/"):
            poster_path = "/" + poster_path
        title = expected_title or next((title for title in candidate_titles if title), "")
        tmdb_id = str(row.get("id") or "").strip()
        out.append(MediaItem(
            title=title,
            media_type=_tmdb_media_type(kind, expected_media_type),
            year=_tmdb_api_year(row),
            url=f"https://www.themoviedb.org/{kind}/{tmdb_id}" if tmdb_id else "",
            douban_id=f"tmdb-{kind}-{tmdb_id}" if tmdb_id else "",
            cover=f"{TMDB_IMAGE_BASE_URL}{poster_path}",
            source="tmdb_api",
            raw=row,
        ))
    return out


def fetch_tmdb_api_suggestions(
    title: str,
    media_type: str = "",
    api_key: str = "",
    fetcher=None,
    timeout: int = 6,
) -> list[MediaItem]:
    safe_title = str(title or "").strip()
    safe_key = str(api_key or "").strip()
    if not safe_title or not safe_key:
        return []
    aliases = POSTER_SEARCH_ALIASES.get(safe_title, [])
    queries = [safe_title] + [alias for alias in aliases if alias and alias != safe_title]
    fetch = fetcher or http_get
    for query in queries:
        for kind in _tmdb_api_media_kinds(media_type):
            params = {
                "api_key": safe_key,
                "query": query,
                "language": "zh-CN",
                "include_adult": "false",
            }
            url = f"{TMDB_API_SEARCH_ENDPOINT}/{kind}?" + urllib.parse.urlencode(params)
            if fetcher is None:
                headers = dict(DEFAULT_HEADERS)
                headers["Accept"] = "application/json"
                request = urllib.request.Request(url, headers=headers)
                with build_url_opener().open(request, timeout=timeout) as response:
                    payload = response.read()
            else:
                try:
                    payload = fetch(url, accept_json=True)
                except TypeError:
                    payload = fetch(url)
            expected = query if query != safe_title else safe_title
            suggestions = parse_tmdb_api_results(payload, expected_title=expected, expected_media_type=media_type, media_kind=kind)
            if suggestions:
                if query != safe_title:
                    for item in suggestions:
                        item.title = safe_title
                return suggestions
    return []


def parse_omdb_result(payload: bytes | str | dict, expected_title: str = "", expected_media_type: str = "") -> list[MediaItem]:
    if isinstance(payload, dict):
        data = payload
    else:
        text = payload.decode("utf-8", errors="ignore") if isinstance(payload, bytes) else str(payload or "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
    if not isinstance(data, dict) or str(data.get("Response") or "").lower() != "true":
        return []
    poster = str(data.get("Poster") or "").strip()
    if not poster or poster.upper() == "N/A" or not poster.startswith(("http://", "https://")):
        return []
    title = str(data.get("Title") or "").strip()
    if expected_title and title and normalize_title(title) != normalize_title(expected_title):
        return []
    raw_type = str(data.get("Type") or "").lower()
    media_type = "电视剧" if raw_type == "series" else "电影"
    if expected_media_type == "动漫":
        media_type = "动漫"
    elif expected_media_type in {"电影", "电视剧"} and media_type != expected_media_type:
        return []
    year = None
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", str(data.get("Year") or ""))
    if year_match:
        try:
            year = int(year_match.group(1))
        except ValueError:
            year = None
    imdb_id = str(data.get("imdbID") or "").strip()
    return [MediaItem(
        title=expected_title or title,
        media_type=media_type,
        year=year,
        url=f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else "",
        douban_id=f"imdb-{imdb_id}" if imdb_id else "",
        cover=poster,
        source="omdb_api",
        raw=data,
    )]


def fetch_omdb_suggestions(
    title: str,
    media_type: str = "",
    api_key: str = "",
    fetcher=None,
    timeout: int = 6,
) -> list[MediaItem]:
    safe_title = str(title or "").strip()
    safe_key = str(api_key or "").strip()
    if not safe_title or not safe_key:
        return []
    aliases = POSTER_SEARCH_ALIASES.get(safe_title, [])
    queries = [safe_title] + [alias for alias in aliases if alias and alias != safe_title]
    omdb_type = "movie" if media_type == "电影" else "series" if media_type in {"电视剧", "动漫"} else ""
    fetch = fetcher or http_get
    for query in queries:
        params = {"apikey": safe_key, "t": query, "plot": "short", "r": "json"}
        if omdb_type:
            params["type"] = omdb_type
        url = OMDB_API_ENDPOINT + "?" + urllib.parse.urlencode(params)
        if fetcher is None:
            headers = dict(DEFAULT_HEADERS)
            headers["Accept"] = "application/json"
            request = urllib.request.Request(url, headers=headers)
            with build_url_opener().open(request, timeout=timeout) as response:
                payload = response.read()
        else:
            try:
                payload = fetch(url, accept_json=True)
            except TypeError:
                payload = fetch(url)
        suggestions = parse_omdb_result(payload, expected_title=query, expected_media_type=media_type)
        if suggestions:
            if query != safe_title:
                for item in suggestions:
                    item.title = safe_title
            return suggestions
    return []


_IMDB_ID_RE = re.compile(r"^tt\d+$", re.IGNORECASE)
_IMDB_MOVIE_TYPES = {"feature", "movie", "short", "tvmovie", "tvspecial", "video"}
_IMDB_SERIES_TYPES = {"tvseries", "tvminiseries"}


def _imdb_identifier(value: object) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if _IMDB_ID_RE.fullmatch(candidate) else ""


def _imdb_year(value: object) -> int | None:
    if isinstance(value, dict):
        value = value.get("year")
    match = re.search(r"\b(19\d{2}|20\d{2})\b", str(value or ""))
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _imdb_media_type(value: object, expected_media_type: str = "") -> str:
    key = re.sub(r"[^a-z]", "", str(value or "").casefold())
    kind = "movie" if key in _IMDB_MOVIE_TYPES else "series" if key in _IMDB_SERIES_TYPES else ""
    expected = str(expected_media_type or "").strip()
    if expected == "电影":
        return "电影" if kind == "movie" else ""
    if expected == "电视剧":
        return "电视剧" if kind == "series" else ""
    if expected == "动漫":
        return "动漫" if kind in {"movie", "series"} else ""
    return "电视剧" if kind == "series" else "电影" if kind == "movie" else ""


def _imdb_cast_values(value: object) -> list[str]:
    values = value if isinstance(value, (list, tuple, set)) else re.split(r"[,;/|]", str(value or ""))
    names: list[str] = []
    for entry in values:
        if isinstance(entry, dict):
            entry = entry.get("name") or entry.get("text") or entry.get("l")
        name = clean_html(str(entry or "")).strip()
        if name and name not in names:
            names.append(name)
    return names


def _imdb_cast_matches(candidate_cast: list[str], expected_cast: Iterable[str] | None) -> bool:
    expected_names = [str(value or "").strip() for value in (expected_cast or []) if str(value or "").strip()]
    if not expected_names:
        return True
    candidate_keys = {_normalized_title_identity_key(value) for value in candidate_cast}
    expected_keys = {_normalized_title_identity_key(value) for value in expected_names}
    candidate_keys.discard("")
    expected_keys.discard("")
    return bool(candidate_keys & expected_keys)


def _imdb_image_url(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("url") or value.get("imageUrl")
    url = html.unescape(str(value or "")).replace("\\/", "/").strip()
    return url if url.startswith(("http://", "https://")) else ""


def parse_imdb_suggestion_results(
    payload: bytes | str | dict,
    expected_title: str = "",
    expected_year: int | None = None,
    expected_media_type: str = "",
    expected_cast: Iterable[str] | None = None,
) -> list[MediaItem]:
    data = _json_payload(payload)
    rows = data.get("d") if isinstance(data.get("d"), list) else []
    matches: list[MediaItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        imdb_id = _imdb_identifier(row.get("id"))
        title = clean_html(str(row.get("l") or row.get("title") or "")).strip()
        if not imdb_id or not title or not _title_matches_expected(title, expected_title):
            continue
        year = _imdb_year(row.get("y") or row.get("year"))
        if expected_year is not None and (year is None or abs(int(expected_year) - year) > 1):
            continue
        media_type = _imdb_media_type(row.get("qid") or row.get("q") or row.get("titleType"), expected_media_type)
        if expected_media_type and not media_type:
            continue
        candidate_cast = _imdb_cast_values(row.get("s") or row.get("stars"))
        if not _imdb_cast_matches(candidate_cast, expected_cast):
            continue
        image = row.get("i") if isinstance(row.get("i"), dict) else {}
        cover = _imdb_image_url(image)
        raw: dict[str, object] = {
            "provider_ids": {"imdb": imdb_id},
            "aliases": [title] if expected_title and normalize_title(title) != normalize_title(expected_title) else [],
        }
        matches.append(MediaItem(
            title=expected_title or title,
            media_type=media_type,
            year=year,
            casts=candidate_cast,
            url=f"https://www.imdb.com/title/{imdb_id}/",
            douban_id=f"imdb-{imdb_id}",
            cover=cover,
            source="imdb_suggestion",
            raw=raw,
        ))
    return matches


def _imdb_graphql_title_record(payload: bytes | str | dict) -> dict:
    data = _json_payload(payload)
    graph = data.get("data") if isinstance(data.get("data"), dict) else {}
    for key in ("title", "mainColumnData"):
        value = graph.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _imdb_landscape_url(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    url = _imdb_image_url(value)
    try:
        width = float(value.get("width") or 0)
        height = float(value.get("height") or 0)
    except (TypeError, ValueError):
        return ""
    if not url or width <= 0 or height <= 0 or width / height < 1.15:
        return ""
    return url


def parse_imdb_graphql_title(
    payload: bytes | str | dict,
    expected_id: str = "",
    expected_title: str = "",
    expected_year: int | None = None,
    expected_media_type: str = "",
) -> list[MediaItem]:
    record = _imdb_graphql_title_record(payload)
    if not record:
        return []
    imdb_id = _imdb_identifier(record.get("id"))
    required_id = _imdb_identifier(expected_id)
    if not imdb_id or (required_id and imdb_id != required_id):
        return []
    title_text = record.get("titleText") if isinstance(record.get("titleText"), dict) else {}
    title = clean_html(str(title_text.get("text") or record.get("title") or "")).strip()
    if not title or not _title_matches_expected(title, expected_title):
        return []
    year = _imdb_year(record.get("releaseYear") or record.get("year"))
    if expected_year is not None and (year is None or abs(int(expected_year) - year) > 1):
        return []
    title_type = record.get("titleType") if isinstance(record.get("titleType"), dict) else {}
    media_type = _imdb_media_type(title_type.get("id") or title_type.get("text") or record.get("titleType"), expected_media_type)
    if expected_media_type and not media_type:
        return []

    primary_image = record.get("primaryImage") if isinstance(record.get("primaryImage"), dict) else {}
    cover = _imdb_image_url(primary_image)
    stills: list[str] = []

    def append_landscape(image: object) -> None:
        url = _imdb_landscape_url(image)
        if url and url not in stills and len(stills) < 8:
            stills.append(url)

    images = record.get("images") if isinstance(record.get("images"), dict) else {}
    for edge in images.get("edges", []) if isinstance(images.get("edges"), list) else []:
        node = edge.get("node") if isinstance(edge, dict) and isinstance(edge.get("node"), dict) else edge
        append_landscape(node)

    episodes = record.get("episodes") if isinstance(record.get("episodes"), dict) else {}
    episode_rows = episodes.get("episodes") if isinstance(episodes.get("episodes"), dict) else episodes
    for edge in episode_rows.get("edges", []) if isinstance(episode_rows.get("edges"), list) else []:
        node = edge.get("node") if isinstance(edge, dict) and isinstance(edge.get("node"), dict) else {}
        append_landscape(node.get("primaryImage") if isinstance(node, dict) else None)

    ratings_summary = record.get("ratingsSummary") if isinstance(record.get("ratingsSummary"), dict) else {}
    rating = parse_float(ratings_summary.get("aggregateRating"))
    votes = None
    try:
        raw_votes = ratings_summary.get("voteCount")
        votes = int(raw_votes) if raw_votes is not None else None
    except (TypeError, ValueError):
        votes = None

    summary = ""
    plots = record.get("plots") if isinstance(record.get("plots"), dict) else {}
    for edge in plots.get("edges", []) if isinstance(plots.get("edges"), list) else []:
        node = edge.get("node") if isinstance(edge, dict) and isinstance(edge.get("node"), dict) else {}
        plot_text = node.get("plotText") if isinstance(node.get("plotText"), dict) else {}
        summary = clean_html(str(plot_text.get("plainText") or plot_text.get("text") or "")).strip()
        if summary:
            break

    raw: dict[str, object] = {"provider_ids": {"imdb": imdb_id}}
    if rating is not None and rating > 0:
        raw["ratings"] = {"imdb": rating}
    if votes is not None and votes >= 0:
        raw["rating_votes"] = {"imdb": votes}
    if stills:
        raw["stills"] = stills
    return [MediaItem(
        title=expected_title or title,
        media_type=media_type,
        year=year,
        url=f"https://www.imdb.com/title/{imdb_id}/",
        douban_id=f"imdb-{imdb_id}",
        cover=cover,
        source="imdb_graphql",
        summary=summary,
        raw=raw,
    )]


_IMDB_TITLE_QUERY = """
query CineScopeTitle($id: ID!) {
  title(id: $id) {
    id
    titleText { text }
    releaseYear { year }
    titleType { id text }
    ratingsSummary { aggregateRating voteCount }
    primaryImage { url width height }
    plots(first: 1) { edges { node { plotText { plainText } } } }
    images(first: 24) { edges { node { id url width height } } }
    episodes {
      episodes(first: 16) {
        edges { node { id primaryImage { url width height } } }
      }
    }
  }
}
"""


def _imdb_fetch_payload(url: str, fetcher=None, timeout: int = 6, data: bytes | None = None, headers: dict[str, str] | None = None):
    request_headers = dict(headers or {})
    if fetcher is None:
        request = urllib.request.Request(url, data=data, headers=request_headers, method="POST" if data is not None else "GET")
        with build_url_opener().open(request, timeout=max(1, int(timeout))) as response:
            return response.read()
    try:
        return fetcher(url, accept_json=True, data=data, headers=request_headers)
    except TypeError:
        try:
            return fetcher(url, accept_json=True)
        except TypeError:
            return fetcher(url)


def fetch_imdb_metadata_suggestions(
    title: str,
    media_type: str = "",
    expected_year: int | None = None,
    expected_cast: Iterable[str] | None = None,
    provider_id: str = "",
    fetcher=None,
    timeout: int = 6,
) -> list[MediaItem]:
    safe_title = clean_html(str(title or "")).strip()
    if not safe_title:
        return []
    aliases = [str(value).strip() for value in POSTER_SEARCH_ALIASES.get(safe_title, []) if str(value).strip()]
    title_candidates = [safe_title, *[value for value in aliases if normalize_title(value) != normalize_title(safe_title)]]
    imdb_id = _imdb_identifier(provider_id)
    suggestion_match: MediaItem | None = None

    if not imdb_id:
        for query in title_candidates:
            first = next((character.casefold() for character in query if character.isalnum()), "_")
            encoded = urllib.parse.quote(query, safe="")
            url = f"{IMDB_SUGGESTION_ENDPOINT}/{urllib.parse.quote(first, safe='')}/{encoded}.json"
            try:
                payload = _imdb_fetch_payload(
                    url,
                    fetcher=fetcher,
                    timeout=timeout,
                    headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
                )
            except Exception:
                continue
            matches = parse_imdb_suggestion_results(
                payload,
                expected_title=query,
                expected_year=expected_year,
                expected_media_type=media_type,
                expected_cast=expected_cast,
            )
            if matches:
                suggestion_match = matches[0]
                provider_ids = suggestion_match.raw.get("provider_ids") if isinstance(suggestion_match.raw.get("provider_ids"), dict) else {}
                imdb_id = _imdb_identifier(provider_ids.get("imdb"))
                break
    if not imdb_id:
        return []

    body = json.dumps({"query": _IMDB_TITLE_QUERY, "variables": {"id": imdb_id}}, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://www.imdb.com",
        "Referer": "https://www.imdb.com/",
        "User-Agent": "Mozilla/5.0",
    }
    try:
        payload = _imdb_fetch_payload(IMDB_GRAPHQL_ENDPOINT, fetcher=fetcher, timeout=timeout, data=body, headers=headers)
    except Exception:
        return [suggestion_match] if suggestion_match is not None else []
    for query in title_candidates:
        parsed = parse_imdb_graphql_title(
            payload,
            expected_id=imdb_id,
            expected_title=query,
            expected_year=expected_year,
            expected_media_type=media_type,
        )
        if parsed:
            for item in parsed:
                item.title = safe_title
                if suggestion_match and not item.cover:
                    item.cover = suggestion_match.cover
            return parsed
    return []


def _imdb_provider_id(item: MediaItem) -> str:
    raw = item.raw if isinstance(item.raw, dict) else {}
    provider_ids = raw.get("provider_ids") if isinstance(raw.get("provider_ids"), dict) else {}
    externals = raw.get("externals") if isinstance(raw.get("externals"), dict) else {}
    values = [
        provider_ids.get("imdb"),
        externals.get("imdb"),
        raw.get("imdb_id"),
        raw.get("imdbID"),
    ]
    douban_id = str(item.douban_id or "").strip()
    if douban_id.lower().startswith("imdb-"):
        values.append(douban_id[5:])
    for value in values:
        imdb_id = _imdb_identifier(value)
        if imdb_id:
            return imdb_id
    return ""


def parse_tvmaze_result(payload: bytes | str | dict, expected_title: str = "", expected_media_type: str = "") -> list[MediaItem]:
    if expected_media_type and expected_media_type not in {"\u7535\u89c6\u5267", "\u52a8\u6f2b"}:
        return []
    data = _json_payload(payload)
    if not isinstance(data, dict):
        return []
    title = str(data.get("name") or "").strip()
    expected_key = normalize_title(expected_title) if expected_title else ""
    if not title or (expected_key and normalize_title(title) != expected_key):
        return []
    image = data.get("image") if isinstance(data.get("image"), dict) else {}
    cover = str(image.get("original") or image.get("medium") or "").strip()
    if not cover.startswith(("http://", "https://")):
        return []
    year = None
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", str(data.get("premiered") or ""))
    if year_match:
        try:
            year = int(year_match.group(1))
        except ValueError:
            year = None
    tvmaze_id = str(data.get("id") or "").strip()
    embedded = data.get("_embedded") if isinstance(data.get("_embedded"), dict) else {}
    episodes = embedded.get("episodes") if isinstance(embedded.get("episodes"), list) else []
    stills: list[str] = []
    for episode in episodes:
        image_data = episode.get("image") if isinstance(episode, dict) and isinstance(episode.get("image"), dict) else {}
        still = str(image_data.get("original") or image_data.get("medium") or "").strip()
        if still.startswith(("http://", "https://")) and still not in stills:
            stills.append(still)
    raw = dict(data)
    provider_format = str(data.get("type") or "").strip()
    if provider_format:
        raw["provider_format"] = provider_format
    if stills:
        raw["stills"] = stills[:8]
    rating = data.get("rating") if isinstance(data.get("rating"), dict) else {}
    rating_value = parse_float(rating.get("average"))
    if rating_value is not None and rating_value > 0:
        raw["ratings"] = {"tvmaze": rating_value}
    directors: list[str] = []
    casts: list[str] = []
    people_photos: dict[str, str] = {}
    crew = embedded.get("crew") if isinstance(embedded.get("crew"), list) else []
    for credit in crew:
        if not isinstance(credit, dict):
            continue
        role = str(credit.get("type") or "").strip().casefold()
        if role not in {"creator", "director", "showrunner"}:
            continue
        person = credit.get("person") if isinstance(credit.get("person"), dict) else {}
        name = str(person.get("name") or "").strip()
        image_data = person.get("image") if isinstance(person.get("image"), dict) else {}
        photo = str(image_data.get("original") or image_data.get("medium") or "").strip()
        if name and name not in directors:
            directors.append(name)
        if name and photo.startswith(("http://", "https://")):
            people_photos.setdefault(name, photo)
    cast_rows = embedded.get("cast") if isinstance(embedded.get("cast"), list) else []
    for credit in cast_rows:
        person = credit.get("person") if isinstance(credit, dict) and isinstance(credit.get("person"), dict) else {}
        name = str(person.get("name") or "").strip()
        image_data = person.get("image") if isinstance(person.get("image"), dict) else {}
        photo = str(image_data.get("original") or image_data.get("medium") or "").strip()
        if name and name not in casts:
            casts.append(name)
        if name and photo.startswith(("http://", "https://")):
            people_photos.setdefault(name, photo)
        if len(casts) >= 16:
            break
    if people_photos:
        raw["people_photos"] = people_photos
    provider_ids: dict[str, str] = {}
    if tvmaze_id:
        provider_ids["tvmaze"] = tvmaze_id
    externals = data.get("externals") if isinstance(data.get("externals"), dict) else {}
    imdb_id = _imdb_identifier(externals.get("imdb"))
    if imdb_id:
        provider_ids["imdb"] = imdb_id
    raw["provider_ids"] = provider_ids
    return [MediaItem(
        title=expected_title or title,
        media_type=expected_media_type if expected_media_type in {"\u7535\u89c6\u5267", "\u52a8\u6f2b"} else "\u7535\u89c6\u5267",
        year=year,
        genres=[
            *([str(value).strip() for value in data.get("genres", []) if str(value).strip()] if isinstance(data.get("genres"), list) else []),
            *(["\u7eaa\u5f55\u7247"] if provider_format.casefold() == "documentary" else []),
        ],
        directors=directors,
        casts=casts,
        url=str(data.get("officialSite") or data.get("url") or "").strip(),
        douban_id=f"tvmaze-{tvmaze_id}" if tvmaze_id else "",
        cover=cover,
        source="tvmaze_api",
        summary=clean_html(str(data.get("summary") or "")),
        raw=raw,
    )]


def fetch_tvmaze_suggestions(
    title: str,
    media_type: str = "",
    fetcher=None,
    timeout: int = 6,
) -> list[MediaItem]:
    safe_title = str(title or "").strip()
    if not safe_title or media_type not in {"", "\u7535\u89c6\u5267", "\u52a8\u6f2b"}:
        return []
    aliases = POSTER_SEARCH_ALIASES.get(safe_title, [])
    queries = [safe_title] + [alias for alias in aliases if alias and alias != safe_title]
    fetch = fetcher or http_get
    for query_index, query in enumerate(queries):
        url = TVMAZE_SHOW_SEARCH_ENDPOINT + "?" + urllib.parse.urlencode([
            ("q", query),
            ("embed[]", "episodes"),
            ("embed[]", "cast"),
            ("embed[]", "crew"),
        ])
        if fetcher is None:
            headers = dict(DEFAULT_HEADERS)
            headers["Accept"] = "application/json"
            request = urllib.request.Request(url, headers=headers)
            try:
                with build_url_opener().open(request, timeout=timeout) as response:
                    payload = response.read()
            except urllib.error.HTTPError as error:
                status = int(error.code or 0)
                error.close()
                if status == 404 and query_index < len(queries) - 1:
                    continue
                raise
        else:
            try:
                payload = fetch(url, accept_json=True)
            except TypeError:
                payload = fetch(url)
        suggestions = parse_tvmaze_result(
            payload,
            expected_title=query,
            expected_media_type=media_type or "\u7535\u89c6\u5267",
        )
        if suggestions:
            if query != safe_title:
                for item in suggestions:
                    item.title = safe_title
            return suggestions
    return []


def _json_payload(payload: bytes | str | dict) -> dict:
    if isinstance(payload, dict):
        return payload
    text = payload.decode("utf-8", errors="ignore") if isinstance(payload, bytes) else str(payload or "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _rexxar_name_rows(value: object) -> list[str]:
    rows = value if isinstance(value, list) else []
    names: list[str] = []
    for row in rows:
        name = str(row.get("name") or "").strip() if isinstance(row, dict) else str(row or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _rexxar_image_url(value: object) -> str:
    url = html.unescape(str(value or "")).replace("\\/", "/").strip()
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return ""
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not (host == "doubanio.com" or host.endswith(".doubanio.com")):
        return ""
    candidates = douban_image_url_candidates(url)
    return candidates[0] if candidates else url


def is_placeholder_people_image_url(value: object) -> bool:
    url = str(value or "").strip().casefold()
    return bool(url) and any(marker in url for marker in PEOPLE_PLACEHOLDER_IMAGE_MARKERS)


def douban_image_url_candidates(value: object) -> list[str]:
    url = html.unescape(str(value or "")).replace("\\/", "/").strip()
    if not url:
        return []
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return []
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not (host == "doubanio.com" or host.endswith(".doubanio.com")):
        return []
    path = parsed.path
    if "/view/photo/" in path:
        path = re.sub(r"/view/photo/(?:large|normal|small|[lms])/", "/view/photo/l/", path, count=1)
    elif "/view/celebrity/" not in path:
        return []
    candidates: list[str] = []
    for image_host in ("img1.doubanio.com", "img2.doubanio.com", "img3.doubanio.com"):
        candidate = urllib.parse.urlunsplit(("https", image_host, path, "", ""))
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def parse_douban_rexxar_search(payload: bytes | str | dict) -> list[MediaItem]:
    """Parse numeric movie/TV subjects from Douban's mobile search response.

    Search results are intentionally not accepted as identity proof on their
    own. Callers must fetch the subject detail and verify title aliases/year
    before merging any metadata or visuals.
    """

    data = _json_payload(payload)
    subjects = data.get("subjects") if isinstance(data.get("subjects"), dict) else {}
    rows = subjects.get("items") if isinstance(subjects.get("items"), list) else []
    out: list[MediaItem] = []
    seen: set[str] = set()
    for row in rows:
        target = row.get("target") if isinstance(row, dict) and isinstance(row.get("target"), dict) else {}
        subject_id = str(target.get("id") or "").strip()
        title = str(target.get("title") or "").strip()
        uri = str(target.get("uri") or "").strip()
        if not subject_id.isdigit() or not title or subject_id in seen:
            continue
        if not re.search(r"/(?:movie|tv)/" + re.escape(subject_id) + r"(?:$|[/?#])", uri):
            continue
        seen.add(subject_id)
        year = None
        try:
            year = int(target.get("year")) if target.get("year") else None
        except (TypeError, ValueError):
            year = None
        rating = target.get("rating") if isinstance(target.get("rating"), dict) else {}
        rating_value = parse_float(rating.get("value"))
        out.append(MediaItem(
            title=title,
            media_type="\u7535\u89c6\u5267" if f"/tv/{subject_id}" in uri else "\u7535\u5f71",
            year=year,
            douban_rating=rating_value,
            vote_count=int(rating.get("count")) if str(rating.get("count") or "").isdigit() else None,
            url=f"https://movie.douban.com/subject/{subject_id}/",
            douban_id=subject_id,
            cover=_rexxar_image_url(target.get("cover_url")),
            source="douban_rexxar_search",
            raw={"search_target": dict(target)},
        ))
    return out


def fetch_douban_rexxar_search_candidates(
    title: str,
    fetcher=None,
    timeout: int = 8,
    count: int = 10,
) -> list[MediaItem]:
    safe_title = str(title or "").strip()
    if not safe_title:
        return []
    url = DOUBAN_REXXAR_SEARCH_ENDPOINT + "?" + urllib.parse.urlencode({
        "q": safe_title,
        "type": "movie",
        "start": 0,
        "count": max(1, min(20, int(count))),
    })
    headers = dict(DEFAULT_HEADERS)
    headers.update({"Accept": "application/json", "Referer": "https://m.douban.com/movie/"})
    if fetcher is not None:
        try:
            payload = fetcher(url, accept_json=True, headers=headers)
        except TypeError:
            try:
                payload = fetcher(url, accept_json=True)
            except TypeError:
                payload = fetcher(url)
    else:
        request = urllib.request.Request(url, headers=headers)
        with build_url_opener().open(request, timeout=max(1, int(timeout))) as response:
            payload = response.read()
    return parse_douban_rexxar_search(payload)


def _first_rexxar_image(image: object) -> str:
    payload = image if isinstance(image, dict) else {}
    for size in ("large", "normal", "small"):
        value = payload.get(size)
        if isinstance(value, dict):
            value = value.get("url")
        url = _rexxar_image_url(value)
        if url:
            return url
    return ""


def parse_douban_rexxar_photos(payload: bytes | str | dict, limit: int = 8) -> list[str]:
    data = _json_payload(payload)
    rows = data.get("photos") if isinstance(data.get("photos"), list) else []
    photos: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = _first_rexxar_image(row.get("image"))
        if url and url not in photos:
            photos.append(url)
        if len(photos) >= max(0, int(limit)):
            break
    return photos


def parse_douban_rexxar_celebrities(payload: bytes | str | dict) -> dict[str, str]:
    data = _json_payload(payload)
    photos: dict[str, str] = {}
    for field in ("directors", "actors"):
        rows = data.get(field) if isinstance(data.get(field), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            names = [
                str(row.get("name") or "").strip(),
                str(row.get("latin_name") or "").strip(),
            ]
            avatar = row.get("avatar") if isinstance(row.get("avatar"), dict) else {}
            url = _rexxar_image_url(avatar.get("large") or avatar.get("normal") or avatar.get("small"))
            if not url or is_placeholder_people_image_url(url):
                continue
            for name in names:
                if name and name not in photos:
                    photos[name] = url
    return photos


def parse_douban_rexxar_credit_names(payload: bytes | str | dict) -> tuple[list[str], list[str]]:
    data = _json_payload(payload)
    groups: list[list[str]] = []
    for field in ("directors", "actors"):
        names: list[str] = []
        rows = data.get(field) if isinstance(data.get(field), list) else []
        for row in rows:
            name = str(row.get("name") or "").strip() if isinstance(row, dict) else ""
            if name and name not in names:
                names.append(name)
        groups.append(names)
    return groups[0], groups[1]


def _normalized_person_key(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(character for character in text if character.isalnum())


def _map_rexxar_credit_photo_aliases(detail: MediaItem, photos: dict[str, str]) -> dict[str, str]:
    expanded = dict(photos)
    aliases = [
        (name, _normalized_person_key(name), url)
        for name, url in photos.items()
        if _normalized_person_key(name) and str(url or "").startswith(("http://", "https://"))
    ]
    for credit_name in [*(detail.directors or []), *(detail.casts or [])]:
        clean_name = str(credit_name or "").strip()
        if not clean_name or clean_name in expanded:
            continue
        credit_key = _normalized_person_key(clean_name)
        if not credit_key:
            continue
        matching_urls = {
            url
            for _alias, alias_key, url in aliases
            if credit_key == alias_key
            or (min(len(credit_key), len(alias_key)) >= 5 and (credit_key in alias_key or alias_key in credit_key))
        }
        if len(matching_urls) == 1:
            expanded[clean_name] = next(iter(matching_urls))
    return expanded


def _rexxar_duration_minutes(value: object) -> int | None:
    rows = value if isinstance(value, list) else [value]
    for row in rows:
        match = re.search(r"(\d{1,3})\s*分钟", str(row or ""))
        if match:
            minutes = int(match.group(1))
            if 0 < minutes < 1000:
                return minutes
    return None


def _rexxar_release_date(value: object) -> str:
    rows = value if isinstance(value, list) else [value]
    for row in rows:
        match = re.search(r"\b((?:19|20)\d{2}-\d{2}-\d{2})\b", str(row or ""))
        if match:
            return match.group(1)
    return ""


def parse_douban_rexxar_subject(payload: bytes | str | dict) -> MediaItem:
    data = _json_payload(payload)
    title = str(data.get("title") or "").strip()
    subject_id = str(data.get("id") or "").strip()
    rating = data.get("rating") if isinstance(data.get("rating"), dict) else {}
    rating_value = parse_float(rating.get("value"))
    vote_count = None
    try:
        vote_count = int(rating.get("count")) if rating.get("count") is not None else None
    except (TypeError, ValueError):
        vote_count = None
    year = None
    try:
        year = int(data.get("year")) if data.get("year") else None
    except (TypeError, ValueError):
        year = None
    genres = [str(value).strip() for value in data.get("genres", []) if str(value).strip()] if isinstance(data.get("genres"), list) else []
    is_tv = bool(data.get("is_tv")) or str(data.get("subtype") or "").lower() in {"tv", "tvshow"}
    media_type = "动漫" if is_tv and "动画" in genres else "电视剧" if is_tv else "电影"
    aliases: list[str] = []
    for value in [data.get("original_title"), *(data.get("aka") if isinstance(data.get("aka"), list) else [])]:
        alias = str(value or "").strip()
        if alias and alias != title and alias not in aliases:
            aliases.append(alias)
    raw: dict[str, object] = {
        "provider_ids": {"douban": subject_id} if subject_id else {},
        "ratings": {"douban": rating_value} if rating_value is not None else {},
        "rating_votes": {"douban": vote_count} if vote_count is not None else {},
    }
    if aliases:
        raw["aliases"] = aliases
    original_title = str(data.get("original_title") or "").strip()
    if original_title:
        raw["original_title"] = original_title
    duration = _rexxar_duration_minutes(data.get("durations"))
    if duration:
        raw["duration"] = duration
    release_date = _rexxar_release_date(data.get("pubdate") or data.get("release_date"))
    if release_date:
        raw["release_date"] = release_date
    for key in ("comment_count", "review_count"):
        try:
            value = int(data.get(key))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            raw[key] = value
    cover = _rexxar_image_url(data.get("cover_url"))
    if not cover:
        pic = data.get("pic") if isinstance(data.get("pic"), dict) else {}
        cover = _rexxar_image_url(pic.get("large") or pic.get("normal"))
    return MediaItem(
        title=title,
        douban_rating=rating_value,
        vote_count=vote_count,
        year=year,
        media_type=media_type,
        genres=genres,
        countries=[str(value).strip() for value in data.get("countries", []) if str(value).strip()] if isinstance(data.get("countries"), list) else [],
        languages=[str(value).strip() for value in data.get("languages", []) if str(value).strip()] if isinstance(data.get("languages"), list) else [],
        directors=_rexxar_name_rows(data.get("directors")),
        casts=_rexxar_name_rows(data.get("actors")),
        url=str(data.get("url") or (f"https://movie.douban.com/subject/{subject_id}/" if subject_id else "")).strip(),
        douban_id=subject_id,
        cover=cover,
        summary=str(data.get("intro") or "").strip(),
        source="douban_rexxar",
        raw=raw,
    )


def _fetch_douban_rexxar_json(url: str, subject_id: str, fetcher=None, timeout: int = 8) -> dict:
    headers = dict(DEFAULT_HEADERS)
    headers.update({
        "Accept": "application/json",
        "Referer": f"https://m.douban.com/movie/subject/{subject_id}/",
    })
    if fetcher is not None:
        try:
            payload = fetcher(url, accept_json=True, headers=headers)
        except TypeError:
            try:
                payload = fetcher(url, accept_json=True)
            except TypeError:
                payload = fetcher(url)
        return _json_payload(payload)
    request = urllib.request.Request(url, headers=headers)
    with build_url_opener().open(request, timeout=max(1, int(timeout))) as response:
        return _json_payload(response.read())


def fetch_douban_rexxar_detail(item: MediaItem, fetcher=None, timeout: int = 8) -> MediaItem | None:
    subject_id = str(item.douban_id or extract_douban_id(item.url) or "").strip()
    if not subject_id.isdigit():
        return None
    detail_base = f"{DOUBAN_REXXAR_SUBJECT_ENDPOINT}/{subject_id}"
    try:
        subject_payload = _fetch_douban_rexxar_json(detail_base, subject_id, fetcher, timeout)
    except Exception:
        return None
    detail = parse_douban_rexxar_subject(subject_payload)
    if not detail.title or detail.douban_id != subject_id:
        return None
    expected_titles = _public_metadata_queries(item, limit=12)
    detail_aliases = detail.raw.get("aliases") if isinstance(detail.raw, dict) else []
    accepted_titles = [detail.title, *(detail_aliases if isinstance(detail_aliases, list) else [])]
    if expected_titles and not any(
        _title_matches_expected(candidate, expected)
        for candidate in accepted_titles
        for expected in expected_titles
    ):
        return None
    if item.year and detail.year and abs(int(item.year) - int(detail.year)) > 1:
        return None

    media_endpoint = (
        DOUBAN_REXXAR_TV_ENDPOINT
        if detail.media_type in {"电视剧", "动漫"}
        else DOUBAN_REXXAR_MOVIE_ENDPOINT
    )
    media_base = f"{media_endpoint}/{subject_id}"
    urls = {
        "photos": f"{media_base}/photos?type=S&start=0&count=8&sortby=like",
        "celebrities": f"{media_base}/celebrities",
    }
    payloads: dict[str, dict] = {"subject": subject_payload}
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="douban-rexxar") as executor:
        futures = {
            executor.submit(_fetch_douban_rexxar_json, url, subject_id, fetcher, timeout): name
            for name, url in urls.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                payloads[name] = future.result()
            except Exception:
                payloads[name] = {}
    stills = parse_douban_rexxar_photos(payloads.get("photos", {}), limit=8)
    if stills:
        detail.raw["stills"] = stills
    celebrity_payload = payloads.get("celebrities", {})
    credit_directors, credit_casts = parse_douban_rexxar_credit_names(celebrity_payload)
    if not detail.directors and credit_directors:
        detail.directors = credit_directors
    if not detail.casts and credit_casts:
        detail.casts = credit_casts
    people_photos = parse_douban_rexxar_celebrities(celebrity_payload)
    if people_photos:
        detail.raw["people_photos"] = _map_rexxar_credit_photo_aliases(detail, people_photos)
    return detail


def fetch_douban_rexxar_search_detail(item: MediaItem, fetcher=None, timeout: int = 8) -> MediaItem | None:
    """Resolve a non-numeric/stale identity through mobile search, then verify detail.

    The search hit itself is never trusted. Every candidate is fetched through
    ``fetch_douban_rexxar_detail`` so the subject title/aliases, year and media
    type are checked before synopsis, stills or people photos are returned.
    """

    if not item or not str(item.title or "").strip():
        return None
    current_id = str(item.douban_id or "").strip()
    strict_year = item.year if not current_id.startswith("premium-") else None
    seen_ids: set[str] = set()
    for query in _public_metadata_queries(item, limit=12):
        try:
            candidates = fetch_douban_rexxar_search_candidates(query, fetcher=fetcher, timeout=timeout)
        except Exception:
            continue
        for candidate in candidates[:10]:
            subject_id = str(candidate.douban_id or "").strip()
            if not subject_id.isdigit() or subject_id in seen_ids:
                continue
            seen_ids.add(subject_id)
            if strict_year and candidate.year and abs(int(strict_year) - int(candidate.year)) > 1:
                continue
            probe = MediaItem(
                title=item.title,
                media_type=item.media_type,
                year=strict_year,
                douban_id=subject_id,
                raw=dict(item.raw) if isinstance(item.raw, dict) else {},
            )
            detail = fetch_douban_rexxar_detail(probe, fetcher=fetcher, timeout=timeout)
            if detail is None:
                continue
            if item.media_type == "\u52a8\u6f2b" and detail.media_type != "\u52a8\u6f2b":
                continue
            if item.media_type == "\u7535\u89c6\u5267" and detail.media_type not in {"\u7535\u89c6\u5267", "\u52a8\u6f2b"}:
                continue
            if item.media_type == "\u7535\u5f71" and detail.media_type != "\u7535\u5f71":
                continue
            return detail
    return None


def _anime_candidate_titles(row: dict) -> list[str]:
    titles: list[str] = []
    title_data = row.get("title")
    if isinstance(title_data, dict):
        titles.extend(str(title_data.get(key) or "").strip() for key in ("romaji", "english", "native"))
    for key in ("title", "title_english", "title_japanese"):
        value = row.get(key)
        if isinstance(value, str):
            titles.append(value.strip())
    for value in row.get("title_synonyms") or row.get("synonyms") or []:
        titles.append(str(value or "").strip())
    return [title for title in titles if title]


def _is_anime_series_format(value: object) -> bool:
    text = str(value or "").strip().upper()
    return text not in {"MOVIE", "MUSIC"}


def _anilist_person_name(value: object) -> str:
    person = value if isinstance(value, dict) else {}
    names = person.get("name") if isinstance(person.get("name"), dict) else {}
    return str(names.get("native") or names.get("full") or "").strip()


def _anilist_person_photo(value: object) -> str:
    person = value if isinstance(value, dict) else {}
    images = person.get("image") if isinstance(person.get("image"), dict) else {}
    url = str(images.get("large") or images.get("medium") or "").strip()
    return url if url.startswith(("http://", "https://")) else ""


def parse_anilist_results(payload: bytes | str | dict, expected_title: str = "", expected_media_type: str = "") -> list[MediaItem]:
    if expected_media_type and expected_media_type != "动漫":
        return []
    data = _json_payload(payload)
    page = ((data.get("data") or {}).get("Page") or {}) if isinstance(data.get("data"), dict) else {}
    rows = page.get("media") or []
    expected_key = normalize_title(expected_title) if expected_title else ""
    out: list[MediaItem] = []
    for row in rows:
        if not isinstance(row, dict) or not _is_anime_series_format(row.get("format")):
            continue
        title_candidates = _anime_candidate_titles(row)
        if expected_key and not any(normalize_title(title) == expected_key for title in title_candidates):
            continue
        cover_data = row.get("coverImage") if isinstance(row.get("coverImage"), dict) else {}
        cover = str(cover_data.get("extraLarge") or cover_data.get("large") or "").strip()
        if not cover.startswith(("http://", "https://")):
            continue
        anime_id = str(row.get("id") or "").strip()
        year = None
        try:
            year = int(row.get("seasonYear")) if row.get("seasonYear") else None
        except (TypeError, ValueError):
            year = None
        raw = dict(row)
        aliases: list[str] = []
        for candidate in title_candidates:
            clean_candidate = str(candidate or "").strip()
            if clean_candidate and clean_candidate != expected_title and clean_candidate not in aliases:
                aliases.append(clean_candidate)
        if aliases:
            raw["aliases"] = aliases
        genres = [str(value).strip() for value in row.get("genres", []) if str(value).strip()] if isinstance(row.get("genres"), list) else []
        rating_value = parse_float(row.get("averageScore") or row.get("meanScore"))
        if rating_value is not None and rating_value > 10:
            rating_value = round(rating_value / 10, 1)
        if rating_value is not None and rating_value > 0:
            raw["ratings"] = {"anilist": rating_value}
        raw["provider_ids"] = {"anilist": anime_id} if anime_id else {}
        banner = str(row.get("bannerImage") or "").strip()
        if banner.startswith(("http://", "https://")):
            raw["backdrop"] = banner
            raw["stills"] = [banner]
        directors: list[str] = []
        casts: list[str] = []
        people_photos: dict[str, str] = {}
        staff = row.get("staff") if isinstance(row.get("staff"), dict) else {}
        staff_edges = staff.get("edges") if isinstance(staff.get("edges"), list) else []
        for edge in staff_edges:
            if not isinstance(edge, dict):
                continue
            role = str(edge.get("role") or "").strip().casefold()
            if role not in {"director", "chief director", "series director"}:
                continue
            person = edge.get("node") if isinstance(edge.get("node"), dict) else {}
            name = _anilist_person_name(person)
            photo = _anilist_person_photo(person)
            if name and name not in directors:
                directors.append(name)
            if name and photo:
                people_photos.setdefault(name, photo)
        characters = row.get("characters") if isinstance(row.get("characters"), dict) else {}
        character_edges = characters.get("edges") if isinstance(characters.get("edges"), list) else []
        for edge in character_edges:
            voice_actors = edge.get("voiceActors") if isinstance(edge, dict) and isinstance(edge.get("voiceActors"), list) else []
            for person in voice_actors:
                name = _anilist_person_name(person)
                photo = _anilist_person_photo(person)
                if name and name not in casts:
                    casts.append(name)
                if name and photo:
                    people_photos.setdefault(name, photo)
                if len(casts) >= 16:
                    break
            if len(casts) >= 16:
                break
        if people_photos:
            raw["people_photos"] = people_photos
        out.append(MediaItem(
            title=expected_title or next((title for title in title_candidates if title), ""),
            media_type="\u52a8\u6f2b",
            year=year,
            genres=genres,
            directors=directors,
            casts=casts,
            url=str(row.get("siteUrl") or (f"https://anilist.co/anime/{anime_id}" if anime_id else "")),
            douban_id=f"anilist-{anime_id}" if anime_id else "",
            cover=cover,
            source="anilist_api",
            summary=clean_html(str(row.get("description") or "")),
            raw=raw,
        ))
    return out


def fetch_anilist_suggestions(
    title: str,
    media_type: str = "",
    fetcher=None,
    timeout: int = 8,
) -> list[MediaItem]:
    safe_title = str(title or "").strip()
    if not safe_title or (media_type and media_type != "动漫"):
        return []
    aliases = POSTER_SEARCH_ALIASES.get(safe_title, [])
    queries = [safe_title] + [alias for alias in aliases if alias and alias != safe_title]
    query = """
    query ($search: String) {
      Page(page: 1, perPage: 5) {
        media(search: $search, type: ANIME) {
          id
          title { romaji english native }
          format
          seasonYear
          coverImage { large extraLarge color }
          bannerImage
          siteUrl
          description(asHtml: false)
          genres
          averageScore
          popularity
          staff(perPage: 12, sort: RELEVANCE) {
            edges {
              role
              node { name { full native } image { large medium } }
            }
          }
          characters(perPage: 12, sort: [ROLE, RELEVANCE, ID]) {
            edges {
              voiceActors(language: JAPANESE, sort: [RELEVANCE, ID]) {
                name { full native }
                image { large medium }
              }
            }
          }
        }
      }
    }
    """
    headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "CineScopeLocal/1.0"}
    for search in queries:
        body = json.dumps({"query": query, "variables": {"search": search}}, ensure_ascii=False).encode("utf-8")
        url = ANILIST_GRAPHQL_ENDPOINT + "?" + urllib.parse.urlencode({"search": search})
        if fetcher is None:
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with build_url_opener().open(request, timeout=timeout) as response:
                payload = response.read()
        else:
            try:
                payload = fetcher(url, accept_json=True, data=body, headers=headers)
            except TypeError:
                try:
                    payload = fetcher(url, accept_json=True)
                except TypeError:
                    payload = fetcher(url)
        suggestions = parse_anilist_results(payload, expected_title=search, expected_media_type="动漫")
        if suggestions:
            if search != safe_title:
                for item in suggestions:
                    item.title = safe_title
            return suggestions
    return []


def parse_jikan_results(payload: bytes | str | dict, expected_title: str = "", expected_media_type: str = "") -> list[MediaItem]:
    if expected_media_type and expected_media_type != "动漫":
        return []
    data = _json_payload(payload)
    rows = data.get("data") if isinstance(data.get("data"), list) else []
    expected_key = normalize_title(expected_title) if expected_title else ""
    out: list[MediaItem] = []
    for row in rows:
        if not isinstance(row, dict) or not _is_anime_series_format(row.get("type")):
            continue
        title_candidates = _anime_candidate_titles(row)
        if expected_key and not any(normalize_title(title) == expected_key for title in title_candidates):
            continue
        images = row.get("images") if isinstance(row.get("images"), dict) else {}
        jpg = images.get("jpg") if isinstance(images.get("jpg"), dict) else {}
        webp = images.get("webp") if isinstance(images.get("webp"), dict) else {}
        cover = str(jpg.get("large_image_url") or webp.get("large_image_url") or jpg.get("image_url") or webp.get("image_url") or "").strip()
        if not cover.startswith(("http://", "https://")):
            continue
        anime_id = str(row.get("mal_id") or "").strip()
        year = None
        try:
            year = int(row.get("year")) if row.get("year") else None
        except (TypeError, ValueError):
            year = None
        out.append(MediaItem(
            title=expected_title or next((title for title in title_candidates if title), ""),
            media_type="动漫",
            year=year,
            url=str(row.get("url") or (f"https://myanimelist.net/anime/{anime_id}" if anime_id else "")),
            douban_id=f"mal-{anime_id}" if anime_id else "",
            cover=cover,
            source="jikan_myanimelist",
            summary=clean_html(str(row.get("synopsis") or "")),
            raw=row,
        ))
    return out


def fetch_jikan_suggestions(
    title: str,
    media_type: str = "",
    fetcher=None,
    timeout: int = 8,
) -> list[MediaItem]:
    safe_title = str(title or "").strip()
    if not safe_title or (media_type and media_type != "动漫"):
        return []
    aliases = POSTER_SEARCH_ALIASES.get(safe_title, [])
    queries = [safe_title] + [alias for alias in aliases if alias and alias != safe_title]
    fetch = fetcher or http_get
    for search in queries:
        params = {"q": search, "limit": "5", "type": "tv"}
        url = JIKAN_ANIME_SEARCH_ENDPOINT + "?" + urllib.parse.urlencode(params)
        if fetcher is None:
            headers = dict(DEFAULT_HEADERS)
            headers["Accept"] = "application/json"
            request = urllib.request.Request(url, headers=headers)
            with build_url_opener().open(request, timeout=timeout) as response:
                payload = response.read()
        else:
            try:
                payload = fetch(url, accept_json=True)
            except TypeError:
                payload = fetch(url)
        suggestions = parse_jikan_results(payload, expected_title=search, expected_media_type="动漫")
        if suggestions:
            if search != safe_title:
                for item in suggestions:
                    item.title = safe_title
            return suggestions
    return []


def parse_wikipedia_pageimage(payload: bytes | str | dict, expected_title: str = "", expected_media_type: str = "") -> list[MediaItem]:
    if isinstance(payload, dict):
        data = payload
    else:
        text = payload.decode("utf-8", errors="ignore") if isinstance(payload, bytes) else str(payload or "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
    pages = ((data.get("query") or {}).get("pages") or {}) if isinstance(data, dict) else {}
    out: list[MediaItem] = []
    for page in pages.values() if isinstance(pages, dict) else []:
        if not isinstance(page, dict):
            continue
        title = str(page.get("title") or "").strip()
        thumb = page.get("thumbnail") if isinstance(page.get("thumbnail"), dict) else {}
        source = str(thumb.get("source") or "").strip()
        if not source.startswith(("http://", "https://")):
            continue
        out.append(MediaItem(
            title=expected_title or title,
            media_type=expected_media_type or "电影",
            cover=source,
            url=f"https://zh.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}" if title else "",
            source="wikipedia_pageimage",
            raw=page,
        ))
    return out


def fetch_wikipedia_image_suggestions(
    title: str,
    media_type: str = "",
    fetcher=None,
    timeout: int = 6,
) -> list[MediaItem]:
    safe_title = str(title or "").strip()
    if not safe_title:
        return []
    aliases = POSTER_SEARCH_ALIASES.get(safe_title, [])
    queries = [safe_title] + [alias for alias in aliases if alias and alias != safe_title]
    fetch = fetcher or http_get
    for query in queries:
        params = {
            "action": "query",
            "format": "json",
            "prop": "pageimages",
            "piprop": "thumbnail",
            "pithumbsize": "700",
            "redirects": "1",
            "titles": query,
        }
        url = WIKIPEDIA_API_ENDPOINT + "?" + urllib.parse.urlencode(params)
        if fetcher is None:
            headers = dict(DEFAULT_HEADERS)
            headers["Accept"] = "application/json"
            request = urllib.request.Request(url, headers=headers)
            with build_url_opener().open(request, timeout=timeout) as response:
                payload = response.read()
        else:
            try:
                payload = fetch(url, accept_json=True)
            except TypeError:
                payload = fetch(url)
        suggestions = parse_wikipedia_pageimage(payload, expected_title=safe_title, expected_media_type=media_type)
        if suggestions:
            return suggestions
    return []


def fetch_subject_suggestions(title: str, fetcher=None, timeout: int = 4) -> list[MediaItem]:
    safe_title = str(title or "").strip()
    if not safe_title:
        return []
    url = DOUBAN_SUBJECT_SUGGEST_ENDPOINT + "?" + urllib.parse.urlencode({"q": safe_title})
    fetch = fetcher or http_get
    if fetcher is None:
        headers = dict(DEFAULT_HEADERS)
        headers["Referer"] = "https://movie.douban.com/subject_search?search_text=" + urllib.parse.quote(safe_title)
        headers["Accept"] = "application/json,text/javascript,*/*;q=0.8"
        request = urllib.request.Request(url, headers=headers)
        with build_url_opener().open(request, timeout=timeout) as response:
            payload = response.read()
        suggestions = parse_subject_suggestions(payload, expected_title=safe_title)
        if suggestions:
            return suggestions
        search_url = "https://search.douban.com/movie/subject_search?" + urllib.parse.urlencode({"search_text": safe_title, "cat": "1002"})
        search_headers = dict(DEFAULT_HEADERS)
        search_headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        search_headers["Referer"] = "https://movie.douban.com/"
        search_request = urllib.request.Request(search_url, headers=search_headers)
        with build_url_opener().open(search_request, timeout=timeout) as response:
            return parse_subject_search_html(response.read().decode("utf-8", errors="ignore"), expected_title=safe_title)
    else:
        try:
            payload = fetch(url, accept_json=True)
        except TypeError:
            payload = fetch(url)
    return parse_subject_suggestions(payload, expected_title=safe_title)


def _needs_subject_suggest_poster(item: MediaItem) -> bool:
    cover = str(item.cover or "").strip()
    subject_id = str(item.douban_id or "").strip()
    return (
        not cover
        or cover.startswith("data:image/svg+xml")
        or subject_id.startswith("premium-")
    )


def is_douban_cdn_image_url(value: str) -> bool:
    url = str(value or "").strip().lower()
    return "doubanio.com/view/photo" in url or "doubanio.com/img" in url or "img.doubanio.com" in url


def needs_external_poster_rescue(item: MediaItem) -> bool:
    cover = str(item.cover or "").strip()
    return _needs_subject_suggest_poster(item) or is_douban_cdn_image_url(cover)


def enrich_missing_posters_from_subject_suggest(
    items: list[MediaItem],
    fetcher=None,
    limit: int = 120,
    sleep_seconds: float = 0.03,
    max_seconds: float = 14.0,
) -> int:
    """Use Douban's public exact title suggestion endpoint to replace designed covers.

    The function only accepts exact normalized title matches. This avoids the earlier class of bugs where a
    high-quality but wrong poster could be attached to a different title.
    """

    enriched = 0
    attempted = 0
    started_at = time.monotonic()
    for item in items:
        if max_seconds and time.monotonic() - started_at >= max_seconds:
            break
        if attempted >= max(0, int(limit)):
            break
        if not item.title or not _needs_subject_suggest_poster(item):
            continue
        attempted += 1
        try:
            suggestions = fetch_subject_suggestions(item.title, fetcher=fetcher)
        except Exception:
            suggestions = []
        if not suggestions:
            if sleep_seconds:
                time.sleep(sleep_seconds)
            continue
        suggestion = suggestions[0]
        if suggestion.cover:
            item.cover = suggestion.cover
        if suggestion.url:
            item.url = suggestion.url
        if suggestion.douban_id and (not item.douban_id or str(item.douban_id).startswith("premium-")):
            item.douban_id = suggestion.douban_id
        if suggestion.year and not item.year:
            item.year = suggestion.year
        item.source = f"{item.source}|douban_subject_suggest" if item.source else "douban_subject_suggest"
        enriched += 1
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return enriched


def enrich_missing_posters_from_web_sources(
    items: list[MediaItem],
    fetcher=None,
    limit: int = 120,
    sleep_seconds: float = 0.03,
    max_seconds: float = 30.0,
    source_config: PosterSourceConfig | None = None,
    progress_callback=None,
) -> int:
    """Repair designed covers with fast multi-source search while preserving exact-title safety."""

    config = source_config or PosterSourceConfig()
    targets = [item for item in items if item.title and needs_external_poster_rescue(item)][:max(0, int(limit))]
    if not targets:
        return 0

    def find_suggestion(item: MediaItem) -> MediaItem | None:
        static_cover = STATIC_POSTER_URLS_BY_TITLE.get(item.title or "")
        if static_cover:
            return MediaItem(
                title=item.title,
                media_type=item.media_type,
                year=item.year,
                url=item.url,
                douban_id=STATIC_POSTER_IDS_BY_TITLE.get(item.title or "") or item.douban_id,
                cover=static_cover,
                source="static_poster_map",
            )
        source_names: list[str] = []
        if config.prefer_external_over_douban:
            if config.enable_tmdb_api and config.tmdb_api_key:
                source_names.append("tmdb_api")
            if config.enable_omdb and config.omdb_api_key:
                source_names.append("omdb_api")
            if config.enable_tvmaze:
                source_names.append("tvmaze")
            if config.enable_anilist:
                source_names.append("anilist")
            if config.enable_jikan:
                source_names.append("jikan")
            if config.enable_tmdb_html:
                source_names.append("tmdb_html")
            if config.enable_wikipedia:
                source_names.append("wikipedia")
            if config.enable_douban:
                source_names.append("douban")
        else:
            if config.enable_douban:
                source_names.append("douban")
            if config.enable_tmdb_api and config.tmdb_api_key:
                source_names.append("tmdb_api")
            if config.enable_omdb and config.omdb_api_key:
                source_names.append("omdb_api")
            if config.enable_tvmaze:
                source_names.append("tvmaze")
            if config.enable_anilist:
                source_names.append("anilist")
            if config.enable_jikan:
                source_names.append("jikan")
            if config.enable_tmdb_html:
                source_names.append("tmdb_html")
            if config.enable_wikipedia:
                source_names.append("wikipedia")
        suggestions: list[MediaItem] = []
        for source in source_names:
            try:
                if source == "tmdb_api":
                    suggestions = fetch_tmdb_api_suggestions(
                        item.title,
                        media_type=item.media_type,
                        api_key=config.tmdb_api_key,
                        fetcher=fetcher,
                    )
                elif source == "omdb_api":
                    suggestions = fetch_omdb_suggestions(
                        item.title,
                        media_type=item.media_type,
                        api_key=config.omdb_api_key,
                        fetcher=fetcher,
                    )
                elif source == "tvmaze":
                    suggestions = fetch_tvmaze_suggestions(item.title, media_type=item.media_type, fetcher=fetcher)
                elif source == "anilist":
                    suggestions = fetch_anilist_suggestions(item.title, media_type=item.media_type, fetcher=fetcher)
                elif source == "jikan":
                    suggestions = fetch_jikan_suggestions(item.title, media_type=item.media_type, fetcher=fetcher)
                elif source == "tmdb_html":
                    suggestions = fetch_themoviedb_suggestions(item.title, media_type=item.media_type, fetcher=fetcher)
                elif source == "wikipedia":
                    suggestions = fetch_wikipedia_image_suggestions(item.title, media_type=item.media_type, fetcher=fetcher)
                else:
                    suggestions = fetch_subject_suggestions(item.title, fetcher=fetcher)
            except Exception:
                suggestions = []
            if suggestions:
                return suggestions[0]
            if sleep_seconds:
                time.sleep(sleep_seconds)
        return None

    def apply_suggestion(item: MediaItem, suggestion: MediaItem) -> bool:
        if not suggestion or not suggestion.cover:
            return False
        item.cover = suggestion.cover
        if suggestion.url:
            item.url = suggestion.url
        if suggestion.douban_id and (not item.douban_id or str(item.douban_id).startswith("premium-")):
            item.douban_id = suggestion.douban_id
        if suggestion.year and not item.year:
            item.year = suggestion.year
        marker = suggestion.source or "web_poster_search"
        item.source = f"{item.source}|{marker}" if item.source else marker
        return True

    enriched = 0
    max_workers = min(16, max(1, len(targets)))
    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures = {executor.submit(find_suggestion, item): item for item in targets}
    try:
        iterator = as_completed(futures, timeout=max_seconds if max_seconds else None)
        for future in iterator:
            item = futures[future]
            try:
                suggestion = future.result()
            except Exception:
                suggestion = None
            if progress_callback:
                try:
                    progress_callback({
                        "title": item.title,
                        "source": (suggestion.source if suggestion else ""),
                        "status": "found" if suggestion and suggestion.cover else "missed",
                        "cover": suggestion.cover if suggestion else "",
                    })
                except Exception:
                    pass
            if suggestion and apply_suggestion(item, suggestion):
                enriched += 1
    except FuturesTimeoutError:
        pass
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return enriched


def fetch_top250(max_pages: int = 10) -> list[MediaItem]:
    out: list[MediaItem] = []
    seen: set[str] = set()
    for page in range(max_pages):
        start = page * 25
        url = f"https://movie.douban.com/top250?start={start}"
        try:
            text = http_get(url, accept_json=False).decode("utf-8", errors="ignore")
        except Exception:
            continue
        for block in re.findall(r'<div class="item">(.*?)</div>\s*</li>', text, flags=re.S):
            link = first_match(r'<a\s+href="([^"]+)"', block)
            title = first_match(r'<span class="title">(.*?)</span>', block)
            rating = first_match(r'<span class="rating_num"[^>]*>(.*?)</span>', block)
            quote = first_match(r'<span class="inq">(.*?)</span>', block)
            pic = first_match(r'<img[^>]+src="([^"]+)"', block)
            if not title:
                continue
            title = clean_html(title)
            key = extract_douban_id(link) or title
            if key in seen:
                continue
            seen.add(key)
            out.append(MediaItem(
                title=title,
                douban_rating=parse_float(clean_html(rating)),
                media_type="电影",
                url=link,
                douban_id=extract_douban_id(link),
                cover=pic,
                summary=clean_html(quote),
                source="douban_top250",
            ))
    return out


def fetch_url_candidates(urls: Iterable[str]) -> list[MediaItem]:
    out: list[MediaItem] = []
    for url in urls:
        url = str(url or "").strip()
        if not url:
            continue
        if "new_search_subjects" in url:
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            tags = qs.get("tags", ["电影"])[0]
            sort = qs.get("sort", ["U"])[0]
            start = int(qs.get("start", [0])[0])
            out.extend(fetch_explore(tags=tags, sort=sort, start=start, limit=50))
        elif "top250" in url:
            out.extend(fetch_top250(max_pages=4))
        else:
            out.extend(fetch_generic_movie_links(url))
    return out


def fetch_generic_movie_links(url: str) -> list[MediaItem]:
    text = http_get(url, accept_json=False).decode("utf-8", errors="ignore")
    out: list[MediaItem] = []
    seen: set[str] = set()
    for match in re.finditer(r'href="(https://movie\.douban\.com/subject/(\d+)/[^"]*)"[^>]*>(.*?)</a>', text, flags=re.S):
        link, subject_id, inner = match.group(1), match.group(2), match.group(3)
        title = clean_html(inner)
        if not title or len(title) > 80 or subject_id in seen:
            continue
        seen.add(subject_id)
        out.append(MediaItem(title=title, url=link, douban_id=subject_id, source=f"douban_page:{url}"))
    return out


def extract_people_photos(page_html: str, known_names: Iterable[str] = ()) -> dict[str, str]:
    """Extract public celebrity portrait URLs from subject detail markup when present."""

    text = page_html or ""
    photos: dict[str, str] = {}
    known = {str(name).strip() for name in known_names if str(name).strip()}

    def attr(markup: str, name: str) -> str:
        return html.unescape(
            first_match(rf'\b{name}=["\']([^"\']+)["\']', markup)
            or ""
        ).replace("\\/", "/").strip()

    def add(name: str, src: str) -> None:
        clean_name = clean_html(name)
        clean_src = html.unescape(src or "").replace("\\/", "/").strip()
        if known and clean_name not in known:
            return
        if clean_name and clean_src and clean_src.startswith(("http://", "https://")):
            photos.setdefault(clean_name, clean_src)

    celebrity_blocks = re.findall(
        r'<(?:li|div)[^>]+class=["\'][^"\']*(?:celebrity|celeb|cast|actor)[^"\']*["\'][^>]*>.*?</(?:li|div)>',
        text,
        flags=re.S | re.I,
    )
    for block in celebrity_blocks:
        img = first_match(r'(<img\b[^>]*>)', block)
        if not img:
            continue
        src = attr(img, "src") or attr(img, "data-src") or attr(img, "data-original")
        name_match = re.search(r'<span[^>]+class=["\'][^"\']*name[^"\']*["\'][^>]*>(.*?)</span>', block, flags=re.S)
        name = (
            clean_html(name_match.group(1) if name_match else "")
            or attr(img, "alt")
            or attr(img, "title")
        )
        add(name, src)

    if known:
        for img in re.findall(r'<img\b[^>]*>', text, flags=re.S | re.I):
            name = attr(img, "alt") or attr(img, "title")
            src = attr(img, "src") or attr(img, "data-src") or attr(img, "data-original")
            add(name, src)

    return photos


def parse_subject_detail_html(page_html: str, url: str = "") -> MediaItem:
    text = page_html or ""
    title = clean_html(
        first_match(r'<span[^>]+property=["\']v:itemreviewed["\'][^>]*>(.*?)</span>', text)
        or first_match(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', text)
        or first_match(r'<title>(.*?)</title>', text).replace("(豆瓣)", "")
    )
    media_type_match = re.search(r"\s*-\s*(电影|电视剧|动画|动漫)\s*$", title)
    media_type = "动漫" if media_type_match and media_type_match.group(1) in {"动画", "动漫"} else (
        media_type_match.group(1) if media_type_match else ""
    )
    title = re.sub(r"\s*-\s*(电影|电视剧|动画|动漫)\s*$", "", title).strip()
    cover = html.unescape(
        first_match(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', text)
        or first_match(r'<meta[^>]+itemprop=["\']image["\'][^>]+content=["\']([^"\']+)["\']', text)
        or first_match(r'<img[^>]+rel=["\']v:image["\'][^>]+src=["\']([^"\']+)["\']', text)
    )
    summary = clean_html(
        first_match(r'<span[^>]+property=["\']v:summary["\'][^>]*>(.*?)</span>', text)
        or first_match(r'<div[^>]+class=["\']related-info["\'][^>]*>.*?<span[^>]*>(.*?)</span>', text)
        or first_match(r'<section[^>]+class=["\']subject-intro["\'][^>]*>.*?<p[^>]*>(.*?)</p>', text)
        or _summary_from_og_description(first_match(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', text))
    )
    directors = [
        clean_html(value)
        for value in re.findall(r'<a[^>]+rel=["\']v:directedBy["\'][^>]*>(.*?)</a>', text, flags=re.S)
        if clean_html(value)
    ]
    casts = [
        clean_html(value)
        for value in re.findall(r'<a[^>]+rel=["\']v:starring["\'][^>]*>(.*?)</a>', text, flags=re.S)
        if clean_html(value)
    ]
    people_photos = extract_people_photos(text, [*directors, *casts])
    genres = [
        clean_html(value)
        for value in re.findall(r'<span[^>]+property=["\']v:genre["\'][^>]*>(.*?)</span>', text, flags=re.S)
        if clean_html(value)
    ]
    countries = parse_list(clean_html(first_match(r'制片国家/地区:</span>\s*([^<]+)<', text)))
    languages = parse_list(clean_html(first_match(r'语言:</span>\s*([^<]+)<', text)))
    mobile_original_title = clean_html(
        first_match(r'<div[^>]+class=["\'][^"\']*sub-original-title[^"\']*["\'][^>]*>(.*?)</div>', text)
    )
    mobile_meta = clean_html(
        first_match(r'<div[^>]+class=["\'][^"\']*sub-meta[^"\']*["\'][^>]*>(.*?)</div>', text)
    )
    mobile_parts = [part.strip() for part in re.split(r"\s*/\s*", mobile_meta) if part.strip()]
    if not genres:
        genres = [part for part in mobile_parts if part in KNOWN_GENRES]
    if not countries and mobile_parts:
        first_genre = next((index for index, part in enumerate(mobile_parts) if part in KNOWN_GENRES), len(mobile_parts))
        countries = [
            part
            for part in mobile_parts[:first_genre]
            if not re.search(r"(?:19|20)\d{2}|上映|片长|分钟|集$", part)
        ]
    year = None
    year_text = (
        first_match(r'property=["\']v:initialReleaseDate["\'][^>]+content=["\'](\d{4})', text)
        or first_match(r'property=["\']v:initialReleaseDate["\'][^>]*>\s*(\d{4})', text)
        or first_match(r'[（(]((?:19|20)\d{2})[）)]', mobile_original_title)
        or first_match(r'\b((?:19|20)\d{2})-\d{2}-\d{2}', mobile_meta)
        or first_match(r'\((\d{4})\)', title)
    )
    if year_text:
        try:
            year = int(year_text)
        except ValueError:
            year = None
    rating = parse_float(
        first_match(r'<meta[^>]+itemprop=["\']ratingValue["\'][^>]+content=["\']([^"\']+)', text)
    )
    vote_count_text = first_match(
        r'<meta[^>]+itemprop=["\']reviewCount["\'][^>]+content=["\']([^"\']+)', text
    )
    vote_count = None
    if vote_count_text:
        try:
            vote_count = int(re.sub(r"[^0-9]", "", vote_count_text))
        except ValueError:
            vote_count = None
    aliases: list[str] = []
    if mobile_original_title:
        original_without_year = re.sub(r"\s*[（(](?:19|20)\d{2}[）)]\s*$", "", mobile_original_title).strip()
        if original_without_year and original_without_year != title:
            aliases.append(original_without_year)
    raw: dict[str, object] = {}
    if people_photos:
        raw["people_photos"] = people_photos
    if aliases:
        raw["aliases"] = aliases
    return MediaItem(
        title=title,
        douban_rating=rating,
        vote_count=vote_count,
        year=year,
        media_type=media_type,
        genres=genres,
        countries=countries,
        languages=languages,
        directors=directors,
        casts=casts,
        url=url,
        douban_id=extract_douban_id(url),
        cover=cover,
        summary=summary,
        source="douban_subject_detail",
        raw=raw,
    )


def _is_generated_catalog_summary(value: object) -> bool:
    summary = str(value or "").strip()
    return not summary or any(
        summary.startswith(prefix)
        for prefix in (
            "正在补齐这部",
            "资料有限：本地片库暂未记录作品简介",
            "由 CineScope 精选扩展池补入的",
            "详情：点击卡片查看简介",
        )
    )


def _is_largely_latin_summary(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    cjk = sum("\u3400" <= char <= "\u9fff" for char in text)
    latin = sum("a" <= char.lower() <= "z" for char in text)
    return cjk == 0 and latin >= 24 and latin >= len(text) * 0.45


def is_localized_summary(value: object) -> bool:
    text = str(value or "").strip()
    return bool(text) and not _is_generated_catalog_summary(text) and not _is_largely_latin_summary(text)


def _has_usable_chinese_copy(value: object) -> bool:
    text = clean_html(html.unescape(str(value or ""))).strip()
    cjk = sum("\u3400" <= char <= "\u9fff" for char in text)
    latin = sum("a" <= char.lower() <= "z" for char in text)
    return cjk >= 4 and cjk >= max(4, latin // 3)


def _decode_translation_payload(payload: object) -> object:
    if isinstance(payload, (dict, list)):
        return payload
    if isinstance(payload, (bytes, bytearray)):
        text = bytes(payload).decode("utf-8", errors="ignore")
    else:
        text = str(payload or "")
    text = text.lstrip("\ufeff").strip()
    if text.startswith(")]}'"):
        text = text.split("\n", 1)[-1].strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _fetch_translation_payload(url: str, fetcher, timeout: int) -> object:
    if fetcher is not None:
        try:
            return fetcher(url, timeout=timeout)
        except TypeError:
            return fetcher(url)

    import requests

    proxy = configured_proxy_url()
    proxy_candidates: list[str] = []
    if proxy and configured_proxy_mode() != "fallback":
        proxy_candidates.append(proxy)
    proxy_candidates.append("")
    if proxy and proxy not in proxy_candidates:
        proxy_candidates.append(proxy)
    last_error: Exception | None = None
    for candidate in proxy_candidates:
        session = requests.Session()
        session.trust_env = False
        response = None
        try:
            proxies = {"http": candidate, "https": candidate} if candidate else None
            response = session.get(
                url,
                headers={**DEFAULT_HEADERS, "Accept": "application/json,text/plain,*/*"},
                timeout=max(1, int(timeout)),
                proxies=proxies,
            )
            response.raise_for_status()
            return bytes(response.content or b"")
        except Exception as exc:
            last_error = exc
        finally:
            if response is not None:
                response.close()
            session.close()
    if last_error is not None:
        raise last_error
    return b""


def _split_translation_text(value: str, max_chars: int = 420) -> list[str]:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return []
    limit = max(120, int(max_chars))
    units = [part.strip() for part in re.split(r"(?<=[.!?;\u3002\uff01\uff1f\uff1b])\s+", text) if part.strip()]
    chunks: list[str] = []
    current = ""

    def append_piece(piece: str) -> None:
        nonlocal current
        candidate = f"{current} {piece}".strip() if current else piece
        if current and len(candidate) > limit:
            chunks.append(current)
            current = piece
        else:
            current = candidate

    for unit in units:
        remainder = unit
        while len(remainder) > limit:
            cut = remainder.rfind(" ", 0, limit + 1)
            if cut < limit // 2:
                cut = limit
            append_piece(remainder[:cut].strip())
            if current:
                chunks.append(current)
                current = ""
            remainder = remainder[cut:].strip()
        if remainder:
            append_piece(remainder)
    if current:
        chunks.append(current)
    return chunks


def fetch_chinese_summary_translation(
    text: str,
    fetcher=None,
    timeout: int = 5,
) -> tuple[str, str]:
    original = str(text or "").strip()
    if not _is_largely_latin_summary(original):
        return "", ""

    google_url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode({
        "client": "gtx",
        "sl": "auto",
        "tl": "zh-CN",
        "dt": "t",
        "q": original,
    })
    try:
        google_data = _decode_translation_payload(
            _fetch_translation_payload(google_url, fetcher, max(1, int(timeout)))
        )
        segments = google_data[0] if isinstance(google_data, list) and google_data else []
        google_copy = "".join(
            str(segment[0] or "")
            for segment in segments
            if isinstance(segment, (list, tuple)) and segment
        )
        google_copy = clean_html(html.unescape(google_copy)).strip()
        if _has_usable_chinese_copy(google_copy):
            return google_copy, "machine_translation:google"
    except Exception:
        pass

    translated_chunks: list[str] = []
    for chunk in _split_translation_text(original):
        mymemory_url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode({
            "q": chunk,
            "langpair": "en|zh-CN",
        })
        try:
            mymemory_data = _decode_translation_payload(
                _fetch_translation_payload(mymemory_url, fetcher, max(1, int(timeout)))
            )
            response_data = mymemory_data.get("responseData") if isinstance(mymemory_data, dict) else {}
            mymemory_copy = response_data.get("translatedText") if isinstance(response_data, dict) else ""
            mymemory_copy = clean_html(html.unescape(str(mymemory_copy or ""))).strip()
            if not _has_usable_chinese_copy(mymemory_copy):
                return "", ""
            translated_chunks.append(mymemory_copy)
        except Exception:
            return "", ""
    if translated_chunks:
        return "".join(translated_chunks), "machine_translation:mymemory"
    return "", ""


def summary_translation_needs_refresh(item: MediaItem) -> bool:
    raw = item.raw if isinstance(item.raw, dict) else {}
    source = str(raw.get("summary_source") or "").strip().casefold()
    original = str(raw.get("summary_original") or "").strip()
    try:
        version = int(raw.get("summary_translation_version") or 0)
    except (TypeError, ValueError):
        version = 0
    return bool(
        source == "machine_translation:mymemory"
        and version < SUMMARY_TRANSLATION_VERSION
        and _is_largely_latin_summary(original)
    )


def _localize_summary_if_needed(item: MediaItem) -> bool:
    if not isinstance(item.raw, dict):
        item.raw = {}
    refresh_legacy = summary_translation_needs_refresh(item)
    original = str(item.raw.get("summary_original") or "").strip() if refresh_legacy else str(item.summary or "").strip()
    if not _is_largely_latin_summary(original):
        return False
    translated, provider = fetch_chinese_summary_translation(original)
    if not translated or not provider:
        return False
    item.raw.setdefault("summary_original", original)
    item.raw["summary_source"] = provider
    item.raw["summary_generated"] = True
    item.raw["summary_translation_version"] = SUMMARY_TRANSLATION_VERSION
    item.summary = translated
    return True


def merge_subject_detail(item: MediaItem, detail: MediaItem) -> MediaItem:
    expected_titles = _public_metadata_queries(item, limit=12)
    incoming_title = str(detail.title or "").strip()
    detail_aliases = detail.raw.get("aliases") if isinstance(detail.raw, dict) else []
    accepted_titles = [incoming_title, *(detail_aliases if isinstance(detail_aliases, list) else [])]
    if expected_titles and incoming_title and not any(
        _title_matches_expected(candidate, expected)
        for candidate in accepted_titles if str(candidate or "").strip()
        for expected in expected_titles
    ):
        return item
    if not isinstance(item.raw, dict):
        item.raw = {}
    current_id = str(item.douban_id or "").strip()
    incoming_id = str(detail.douban_id or "").strip()
    verified_numeric_repair = incoming_id.isdigit() and not current_id.isdigit()
    external_douban_localization = bool(
        detail.source.startswith("douban") and str(item.source or "").startswith("global:")
    )
    placeholder_people = any(
        is_curated_placeholder_person(value)
        for value in [*(item.directors or []), *(item.casts or [])]
    )
    synthetic_repair = bool(
        detail.source.startswith("douban")
        and (
            str(item.source or "").startswith("premium")
            or
            current_id.startswith("premium-")
            or (placeholder_people and str(item.source or "").startswith(("recommendation", "title_seed", "premium")))
        )
    )
    if verified_numeric_repair:
        item.raw["resolved_from_provider"] = current_id
    if synthetic_repair or (current_id.isdigit() and incoming_id.isdigit() and current_id != incoming_id):
        item.raw["identity_repaired_from"] = current_id or "synthetic-catalog"
    if detail.title and (not item.title or verified_numeric_repair or synthetic_repair or external_douban_localization):
        previous_title = str(item.title or "").strip()
        if previous_title and previous_title != detail.title:
            aliases = item.raw.get("aliases") if isinstance(item.raw.get("aliases"), list) else []
            item.raw["aliases"] = [previous_title, *[value for value in aliases if value != previous_title]]
        item.title = detail.title
    if detail.year and (not item.year or synthetic_repair):
        item.year = detail.year
    if detail.douban_rating is not None and (item.douban_rating is None or synthetic_repair):
        item.douban_rating = detail.douban_rating
    if detail.vote_count is not None and (item.vote_count is None or synthetic_repair):
        item.vote_count = detail.vote_count
    if detail.media_type and not item.media_type:
        item.media_type = detail.media_type
    if detail.cover and not item.cover:
        item.cover = detail.cover
    if detail.summary:
        existing_summary = str(item.summary or "").strip()
        summary_replaced = False
        if str(item.source or "").startswith("douban_user:"):
            if existing_summary and not item.raw.get("user_comment"):
                item.raw["user_comment"] = existing_summary
            item.summary = detail.summary
            summary_replaced = True
        elif (
            _is_generated_catalog_summary(item.summary)
            or synthetic_repair
            or (detail.source.startswith("douban") and _is_largely_latin_summary(item.summary))
            or (_is_largely_latin_summary(item.summary) and _has_usable_chinese_copy(detail.summary))
        ):
            item.summary = detail.summary
            summary_replaced = True
        if summary_replaced:
            if existing_summary and existing_summary != item.summary and _is_largely_latin_summary(existing_summary):
                item.raw.setdefault("summary_original", existing_summary)
            detail_raw = detail.raw if isinstance(detail.raw, dict) else {}
            item.raw["summary_source"] = str(detail_raw.get("summary_source") or detail.source or "public_metadata")
            if detail_raw.get("summary_generated"):
                item.raw["summary_generated"] = True
            else:
                item.raw.pop("summary_generated", None)
    verified_douban_people = bool(
        detail.source.startswith("douban")
        and incoming_id.isdigit()
        and (not current_id.isdigit() or current_id == incoming_id or synthetic_repair)
    )
    if verified_douban_people and (detail.directors or detail.casts):
        item.raw["people_credit_source"] = f"douban:{incoming_id}"

    def should_replace_people_field(current: list[str], incoming: list[str]) -> bool:
        return bool(incoming) and (
            verified_douban_people
            or not current
            or any(is_curated_placeholder_person(value) for value in current)
        )

    for field in ["genres", "countries", "languages", "directors", "casts"]:
        current = list(getattr(item, field) or [])
        incoming = list(getattr(detail, field) or [])
        if field in {"directors", "casts"} and should_replace_people_field(current, incoming):
            setattr(item, field, incoming)
            continue
        for value in getattr(detail, field) or []:
            if value and value not in current:
                current.append(value)
        setattr(item, field, current)
    detail_people_photos = detail.raw.get("people_photos") if isinstance(detail.raw, dict) else None
    detail_aliases = detail.raw.get("aliases") if isinstance(detail.raw, dict) else None
    if isinstance(detail_aliases, list) and detail_aliases:
        item_aliases = item.raw.get("aliases") if isinstance(item.raw, dict) else None
        merged_aliases = list(item_aliases) if isinstance(item_aliases, list) else []
        for alias in detail_aliases:
            clean_alias = str(alias).strip()
            if clean_alias and clean_alias not in merged_aliases:
                merged_aliases.append(clean_alias)
        item.raw["aliases"] = merged_aliases
    detail_stills = detail.raw.get("stills") if isinstance(detail.raw, dict) else None
    if isinstance(detail_stills, (list, tuple)) and detail_stills:
        existing_stills = item.raw.get("stills") if isinstance(item.raw, dict) else None
        merged_stills = list(existing_stills) if isinstance(existing_stills, list) else []
        for still in detail_stills:
            clean_still = str(still or "").strip()
            if clean_still.startswith(("http://", "https://")) and clean_still not in merged_stills:
                merged_stills.append(clean_still)
        if merged_stills:
            item.raw["stills"] = merged_stills[:8]
    if isinstance(detail.raw, dict):
        for key in ("ratings", "rating_votes", "provider_ids"):
            incoming = detail.raw.get(key)
            if not isinstance(incoming, dict) or not incoming:
                continue
            current = item.raw.get(key) if isinstance(item.raw.get(key), dict) else {}
            item.raw[key] = {**current, **incoming}
        for key in ("comment_count", "review_count", "original_title", "provider_format"):
            incoming = detail.raw.get(key)
            if incoming not in (None, "") and item.raw.get(key) in (None, ""):
                item.raw[key] = incoming
        duration = detail.raw.get("duration")
        if isinstance(duration, int) and 0 < duration < 1000 and not item.raw.get("duration"):
            item.raw["duration"] = duration
        release_date = str(detail.raw.get("release_date") or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", release_date) and not item.raw.get("release_date"):
            item.raw["release_date"] = release_date
    if isinstance(detail_people_photos, dict) and detail_people_photos:
        item_people_photos = item.raw.get("people_photos") if isinstance(item.raw, dict) else None
        merged_people_photos = {
            str(name): str(photo)
            for name, photo in (item_people_photos.items() if isinstance(item_people_photos, dict) else [])
            if photo and not is_placeholder_people_image_url(photo)
        }
        current_people_names = {
            str(value).strip()
            for value in [*(item.directors or []), *(item.casts or [])]
            if str(value).strip()
        }
        for name, photo in detail_people_photos.items():
            clean_name = str(name).strip()
            if current_people_names and clean_name not in current_people_names:
                continue
            if clean_name and photo and not is_placeholder_people_image_url(photo):
                merged_people_photos[clean_name] = str(photo)
        item.raw["people_photos"] = merged_people_photos
    if incoming_id and (not current_id or verified_numeric_repair):
        item.douban_id = detail.douban_id
    if detail.url and (not item.url or verified_numeric_repair):
        item.url = detail.url
    return item


def has_people_photo_coverage(item: MediaItem) -> bool:
    if not isinstance(item.raw, dict):
        return False
    photos = item.raw.get("people_photos")
    if not isinstance(photos, dict) or not photos:
        return False
    directors = [str(name).strip() for name in item.directors or [] if str(name).strip()]
    casts = [str(name).strip() for name in item.casts or [] if str(name).strip()]
    if not directors or not casts:
        return False
    names = [*directors[:1], *casts[:5]]
    for name in names:
        url = str(photos.get(name) or "").strip()
        if not url.startswith(("http://", "https://")):
            return False
        if is_placeholder_people_image_url(url):
            return False
    return True


def _public_metadata_queries(item: MediaItem, limit: int = 8) -> list[str]:
    raw = item.raw if isinstance(item.raw, dict) else {}
    values: list[object] = [item.title]
    for key in ("aliases", "original_titles", "original_title"):
        value = raw.get(key)
        if isinstance(value, (list, tuple, set)):
            values.extend(value)
        elif value:
            values.append(value)
    values.extend(POSTER_SEARCH_ALIASES.get(str(item.title or "").strip(), []))
    queries: list[str] = []
    seen: set[str] = set()
    for value in values:
        query = clean_html(str(value or "")).replace("\u200e", "").strip()
        normalized = normalize_title(query)
        if len(query) < 2 or len(query) > 160 or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        queries.append(query)
        if len(queries) >= max(1, int(limit)):
            break
    return queries


_SEASON_IDENTITY_RE = re.compile(
    r"(?:\u7b2c\s*[0-9\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e]+\s*\u5b63|\bseason\s*(?:[0-9]+|[ivxlcdm]+)\b|\bs\d{1,2}\b)",
    flags=re.I,
)


def _has_explicit_season_identity(item: MediaItem) -> bool:
    raw = item.raw if isinstance(item.raw, dict) else {}
    values: list[object] = [item.title, item.summary]
    for key in ("aliases", "original_titles", "original_title"):
        value = raw.get(key)
        if isinstance(value, (list, tuple, set)):
            values.extend(value)
        elif value:
            values.append(value)
    return any(_SEASON_IDENTITY_RE.search(str(value or "")) for value in values)


def _title_without_season_marker(value: object) -> str:
    text = clean_html(str(value or "")).replace("\u200e", "").strip()
    text = re.sub(
        r"(?:[-:|\u00b7]\s*)?(?:\u7b2c\s*[0-9\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e]+\s*\u5b63|season\s*(?:[0-9]+|[ivxlcdm]+)|s\d{1,2})\s*$",
        "",
        text,
        flags=re.I,
    ).strip()
    return normalize_title(text)


def _can_borrow_parent_series_people(item: MediaItem, suggestion: MediaItem) -> bool:
    if item.media_type not in {"\u7535\u89c6\u5267", "\u52a8\u6f2b"} or suggestion.source != "tvmaze_api":
        return False
    if not item.year or not suggestion.year or int(item.year) <= int(suggestion.year) + 1:
        return False
    if not _has_explicit_season_identity(item):
        return False
    suggestion_raw = suggestion.raw if isinstance(suggestion.raw, dict) else {}
    suggestion_people = suggestion_raw.get("people_photos")
    if not (suggestion.directors or suggestion.casts) or not isinstance(suggestion_people, dict) or not suggestion_people:
        return False
    parent_title = normalize_title(str(suggestion.title or "").strip())
    if not parent_title:
        return False
    return any(
        parent_title in {normalize_title(query), _title_without_season_marker(query)}
        for query in _public_metadata_queries(item, limit=12)
    )


def _merge_parent_series_people(item: MediaItem, suggestion: MediaItem) -> bool:
    if not isinstance(item.raw, dict):
        item.raw = {}
    before = (
        tuple(item.directors or []),
        tuple(item.casts or []),
        dict(item.raw.get("people_photos") or {}) if isinstance(item.raw.get("people_photos"), dict) else {},
    )
    for field in ("directors", "casts"):
        current = [
            str(value).strip()
            for value in getattr(item, field) or []
            if str(value).strip() and not is_curated_placeholder_person(value)
        ]
        for value in getattr(suggestion, field) or []:
            clean_value = str(value).strip()
            if clean_value and clean_value not in current:
                current.append(clean_value)
        setattr(item, field, current)

    incoming_photos = suggestion.raw.get("people_photos") if isinstance(suggestion.raw, dict) else {}
    existing_photos = {
        str(name): str(photo)
        for name, photo in (item.raw.get("people_photos") or {}).items()
        if name and photo and not is_placeholder_people_image_url(photo)
    } if isinstance(item.raw.get("people_photos"), dict) else {}
    visible_names = {
        str(name).strip()
        for name in [*(item.directors or []), *(item.casts or [])]
        if str(name).strip()
    }
    if isinstance(incoming_photos, dict):
        for name, photo in incoming_photos.items():
            clean_name = str(name).strip()
            clean_photo = str(photo or "").strip()
            if (
                clean_name in visible_names
                and clean_photo.startswith(("http://", "https://"))
                and not is_placeholder_people_image_url(clean_photo)
            ):
                existing_photos.setdefault(clean_name, clean_photo)
    if existing_photos:
        item.raw["people_photos"] = existing_photos
    after = (
        tuple(item.directors or []),
        tuple(item.casts or []),
        dict(item.raw.get("people_photos") or {}) if isinstance(item.raw.get("people_photos"), dict) else {},
    )
    return after != before


def _public_metadata_state(item: MediaItem) -> tuple[bool, bool, bool, bool, bool, bool, bool]:
    raw = item.raw if isinstance(item.raw, dict) else {}
    ratings = raw.get("ratings") if isinstance(raw.get("ratings"), dict) else {}
    parsed_ratings = [parse_float(value) for value in ratings.values()]
    return (
        is_localized_summary(item.summary),
        bool(item.genres),
        item.douban_rating is not None or any(value is not None and value > 0 for value in parsed_ratings),
        bool(item.directors),
        bool(item.casts),
        isinstance(raw.get("stills"), list) and bool(raw.get("stills")),
        has_people_photo_coverage(item),
    )


def enrich_public_metadata(item: MediaItem, max_seconds: float = 10.0) -> bool:
    """Fill synopsis and visual still candidates from free public providers.

    This is intentionally a best-effort supplement to Douban. It never replaces
    verified Douban fields and only merges a provider result when its title
    matcher accepted the requested work.
    """
    if not item or not str(item.title or "").strip():
        return False
    if all(_public_metadata_state(item)) and not summary_translation_needs_refresh(item):
        return False
    started_at = time.monotonic()
    changed_any = False
    raw = item.raw if isinstance(item.raw, dict) else {}
    provider_ids = raw.get("provider_ids") if isinstance(raw.get("provider_ids"), dict) else {}
    tvmaze_id = str(provider_ids.get("tvmaze") or "").strip()
    if not tvmaze_id and str(item.douban_id or "").startswith("tvmaze-"):
        tvmaze_id = str(item.douban_id).removeprefix("tvmaze-").strip()
    if (
        item.media_type == "\u7535\u89c6\u5267"
        and tvmaze_id
        and not _imdb_provider_id(item)
        and not str(raw.get("provider_format") or "").strip()
    ):
        for query in _public_metadata_queries(item):
            try:
                suggestions = fetch_tvmaze_suggestions(query, media_type="\u7535\u89c6\u5267")
            except Exception:
                suggestions = []
            matched = next((
                suggestion
                for suggestion in suggestions
                if isinstance(suggestion, MediaItem)
                and not (
                    item.year
                    and suggestion.year
                    and abs(int(item.year) - int(suggestion.year)) > 1
                )
            ), None)
            if matched is None:
                continue
            before_genres = tuple(item.genres)
            before_format = str(raw.get("provider_format") or "").strip()
            merge_subject_detail(item, matched)
            raw = item.raw if isinstance(item.raw, dict) else {}
            if tuple(item.genres) != before_genres or str(raw.get("provider_format") or "").strip() != before_format:
                changed_any = True
            break
    changed_any = _localize_summary_if_needed(item) or changed_any
    if all(_public_metadata_state(item)) and not summary_translation_needs_refresh(item):
        return changed_any
    providers = []

    def imdb_provider(query: str) -> list[MediaItem]:
        provider_id = _imdb_provider_id(item)
        if not provider_id and not item.casts:
            return []
        return fetch_imdb_metadata_suggestions(
            query,
            media_type=item.media_type,
            expected_year=item.year,
            expected_cast=item.casts,
            provider_id=provider_id,
        )

    has_verified_imdb_id = bool(_imdb_provider_id(item))
    if item.media_type == "电影":
        tmdb_provider = lambda query: fetch_themoviedb_metadata_suggestions(query, media_type="电影", expected_year=item.year)
        providers = [imdb_provider, tmdb_provider] if has_verified_imdb_id else [tmdb_provider, imdb_provider]
    elif item.media_type == "电视剧":
        tmdb_provider = lambda query: fetch_themoviedb_metadata_suggestions(query, media_type="电视剧", expected_year=item.year)
        tvmaze_provider = lambda query: fetch_tvmaze_suggestions(query, media_type="电视剧")
        # TVMaze identities can reveal an IMDb id; once one is verified, IMDb is
        # the fastest path to a rating and landscape stills and must not sit
        # behind slower discovery providers.
        providers = (
            [imdb_provider, tvmaze_provider, tmdb_provider]
            if has_verified_imdb_id
            else [tvmaze_provider, imdb_provider, tmdb_provider]
        )
    elif item.media_type == "动漫":
        providers = [
            lambda query: fetch_themoviedb_metadata_suggestions(query, media_type="动漫", expected_year=item.year),
            lambda query: fetch_tvmaze_suggestions(query, media_type="动漫"),
            lambda query: fetch_anilist_suggestions(query, media_type="动漫"),
            lambda query: fetch_jikan_suggestions(query, media_type="动漫"),
            imdb_provider,
        ]
    queries = _public_metadata_queries(item)
    for provider in providers:
        for query in queries:
            if max_seconds and time.monotonic() - started_at >= max_seconds:
                return changed_any
            try:
                suggestions = provider(query) or []
            except Exception:
                suggestions = []
            for suggestion in suggestions:
                if not isinstance(suggestion, MediaItem):
                    continue
                suggestion_raw = suggestion.raw if isinstance(suggestion.raw, dict) else {}
                suggestion_ratings = (
                    suggestion_raw.get("ratings") if isinstance(suggestion_raw.get("ratings"), dict) else {}
                )
                suggestion_people = (
                    suggestion_raw.get("people_photos")
                    if isinstance(suggestion_raw.get("people_photos"), dict)
                    else {}
                )
                year_mismatch = bool(
                    item.year
                    and suggestion.year
                    and abs(int(item.year) - int(suggestion.year)) > 1
                )
                parent_series_people = bool(
                    year_mismatch and _can_borrow_parent_series_people(item, suggestion)
                )
                if year_mismatch:
                    if not parent_series_people:
                        continue
                    before = _public_metadata_state(item)
                    merged_people = _merge_parent_series_people(item, suggestion)
                    after = _public_metadata_state(item)
                    if merged_people or after != before:
                        changed_any = True
                    if all(after) and not summary_translation_needs_refresh(item):
                        return changed_any
                    continue
                if (
                    not suggestion.summary
                    and not suggestion_raw.get("stills")
                    and not suggestion_ratings
                    and not suggestion.directors
                    and not suggestion.casts
                    and not suggestion_people
                ):
                    continue
                source_title = str(suggestion.title or "").strip()
                if source_title and normalize_title(source_title) != normalize_title(item.title):
                    aliases = suggestion_raw.get("aliases") if isinstance(suggestion_raw.get("aliases"), list) else []
                    suggestion.raw = {**suggestion_raw, "aliases": [source_title, *aliases]}
                    suggestion.title = item.title
                before = _public_metadata_state(item)
                merge_subject_detail(item, suggestion)
                localized = _localize_summary_if_needed(item)
                after = _public_metadata_state(item)
                if after != before or localized:
                    changed_any = True
                if all(after) and not summary_translation_needs_refresh(item):
                    return changed_any
    return changed_any


def _needs_verified_douban_localization(item: MediaItem) -> bool:
    return bool(
        str(item.source or "").startswith("global:")
        and str(item.douban_id or "").strip().isdigit()
        and (_is_largely_latin_summary(item.summary) or not re.search(r"[\u3400-\u9fff]", str(item.title or "")))
    )


def enrich_media_items(
    items: list[MediaItem],
    fetcher=None,
    limit: int = 12,
    sleep_seconds: float = 0.05,
    force_people_photos: bool = False,
) -> list[MediaItem]:
    fetch = fetcher or (lambda url: http_get(url, accept_json=False))
    enriched = 0
    for item in items:
        if enriched >= limit:
            break
        current_raw = item.raw if isinstance(item.raw, dict) else {}
        current_stills = current_raw.get("stills") if isinstance(current_raw.get("stills"), list) else []
        if (
            item.summary
            and item.directors
            and item.casts
            and item.genres
            and item.cover
            and item.douban_rating is not None
            and current_stills
            and (not force_people_photos or has_people_photo_coverage(item))
            and not _needs_verified_douban_localization(item)
        ):
            continue
        merged_any_detail = False
        if fetcher is None:
            subject_id = str(item.douban_id or extract_douban_id(item.url) or "").strip()
            try:
                rexxar_detail = fetch_douban_rexxar_detail(item) if subject_id.isdigit() else None
            except Exception:
                rexxar_detail = None
            if rexxar_detail is None:
                try:
                    rexxar_detail = fetch_douban_rexxar_search_detail(item)
                except Exception:
                    rexxar_detail = None
            if rexxar_detail is not None:
                merge_subject_detail(item, rexxar_detail)
                merged_any_detail = True
                raw = item.raw if isinstance(item.raw, dict) else {}
                has_stills = isinstance(raw.get("stills"), list) and bool(raw.get("stills"))
                if (
                    item.summary
                    and item.directors
                    and item.casts
                    and item.genres
                    and item.cover
                    and item.douban_rating is not None
                    and has_stills
                    and (not force_people_photos or has_people_photo_coverage(item))
                ):
                    enriched += 1
                    if sleep_seconds:
                        time.sleep(sleep_seconds)
                    continue
        urls = subject_detail_urls(item)
        if not urls and force_people_photos and item.title:
            try:
                suggestions = fetch_subject_suggestions(item.title)
            except Exception:
                suggestions = []
            suggestion = suggestions[0] if suggestions else None
            if suggestion:
                if suggestion.douban_id:
                    item.douban_id = suggestion.douban_id
                if suggestion.url:
                    item.url = suggestion.url
                if suggestion.cover and (not item.cover or str(item.cover).startswith("data:image/svg+xml")):
                    item.cover = suggestion.cover
                if suggestion.year and not item.year:
                    item.year = suggestion.year
                urls = subject_detail_urls(item)
        if not urls:
            continue
        if item.summary and item.directors and item.casts and item.genres and item.cover:
            if not force_people_photos or has_people_photo_coverage(item):
                continue
        for url in urls:
            try:
                payload = fetch(url)
                html_text = payload.decode("utf-8", errors="ignore") if isinstance(payload, bytes) else str(payload)
                detail = parse_subject_detail_html(html_text, url=url)
                if not detail.cover and not detail.summary and detail.title in {"", "豆瓣"}:
                    continue
                merge_subject_detail(item, detail)
                merged_any_detail = True
                if not force_people_photos or has_people_photo_coverage(item):
                    break
            except Exception:
                continue
        if merged_any_detail:
            enriched += 1
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return items


def http_get(url: str, accept_json: bool = True, timeout: int = 12) -> bytes:
    headers = dict(DEFAULT_HEADERS)
    if not accept_json:
        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        if "m.douban.com" in url:
            headers["Referer"] = "https://m.douban.com/movie/"
            headers["User-Agent"] = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"
    request = urllib.request.Request(url, headers=headers)
    opener = build_url_opener()
    with opener.open(request, timeout=timeout) as response:
        return response.read()


def fetch_douban_detail_html(url: str, cookie: str = "", timeout: int = 10) -> bytes:
    headers = dict(DEFAULT_HEADERS)
    headers.update({
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://movie.douban.com/",
    })
    clean_cookie = str(cookie or "").strip()
    if clean_cookie:
        headers["Cookie"] = clean_cookie
    request = urllib.request.Request(_validated_douban_subject_url(url), headers=headers)
    opener = build_douban_detail_opener()
    with opener.open(request, timeout=max(1, int(timeout))) as response:
        return response.read()


def configured_proxy_url(env: dict[str, str] | None = None) -> str:
    environment = os.environ if env is None else env
    for name in ("CINESCOPE_OUTBOUND_PROXY", "DOUBAN_RECOMMENDER_HTTP_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY"):
        value = environment.get(name) or environment.get(name.lower())
        if value:
            return str(value).strip()
    return ""


def configured_proxy_mode(env: dict[str, str] | None = None) -> str:
    environment = os.environ if env is None else env
    return str(environment.get("CINESCOPE_PROXY_MODE") or "").strip().casefold()


class _RequestsResponseAdapter:
    def __init__(self, response, url: str):
        self._response = response
        self._url = str(getattr(response, "url", "") or url)
        self.headers = response.headers
        self.status = int(response.status_code)
        self.code = self.status

    def read(self, amount: int | None = None) -> bytes:
        payload = bytes(self._response.content or b"")
        return payload if amount is None else payload[: max(0, int(amount))]

    def geturl(self) -> str:
        return self._url

    def close(self) -> None:
        self._response.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        self.close()
        return False


class _RequestsProxyOpener:
    def __init__(self, proxy_url: str, redirect_validator=None):
        self.proxy_url = str(proxy_url or "").strip()
        self.redirect_validator = redirect_validator

    def open(self, request, timeout: int | float = 12):
        try:
            import requests
        except ImportError as exc:
            raise urllib.error.URLError("SOCKS proxy support requires requests[socks]") from exc
        req = request if isinstance(request, urllib.request.Request) else urllib.request.Request(str(request))
        session = requests.Session()
        session.trust_env = False
        url = str(req.full_url)
        method = str(req.get_method() or "GET").upper()
        data = req.data
        headers = dict(req.header_items())
        proxies = {"http": self.proxy_url, "https": self.proxy_url}
        for _redirect in range(6):
            try:
                response = session.request(
                    method,
                    url,
                    headers=headers,
                    data=data,
                    timeout=timeout,
                    proxies=proxies,
                    allow_redirects=False,
                )
            except requests.RequestException as exc:
                session.close()
                raise urllib.error.URLError(str(exc)) from exc
            status = int(response.status_code)
            location = str(response.headers.get("Location") or "").strip()
            if status in {301, 302, 303, 307, 308} and location:
                next_url = urllib.parse.urljoin(url, location)
                response.close()
                if self.redirect_validator is not None:
                    next_url = self.redirect_validator(next_url)
                if status == 303 or (status in {301, 302} and method not in {"GET", "HEAD"}):
                    method = "GET"
                    data = None
                url = next_url
                continue
            session.close()
            if status >= 400:
                body = bytes(response.content or b"")
                response.close()
                raise urllib.error.HTTPError(url, status, str(response.reason or "HTTP error"), response.headers, io.BytesIO(body))
            return _RequestsResponseAdapter(response, url)
        session.close()
        raise urllib.error.HTTPError(url, 310, "too many redirects", {}, None)


def _build_proxy_opener(proxy: str):
    if urllib.parse.urlsplit(proxy).scheme.lower() in {"socks5", "socks5h"}:
        return _RequestsProxyOpener(proxy)
    return urllib.request.build_opener(urllib.request.ProxyHandler({
        "http": proxy,
        "https": proxy,
    }))


def build_url_opener():
    proxy = configured_proxy_url()
    if proxy and configured_proxy_mode() != "fallback":
        return _build_proxy_opener(proxy)
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def build_retry_url_opener():
    proxy = configured_proxy_url()
    if proxy and configured_proxy_mode() == "fallback":
        return _build_proxy_opener(proxy)
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


class _DoubanSubjectRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url = _validated_douban_subject_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, safe_url)


def build_douban_detail_opener():
    handlers: list[object] = [_DoubanSubjectRedirectHandler()]
    proxy = configured_proxy_url()
    if proxy and urllib.parse.urlsplit(proxy).scheme.lower() in {"socks5", "socks5h"}:
        return _RequestsProxyOpener(proxy, redirect_validator=_validated_douban_subject_url)
    if proxy:
        handlers.insert(0, urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener(*handlers)


def subject_detail_urls(item: MediaItem) -> list[str]:
    subject_id = item.douban_id or extract_douban_id(item.url)
    urls: list[str] = []
    if subject_id and str(subject_id).isdigit():
        mobile = f"https://m.douban.com/movie/subject/{subject_id}/"
        desktop = f"https://movie.douban.com/subject/{subject_id}/"
        for url in (mobile, desktop):
            if url not in urls:
                urls.append(url)
    return urls


def _validated_douban_subject_url(url: str) -> str:
    text = str(url or "").strip()
    parsed = urllib.parse.urlparse(text)
    if (
        parsed.scheme.lower() != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Douban subject URL must use a canonical HTTPS endpoint")
    host = (parsed.hostname or "").lower()
    pattern = r"/subject/(\d+)/?" if host == "movie.douban.com" else r"/movie/subject/(\d+)/?" if host == "m.douban.com" else ""
    match = re.fullmatch(pattern, parsed.path) if pattern else None
    if not match:
        raise ValueError("Douban subject URL must use a canonical Douban subject host")
    prefix = "/subject" if host == "movie.douban.com" else "/movie/subject"
    return f"https://{host}{prefix}/{match.group(1)}/"


def _summary_from_og_description(value: str) -> str:
    text = html.unescape(value or "")
    m = re.search(r"简介[:：]\s*(.*)", text, flags=re.S)
    return m.group(1).strip() if m else text.strip()


def first_match(pattern: str, text: str) -> str:
    m = re.search(pattern, text, flags=re.S)
    return m.group(1).strip() if m else ""


def clean_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<.*?>", "", text, flags=re.S)
    return html.unescape(text).strip()


def parse_float(value: object) -> float | None:
    if value is None:
        return None
    m = re.search(r"\d+(?:\.\d+)?", str(value))
    return float(m.group(0)) if m else None
