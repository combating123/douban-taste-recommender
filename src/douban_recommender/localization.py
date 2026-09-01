from __future__ import annotations

import re
from functools import lru_cache
from typing import Mapping

try:
    from opencc import OpenCC
except ImportError:  # The launcher installs the declared dependency when needed.
    OpenCC = None


_HAN_RE = re.compile(r"[\u3400-\u9fff]")
_KANA_RE = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")
_HANGUL_RE = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]")
_SPACE_RE = re.compile(r"\s+")
_TITLE_KEY_RE = re.compile(r"[^a-z0-9]+")


# This fallback keeps startup functional even when package installation is
# temporarily unavailable. OpenCC remains the primary converter and handles
# the complete phrase/character tables.
_FALLBACK_T2S = str.maketrans({
    "惡": "恶", "獸": "兽", "總": "总", "員": "员",
    "戰": "战", "進": "进", "譚": "谭", "職": "职", "轉": "转",
    "異": "异", "後": "后", "為": "为", "這": "这", "將": "将",
    "來": "来", "還": "还", "個": "个", "與": "与", "們": "们",
    "牠": "它", "經": "经", "開": "开", "熱": "热", "鬥": "斗",
    "從": "从", "滿": "满", "嶺": "岭", "學": "学", "園": "园",
    "顧": "顾", "無": "无", "選": "选", "擇": "择", "時": "时",
    "尚": "尚", "產": "产", "業": "业", "麗": "丽", "蓮": "莲",
    "聯": "联", "終": "终", "動": "动", "畫": "画", "兒": "儿",
    "劇": "剧", "類": "类", "華": "华", "實": "实", "現": "现",
    "賊": "贼", "賽": "赛", "際": "际", "鳴": "鸣", "龍": "龙",
    "帶": "带", "體": "体", "繼": "继", "續": "续", "層": "层",
    "確": "确", "認": "认", "資": "资", "料": "料", "線": "线",
    "評": "评", "價": "价", "數": "数", "萬": "万", "達": "达",
    "導": "导", "演": "演", "節": "节", "國": "国", "華": "华",
})


_MAINLAND_PHRASE_NORMALIZATIONS: tuple[tuple[str, str], ...] = (
    ("穿著", "穿着"),
    ("衣著", "衣着"),
    ("带著", "带着"),
    ("有著", "有着"),
    ("拿著", "拿着"),
    ("跟著", "跟着"),
    ("看著", "看着"),
    ("随著", "随着"),
    ("凭著", "凭着"),
    ("靠著", "靠着"),
    ("抱著", "抱着"),
    ("著裝", "着装"),
    ("著装", "着装"),
    ("附著", "附着"),
    ("著陸", "着陆"),
    ("著陆", "着陆"),
    ("著迷", "着迷"),
    ("著手", "着手"),
    ("著眼", "着眼"),
    ("数位", "数字"),
    ("身分", "身份"),
    ("网路", "网络"),
    ("揭密", "揭秘"),
)


