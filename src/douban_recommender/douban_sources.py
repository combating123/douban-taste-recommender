from __future__ import annotations

import html
import json
import os
import re
import time
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
THEMOVIEDB_SEARCH_ENDPOINT = "https://www.themoviedb.org/search"
TMDB_API_SEARCH_ENDPOINT = "https://api.themoviedb.org/3/search"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
OMDB_API_ENDPOINT = "https://www.omdbapi.com/"
TVMAZE_SHOW_SEARCH_ENDPOINT = "https://api.tvmaze.com/singlesearch/shows"
WIKIPEDIA_API_ENDPOINT = "https://zh.wikipedia.org/w/api.php"
ANILIST_GRAPHQL_ENDPOINT = "https://graphql.anilist.co"
JIKAN_ANIME_SEARCH_ENDPOINT = "https://api.jikan.moe/v4/anime"
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
    "人生切割术": ["Severance"],
    "3月的狮子": ["3-gatsu no Lion", "March comes in like a lion"],
    "少女歌剧 Revue Starlight": ["Shoujo Kageki Revue Starlight", "Revue Starlight"],
    "末日三问": ["Shuumatsu Nani Shitemasu ka", "WorldEnd"],
    "赛马娘 Road to the Top": ["Uma Musume Pretty Derby Road to the Top"],
    "Fate/stay night UBW": ["Fate/stay night: Unlimited Blade Works"],
    "PSYCHO-PASS 心理测量者": ["PSYCHO-PASS"],
}

POSTER_SEARCH_ALIASES.update({
    "????": ["Memento"],
    "?????": ["Drive My Car"],
    "????": ["The Book of Fish"],
    "?????": ["Generation War", "Unsere M?tter, unsere V?ter"],
    "????????": ["Love Death and Robots", "Love, Death & Robots"],
    "????": ["Fog Hill of Five Elements"],
    "????": ["Yao Chinese Folktales", "Yao-Chinese Folktales", "Chinese Folktales"],
    "?????": ["Steins Gate", "Steins;Gate"],
    "??????": ["Girls Last Tour", "Girls' Last Tour"],
    "???": ["Mononoke"],
    "???": ["Scissor Seven", "Wu Liuqi"],
})

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

STATIC_POSTER_URLS_BY_TITLE.update({
    "????": "https://m.media-amazon.com/images/M/MV5BMGQ3Y2Q4NjktN2E4Ny00Y2Q2LTliZDUtZTNiNjRhY2I0NGIyXkEyXkFqcGc@._V1_.jpg",
    "?????": "https://m.media-amazon.com/images/M/MV5BOGE5ZWRhYjYtNzVkMS00ZGU3LTg2MTMtODYyMmJlMDMyZjU0XkEyXkFqcGc@._V1_.jpg",
    "????": "https://m.media-amazon.com/images/M/MV5BNWYyMDkxY2ItNmRmMC00Y2ZmLTkwZGYtNDJiYmZhOGUzOGY0XkEyXkFqcGc@._V1_.jpg",
    "?????": "https://static.tvmaze.com/uploads/images/original_untouched/7/17646.jpg",
    "????????": "https://static.tvmaze.com/uploads/images/original_untouched/501/1253559.jpg",
    "????": "https://m.media-amazon.com/images/M/MV5BMTZmNmNmYmQtNTIxMi00MjJjLWE5N2UtODZhMmZhOGExOGQyXkEyXkFqcGc@._V1_.jpg",
    "????": "https://m.media-amazon.com/images/M/MV5BODNhN2E5YjQtMTBlOC00NmIzLWI1ZmEtNGE4NjkzODhlM2Q2XkEyXkFqcGc@._V1_.jpg",
    "?????": "https://cdn.myanimelist.net/images/anime/1935/127974l.jpg",
    "??????": "https://cdn.myanimelist.net/images/anime/12/88321l.jpg",
    "???": "https://cdn.myanimelist.net/images/anime/3/20713l.jpg",
    "???": "https://m.media-amazon.com/images/M/MV5BNDdhYTU2OTUtNjRiOS00MjQxLThlNzctZWEyY2Q3YTA2M2ZmXkEyXkFqcGc@._V1_.jpg",
})

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

