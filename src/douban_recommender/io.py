from __future__ import annotations

import ast
import csv
import io
import re
from pathlib import Path
from typing import Iterable

from .models import MediaItem

HEADER_ALIASES: dict[str, list[str]] = {
    "title": ["title", "name", "subject", "标题", "片名", "电影", "剧名", "名称", "条目", "条目名称"],
    "my_rating": ["my_rating", "my rate", "mine", "我的评分", "个人评分", "用户评分", "我的打分", "星级", "评分"],
    "douban_rating": ["douban_rating", "douban rate", "douban", "rate", "rating", "豆瓣评分", "平均评分", "大众评分"],
    "vote_count": ["vote_count", "votes", "ratings_count", "评价人数", "评分人数", "人数"],
    "year": ["year", "年份", "年代", "上映年份", "首播年份"],
    "media_type": ["media_type", "subject_type", "条目类型", "影视类型", "类别", "type"],
    "genres": ["genres", "genre", "类型", "分类", "风格", "题材", "genre/tags", "genres/tags"],
    "countries": ["countries", "country", "国家/地区", "国家地区", "地区", "制片国家/地区", "制片国家", "国家"],
    "languages": ["languages", "language", "语言"],
    "directors": ["directors", "director", "导演", "编导"],
    "casts": ["casts", "cast", "actors", "actor", "主演", "演员", "卡司"],
    "tags": ["tags", "tag", "标签", "我的标签", "豆瓣标签", "关键词", "口味"],
    "url": ["url", "link", "链接", "网址", "豆瓣链接", "条目链接", "subject_url"],
    "douban_id": ["douban_id", "id", "subject_id", "豆瓣id", "条目id"],
    "cover": ["cover", "poster", "海报", "封面"],
    "summary": ["summary", "desc", "description", "简介", "剧情简介", "短评", "评论", "我的短评", "备注"],
}

RATING_WORDS = {
    "很差": 1,
    "较差": 2,
    "还行": 3,
    "推荐": 4,
    "力荐": 5,
    "不喜欢": 1,
    "一般": 3,
    "喜欢": 4,
    "非常喜欢": 5,
}

MEDIA_WORDS = {"电影", "电视剧", "剧集", "美剧", "英剧", "日剧", "韩剧", "国产剧", "港剧", "台剧", "纪录片", "动画"}


def read_text_file(path: str | Path) -> str:
    data = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "big5", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def load_media_csv(path: str | Path, kind: str = "ratings") -> list[MediaItem]:
    return load_media_csv_from_text(read_text_file(path), kind=kind)


def load_media_csv_from_text(text: str, kind: str = "ratings") -> list[MediaItem]:
    text = (text or "").strip("\ufeff\n\r ")
    if not text:
        return []
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return []
    rows: list[MediaItem] = []
    for raw in reader:
        item = row_to_media_item(raw, kind=kind)
        if item and item.title:
            rows.append(item)
    return rows


def row_to_media_item(row: dict[str, str], kind: str = "ratings") -> MediaItem | None:
    normalized = {normalize_header(k): (v or "").strip() for k, v in row.items() if k is not None}
    original = {str(k): v for k, v in row.items()}

    def pick(field: str) -> str:
        aliases = [normalize_header(x) for x in HEADER_ALIASES[field]]
        for alias in aliases:
            if alias in normalized and normalized[alias] != "":
                return normalized[alias]
        return ""

    title = pick("title")
    if not title:
        for value in row.values():
            if value and str(value).strip():
                title = str(value).strip()
                break
    if not title:
        return None

    raw_genres = pick("genres")
    raw_media_type = pick("media_type")
    genres = parse_list(raw_genres)
    media_type = normalize_media_type(raw_media_type)
    if not media_type and len(genres) == 1 and genres[0] in MEDIA_WORDS:
        media_type = normalize_media_type(genres[0])
        genres = []
    if not media_type:
        for g in list(genres):
            if g in {"电影", "电视剧", "剧集", "美剧", "英剧", "日剧", "韩剧", "国产剧", "港剧", "台剧"}:
                media_type = normalize_media_type(g)
                genres.remove(g)
                break

    if kind == "ratings":
        my_rating = parse_rating(pick("my_rating"), personal=True)
        douban_rating = parse_rating(pick("douban_rating"), personal=False)
    else:
        # 候选库里“评分”通常指豆瓣/大众评分，不能按个人 1-5 星折半。
        my_rating = None
        douban_rating = parse_rating(pick("douban_rating") or pick("my_rating"), personal=False)

    item = MediaItem(
        title=title,
        my_rating=my_rating,
        douban_rating=douban_rating,
        vote_count=parse_int(pick("vote_count")),
        year=parse_year(pick("year") or title),
        media_type=media_type,
        genres=genres,
        countries=parse_list(pick("countries")),
        languages=parse_list(pick("languages")),
        directors=parse_list(pick("directors")),
        casts=parse_list(pick("casts")),
        tags=parse_list(pick("tags")),
        url=pick("url"),
        douban_id=pick("douban_id") or extract_douban_id(pick("url")),
        cover=pick("cover"),
        summary=pick("summary"),
        source="csv",
        raw=original,
    )
    return item


def normalize_header(text: str) -> str:
    text = str(text or "").strip().lower().replace("\ufeff", "")
    text = re.sub(r"[\s_\-]+", "", text)
    text = text.replace("（", "(").replace("）", ")")
    return text


def parse_list(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(x).strip() for x in value if str(x).strip()]
    text = str(value).strip()
    if not text:
        return []
    if (text.startswith("[") and text.endswith("]")) or (text.startswith("(") and text.endswith(")")):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, (list, tuple, set)):
                return parse_list(parsed)
        except Exception:
            pass
    text = re.sub(r"<br\s*/?>", "/", text, flags=re.I)
    pieces = re.split(r"\s*(?:/|、|,|，|;|；|\||\\|\n|\r|\t)\s*", text)
    out: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        p = piece.strip(" \"'[]()（）【】")
        if not p or p in seen:
            continue
        out.append(p)
        seen.add(p)
    return out


def parse_rating(value: str | float | int | None, personal: bool) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        num = float(value)
    else:
        text = str(value).strip()
        if not text or text in {"-", "无", "None", "nan"}:
            return None
        if text in RATING_WORDS:
            return float(RATING_WORDS[text])
        if "★" in text or "⭐" in text:
            return float(text.count("★") + text.count("⭐"))
        m = re.search(r"\d+(?:\.\d+)?", text)
        if not m:
            return None
        num = float(m.group(0))
    if personal and num > 5 and num <= 10:
        return round(num / 2, 2)
    return num


def parse_int(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).replace(",", "")
    m = re.search(r"\d+", text)
    return int(m.group(0)) if m else None


def parse_year(value: str | None) -> int | None:
    if not value:
        return None
    m = re.search(r"(?:19|20)\d{2}", str(value))
    return int(m.group(0)) if m else None


def extract_douban_id(url: str | None) -> str:
    if not url:
        return ""
    m = re.search(r"subject/(\d+)", url)
    return m.group(1) if m else ""


def normalize_media_type(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text in {"电视剧", "剧集", "美剧", "英剧", "日剧", "韩剧", "国产剧", "港剧", "台剧", "TV", "tv", "series"}:
        return "电视剧"
    if text in {"电影", "影片", "movie", "film", "短片", "纪录片", "动画"}:
        return "电影"
    return text