_MAINLAND_SUMMARY_NORMALIZATIONS: tuple[tuple[str, str], ...] = (
    ("《The Dark Knight》", "《蝙蝠侠：黑暗骑士》"),
    ("《Dallas Buyers Club》", "《达拉斯买家俱乐部》"),
    ("《Rachel Getting Married》", "《蕾切尔的婚礼》"),
    ("《Alice Doesn't Live Here Anymore》", "《爱丽丝不住在这里了》"),
    ("《The Cider House Rules》", "《苹果酒屋法则》"),
    ("《Les Misérables》", "《悲惨世界》"),
    ("《Zero Dark Thirty》", "《猎杀本·拉登》"),
    ("《Inception》", "《盗梦空间》"),
    ("《Interstellar》", "《星际穿越》"),
    ("史蒂芬·史匹柏", "史蒂文·斯皮尔伯格"),
    ("克里斯多夫·诺兰", "克里斯托弗·诺兰"),
    ("梅莉史翠普", "梅丽尔·斯特里普"),
    ("安海瑟薇", "安妮·海瑟薇"),
    ("艾蜜莉·布朗", "艾米莉·布朗特"),
    ("艾蜜莉布朗", "艾米莉·布朗特"),
    ("史丹利图奇", "斯坦利·图齐"),
    ("大卫法兰科", "大卫·弗兰科尔"),
    ("大卫·柯普", "大卫·凯普"),
    ("萝伦薇丝柏格", "劳伦·魏丝伯格"),
    ("奥黛莎杨", "奥黛莎·杨"),
    ("乔科尔", "乔·科尔"),
    ("杰森瑞特曼", "贾森·雷特曼"),
    ("伊凡瑞特曼", "伊万·雷特曼"),
    ("布兰登费雪", "布兰登·费舍"),
    ("莎蒂辛克", "萨迪·辛克"),
    ("洁西卡·雀丝坦", "杰西卡·查斯坦"),
    ("艾伦·鲍丝汀", "艾伦·伯斯汀"),
    ("米高·肯恩", "迈克尔·凯恩"),
    ("魏斯‧班特利", "韦斯·本特利"),
    ("凯西·艾佛列克", "卡西·阿弗莱克"),
    ("麦肯基·弗依", "麦肯吉·弗依"),
    ("陶佛·葛瑞斯", "托弗·戈瑞斯"),
    ("查宁塔图", "查宁·塔图姆"),
    ("杰米福克斯", "杰米·福克斯"),
    ("奇异博士史传奇", "奇异博士斯特兰奇"),
    ("魔鬼克星 未来世", "超能敢死队"),
    ("魔鬼克星", "超能敢死队"),
    ("型男飞行日志", "在云端"),
    ("约翰维克", "约翰·威克"),
    ("霍格华兹", "霍格沃茨"),
    ("蜘蛛人", "蜘蛛侠"),
    ("神秘法师", "神秘客"),
    ("小小兵", "小黄人"),
    ("太菲鸭", "达菲鸭"),
    ("教宗", "教皇"),
    ("邱吉尔", "丘吉尔"),
    ("卡司", "主演阵容"),
    ("担纲", "担任"),
    ("透过", "通过"),
    ("想像", "想象"),
    ("潜舰", "潜艇"),
    ("讯号", "信号"),
    ("「", "“"),
    ("」", "”"),
    ("『", "“"),
    ("』", "”"),
)


GENRE_TRANSLATIONS: dict[str, str] = {
    "action": "动作",
    "action & adventure": "动作 / 冒险",
    "adventure": "冒险",
    "animation": "动画",
    "anime": "动画",
    "comedy": "喜剧",
    "concert films": "演唱会",
    "crime": "犯罪",
    "documentary": "纪录片",
    "drama": "剧情",
    "ecchi": "轻度成人向",
    "family": "家庭",
    "fantasy": "奇幻",
    "foreign": "外语片",
    "history": "历史",
    "holiday": "节日",
    "horror": "恐怖",
    "independent": "独立电影",
    "kids": "儿童",
    "kids & family": "儿童 / 家庭",
    "music": "音乐",
    "musicals": "歌舞",
    "mystery": "悬疑",
    "mahou shoujo": "魔法少女",
    "mecha": "机甲",
    "psychological": "心理",
    "romance": "爱情",
    "sci-fi & fantasy": "科幻 / 奇幻",
    "sci-fi": "科幻",
    "science fiction": "科幻",
    "science-fiction": "科幻",
    "short films": "短片",
    "slice of life": "日常",
    "special interest": "专题",
    "sports": "运动",
    "supernatural": "奇幻",
    "super power": "超能力",
    "thriller": "惊悚",
    "urban": "都市",
    "war": "战争",
    "western": "西部",
}


# Exact, verified display names used by the live discovery providers.  We do
# not machine-transliterate unknown people: an omitted credit is less
# misleading than a plausible-looking but incorrect Chinese name.
PERSON_DISPLAY_NAMES: dict[str, str] = {
    "aaron horvath": "亚伦·霍瓦斯",
    "andrew stanton": "安德鲁·斯坦顿",
    "ayuko tsukahara": "塚原亚由子",
    "chad stahelski": "查德·斯塔赫斯基",
    "chris columbus": "克里斯·哥伦布",
    "christopher miller": "克里斯托弗·米勒",
    "christopher nolan": "克里斯托弗·诺兰",
    "danny boyle": "丹尼·博伊尔",
    "darren aronofsky": "达伦·阿伦诺夫斯基",
    "david frankel": "大卫·弗兰科尔",
    "david lynch": "大卫·林奇",
    "derek yee": "尔冬升",
    "edward berger": "爱德华·贝尔格",
    "edward yang": "杨德昌",
    "guy ritchie": "盖·里奇",
    "jason reitman": "贾森·雷特曼",
    "jon watts": "乔·沃茨",
    "jonathan mostow": "乔纳森·莫斯托",
    "michael jelenic": "迈克尔·杰勒尼克",
    "pawo choyning dorji": "帕武·多杰",
    "peter browngardt": "彼得·布朗加特",
    "phil lord": "菲尔·罗德",
    "pierre coffin": "皮埃尔·柯芬",
    "roland emmerich": "罗兰·艾默里奇",
    "sofia coppola": "索菲亚·科波拉",
    "steven spielberg": "史蒂文·斯皮尔伯格",
    "thordur palsson": "索杜尔·帕尔松",
    "þórður pálsson": "索杜尔·帕尔松",
}