STATIC_POSTER_IDS_BY_TITLE.update({
    "????": "imdb-tt0209144",
    "?????": "imdb-tt14039582",
    "????": "imdb-tt14371900",
    "?????": "tvmaze-1224",
    "????????": "tvmaze-40329",
    "????": "imdb-tt12953630",
    "????": "imdb-tt26007176",
    "?????": "mal-9253",
    "??????": "mal-35838",
    "???": "mal-2246",
    "???": "imdb-tt10384610",
})

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


def _title_matches_expected(candidate_title: str, expected_title: str) -> bool:
    if not expected_title:
        return True
    return normalize_title(_primary_search_title(candidate_title)) == normalize_title(expected_title)


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


def parse_themoviedb_search_html(page_html: str, expected_title: str = "", expected_media_type: str = "") -> list[MediaItem]:
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
        year = None
        year_match = re.search(r"\b(19\d{2}|20\d{2})\b", clean_html(card))
        if year_match:
            try:
                year = int(year_match.group(1))
            except ValueError:
                year = None
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


def fetch_themoviedb_suggestions(title: str, media_type: str = "", fetcher=None, timeout: int = 6) -> list[MediaItem]:
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
        suggestions = parse_themoviedb_search_html(text, expected_title=expected, expected_media_type=media_type)
        if suggestions:
            if query != safe_title:
                for item in suggestions:
                    item.title = safe_title
            return suggestions
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


def parse_tvmaze_result(payload: bytes | str | dict, expected_title: str = "", expected_media_type: str = "") -> list[MediaItem]:
    if expected_media_type and expected_media_type not in {"\u7535\u89c6\u5267"}:
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
    return [MediaItem(
        title=expected_title or title,
        media_type="\u7535\u89c6\u5267",
        year=year,
        url=str(data.get("officialSite") or data.get("url") or "").strip(),
        douban_id=f"tvmaze-{tvmaze_id}" if tvmaze_id else "",
        cover=cover,
        source="tvmaze_api",
        raw=data,
    )]


def fetch_tvmaze_suggestions(
    title: str,
    media_type: str = "",
    fetcher=None,
    timeout: int = 6,
) -> list[MediaItem]:
    safe_title = str(title or "").strip()
    if not safe_title or media_type not in {"", "\u7535\u89c6\u5267"}:
        return []
    aliases = POSTER_SEARCH_ALIASES.get(safe_title, [])
    queries = [safe_title] + [alias for alias in aliases if alias and alias != safe_title]
    fetch = fetcher or http_get
    for query in queries:
        url = TVMAZE_SHOW_SEARCH_ENDPOINT + "?" + urllib.parse.urlencode({"q": query})
        if fetcher is None:
            headers = dict(DEFAULT_HEADERS)
            headers["Accept"] = "application/json"
            request = urllib.request.Request(url, headers=headers)
            try:
                with build_url_opener().open(request, timeout=timeout) as response:
                    payload = response.read()
            except urllib.error.HTTPError as error:
                error.close()
                raise
        else:
            try:
                payload = fetch(url, accept_json=True)
            except TypeError:
                payload = fetch(url)
        suggestions = parse_tvmaze_result(payload, expected_title=query, expected_media_type="\u7535\u89c6\u5267")
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


def _anime_candidate_titles(row: dict) -> list[str]:
    titles: list[str] = []
    title_data = row.get("title")
    if isinstance(title_data, dict):
        titles.extend(str(title_data.get(key) or "").strip() for key in ("romaji", "english", "native"))
    for key in ("title", "title_english", "title_japanese"):
        titles.append(str(row.get(key) or "").strip())
    for value in row.get("title_synonyms") or row.get("synonyms") or []:
        titles.append(str(value or "").strip())
    return [title for title in titles if title]