_COMPOUND_PERSON_RE = re.compile(r"\s+(?:&|and)\s+", flags=re.I)


# Provider-id overrides are deliberately small and verified. Unknown titles
# are hidden rather than presenting a Japanese native title as Chinese.
ANIME_PROVIDER_DISPLAY_TITLES: dict[tuple[str, str], str] = {
    ("anilist", "269"): "死神",
    ("anilist", "182205"): "关于我转生变成史莱姆这档事 第4季",
    ("anilist", "185874"): "死神：千年血战篇 第4季",
    ("anilist", "189046"): "Re：从零开始的异世界生活 第4季",
    ("anilist", "178789"): "无职转生 第3季",
    ("anilist", "184492"): "入间同学入魔了 第4季",
    ("anilist", "200637"): "超超超超超喜欢你的100个女朋友 第3季",
}


ANIME_BASE_DISPLAY_TITLES: dict[str, str] = {
    "arcane": "英雄联盟：双城之战",
    "frieren": "葬送的芙莉莲",
    "frierenbeyondjourneysend": "葬送的芙莉莲",
    "onepiece": "海贼王",
    "narutoshippuden": "火影忍者：疾风传",
    "bleach": "死神",
    "mushokutensei": "无职转生",
    "mushokutenseijoblessreincarnation": "无职转生",
    "rezerokarahajimeruisekaiseikatsu": "Re：从零开始的异世界生活",
    "rezerostartinglifeinanotherworld": "Re：从零开始的异世界生活",
    "tenseishitaraslimedattaken": "关于我转生变成史莱姆这档事",
    "thattimeigotreincarnatedasaslime": "关于我转生变成史莱姆这档事",
    "mairimashitairumakun": "入间同学入魔了",
    "welcometodemonschoolirumakun": "入间同学入魔了",
    "the100girlfriendswhoreallyreallyreallyreallyreallyloveyou": "超超超超超喜欢你的100个女朋友",
}


@lru_cache(maxsize=1)
def _opencc_converter():
    return OpenCC("t2s") if OpenCC is not None else None


@lru_cache(maxsize=4096)
def to_simplified_chinese(value: object) -> str:
    text = str(value or "")
    if not text:
        return ""
    converter = _opencc_converter()
    if converter is not None:
        try:
            # OpenCC's t2s table intentionally preserves a few context-sensitive
            # Taiwan variants such as "穿著". The small post-pass normalizes the
            # UI vocabulary expected by a Mainland Simplified Chinese interface.
            text = converter.convert(text).translate(_FALLBACK_T2S)
        except (OSError, TypeError, ValueError):
            text = text.translate(_FALLBACK_T2S)
    else:
        text = text.translate(_FALLBACK_T2S)
    for source, target in _MAINLAND_PHRASE_NORMALIZATIONS:
        text = text.replace(source, target)
    return text


def localize_genre(value: object) -> str:
    text = _SPACE_RE.sub(" ", str(value or "")).strip()
    return GENRE_TRANSLATIONS.get(text.casefold(), to_simplified_chinese(text))


def localize_summary(value: object) -> str:
    text = to_simplified_chinese(value)
    for source, target in _MAINLAND_SUMMARY_NORMALIZATIONS:
        text = text.replace(source, target)
    return text


def localize_people_names(values, *, verified_only: bool = False) -> list[str]:
    """Return stable Simplified-Chinese credits without guessed transliterations."""

    localized: list[str] = []
    for value in values or ():
        raw = _SPACE_RE.sub(" ", str(value or "")).strip()
        if not raw:
            continue
        parts = _COMPOUND_PERSON_RE.split(raw) if _COMPOUND_PERSON_RE.search(raw) else [raw]
        for part in parts:
            simplified = to_simplified_chinese(part)
            mapped = PERSON_DISPLAY_NAMES.get(part.casefold(), "")
            if mapped:
                localized.append(mapped)
            elif contains_han(simplified) or not verified_only:
                localized.append(simplified)
    return _dedupe(localized)