def _is_anime_series_format(value: object) -> bool:
    text = str(value or "").strip().upper()
    return text not in {"MOVIE", "MUSIC"}


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
        out.append(MediaItem(
            title=expected_title or next((title for title in title_candidates if title), ""),
            media_type="动漫",
            year=year,
            url=str(row.get("siteUrl") or (f"https://anilist.co/anime/{anime_id}" if anime_id else "")),
            douban_id=f"anilist-{anime_id}" if anime_id else "",
            cover=cover,
            source="anilist_api",
            raw=row,
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
          siteUrl
          averageScore
          popularity
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
    year = None
    year_text = (
        first_match(r'property=["\']v:initialReleaseDate["\'][^>]+content=["\'](\d{4})', text)
        or first_match(r'property=["\']v:initialReleaseDate["\'][^>]*>\s*(\d{4})', text)
        or first_match(r'\((\d{4})\)', title)
    )
    if year_text:
        try:
            year = int(year_text)
        except ValueError:
            year = None
    return MediaItem(
        title=title,
        year=year,
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
        raw={"people_photos": people_photos} if people_photos else {},
    )


def merge_subject_detail(item: MediaItem, detail: MediaItem) -> MediaItem:
    if detail.title and not item.title:
        item.title = detail.title
    if detail.year and not item.year:
        item.year = detail.year
    if detail.cover and not item.cover:
        item.cover = detail.cover
    if detail.summary and not item.summary:
        item.summary = detail.summary
    def should_replace_people_field(current: list[str], incoming: list[str]) -> bool:
        return bool(incoming) and (not current or any(is_curated_placeholder_person(value) for value in current))

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
    if isinstance(detail_people_photos, dict) and detail_people_photos:
        item_people_photos = item.raw.get("people_photos") if isinstance(item.raw, dict) else None
        merged_people_photos = dict(item_people_photos) if isinstance(item_people_photos, dict) else {}
        current_people_names = {
            str(value).strip()
            for value in [*(item.directors or []), *(item.casts or [])]
            if str(value).strip()
        }
        for name, photo in detail_people_photos.items():
            clean_name = str(name).strip()
            if current_people_names and clean_name not in current_people_names:
                continue
            if clean_name and photo and clean_name not in merged_people_photos:
                merged_people_photos[clean_name] = str(photo)
        item.raw["people_photos"] = merged_people_photos
    if detail.douban_id and not item.douban_id:
        item.douban_id = detail.douban_id
    if detail.url and not item.url:
        item.url = detail.url
    return item


def has_people_photo_coverage(item: MediaItem) -> bool:
    if not isinstance(item.raw, dict):
        return False
    photos = item.raw.get("people_photos")
    if not isinstance(photos, dict) or not photos:
        return False
    names = [*(item.directors or []), *(item.casts or [])]
    if not names:
        return True
    return all(str(name) in photos for name in names if str(name).strip())


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
        merged_any_detail = False
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
    request = urllib.request.Request(str(url), headers=headers)
    opener = build_url_opener()
    with opener.open(request, timeout=max(1, int(timeout))) as response:
        return response.read()


def configured_proxy_url() -> str:
    for name in ("DOUBAN_RECOMMENDER_HTTP_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY"):
        value = os.environ.get(name) or os.environ.get(name.lower())
        if value:
            return value.strip()
    return ""


def build_url_opener():
    proxy = configured_proxy_url()
    if not proxy:
        return urllib.request.build_opener()
    return urllib.request.build_opener(urllib.request.ProxyHandler({
        "http": proxy,
        "https": proxy,
    }))


def subject_detail_urls(item: MediaItem) -> list[str]:
    subject_id = item.douban_id or extract_douban_id(item.url)
    urls: list[str] = []
    if subject_id and str(subject_id).isdigit():
        mobile = f"https://m.douban.com/movie/subject/{subject_id}/"
        desktop = f"https://movie.douban.com/subject/{subject_id}/"
        for url in (mobile, desktop):
            if url not in urls:
                urls.append(url)
    if item.url and "movie.douban.com/subject/" in item.url and item.url not in urls:
        urls.append(item.url)
    return urls


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