def contains_han(value: object) -> bool:
    return bool(_HAN_RE.search(str(value or "")))


def contains_non_chinese_east_asian_script(value: object) -> bool:
    text = str(value or "")
    return bool(_KANA_RE.search(text) or _HANGUL_RE.search(text))


def is_reliable_chinese_title(value: object) -> bool:
    text = str(value or "").strip()
    if not text or contains_non_chinese_east_asian_script(text):
        return False
    return len(_HAN_RE.findall(text)) >= 2


def _dedupe(values) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or ():
        text = _SPACE_RE.sub(" ", str(value or "")).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _title_key(value: object) -> str:
    return _TITLE_KEY_RE.sub("", str(value or "").casefold())


def _season_number(values: list[str]) -> int | None:
    patterns = (
        r"\bseason\s*(\d{1,2})\b",
        r"\b(\d{1,2})(?:st|nd|rd|th)\s+season\b",
        r"\bpart\s*(\d{1,2})\b",
        r"第\s*(\d{1,2})\s*(?:季|期|部|系列)",
    )
    for value in values:
        for pattern in patterns:
            match = re.search(pattern, value, flags=re.I)
            if match:
                number = int(match.group(1))
                if 1 < number <= 20:
                    return number
    return None


def _without_season(value: str) -> str:
    text = value
    for pattern in (
        r"\s*[-:：]?\s*season\s*\d{1,2}\b.*$",
        r"\s*[-:：]?\s*\d{1,2}(?:st|nd|rd|th)\s+season\b.*$",
        r"\s*[-:：]?\s*part\s*\d{1,2}\b.*$",
        r"\s*第\s*\d{1,2}\s*(?:季|期|部|系列).*$",
    ):
        text = re.sub(pattern, "", text, flags=re.I)
    return text.strip(" -–—:：")


def _curated_title(candidates: list[str]) -> str:
    try:
        from .curated_catalog import curated_display_title_for_alias
    except (ImportError, AttributeError):
        curated_display_title_for_alias = None

    season = _season_number(candidates)
    for candidate in candidates:
        base = _without_season(candidate)
        key = _title_key(base)
        title = ANIME_BASE_DISPLAY_TITLES.get(key, "")
        if not title:
            matches = [
                (len(alias), localized)
                for alias, localized in ANIME_BASE_DISPLAY_TITLES.items()
                if len(alias) >= 6 and key.startswith(alias)
            ]
            if matches:
                title = max(matches)[1]
        if not title and curated_display_title_for_alias is not None:
            title = curated_display_title_for_alias(candidate) or curated_display_title_for_alias(base)
        title = to_simplified_chinese(title)
        if not title:
            continue
        if season and not re.search(r"第\s*\d+\s*季", title):
            title = f"{title} 第{season}季"
        return title
    return ""


def localize_anime_title(
    row: Mapping[str, object],
    *,
    provider: str = "",
) -> tuple[str, list[str]]:
    title_data = row.get("title") if isinstance(row.get("title"), dict) else {}
    synonyms = _dedupe([
        *(row.get("title_synonyms") or []),
        *(row.get("synonyms") or []),
    ])
    primary_candidates = _dedupe([
        title_data.get("english"),
        title_data.get("romaji"),
        row.get("title_english"),
        row.get("title"),
    ])
    native_candidates = _dedupe([
        title_data.get("native"),
        row.get("title_japanese"),
    ])
    all_candidates = _dedupe([*primary_candidates, *native_candidates, *synonyms])

    reliable_alias = next(
        (to_simplified_chinese(value) for value in synonyms if is_reliable_chinese_title(value)),
        "",
    )
    country = str(row.get("countryOfOrigin") or "").strip().upper()
    if not reliable_alias and country in {"CN", "TW", "HK"}:
        reliable_alias = next(
            (to_simplified_chinese(value) for value in native_candidates if is_reliable_chinese_title(value)),
            "",
        )

    clean_provider = str(provider or ("jikan" if row.get("mal_id") else "anilist" if row.get("id") else "")).strip().casefold()
    provider_id = str(row.get("mal_id") if clean_provider == "jikan" else row.get("id") or "").strip()
    verified = to_simplified_chinese(ANIME_PROVIDER_DISPLAY_TITLES.get((clean_provider, provider_id), ""))
    display_title = reliable_alias or verified or _curated_title(primary_candidates)
    aliases = [
        value
        for value in all_candidates
        if to_simplified_chinese(value).casefold() != display_title.casefold()
    ]
    return display_title, aliases
