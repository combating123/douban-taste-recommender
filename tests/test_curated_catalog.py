import unittest

from douban_recommender.curated_catalog import (
    apply_curated_people_photos,
    apply_curated_posters,
    backfill_missing_media_types,
    curated_seed_candidates,
    premium_expansion_candidates,
)
from douban_recommender import curated_catalog as catalog
from douban_recommender.eligibility import is_animated_series
from douban_recommender.models import MediaItem


class CuratedCatalogTests(unittest.TestCase):
    def test_curated_seed_candidates_include_movie_series_and_anime(self):
        items = curated_seed_candidates()
        media_types = {item.media_type for item in items}

        self.assertIn("电影", media_types)
        self.assertIn("电视剧", media_types)
        self.assertIn("动漫", media_types)
        self.assertGreaterEqual(len([item for item in items if item.media_type == "动漫"]), 10)
        self.assertTrue(all(item.douban_id for item in items))
        self.assertTrue(all(item.summary for item in items))
        self.assertTrue(all(item.cover.startswith("https://img") for item in items))

    def test_curated_poster_map_fills_known_sample_candidates(self):
        items = [
            MediaItem(title="控方证人", douban_id="1296141", media_type="电影"),
            MediaItem(title="漫长的季节", douban_id="35465232", media_type="电视剧"),
            MediaItem(title="孤独摇滚！", douban_id="35366293", media_type="动漫"),
        ]

        apply_curated_posters(items)

        self.assertTrue(all(item.cover for item in items))
        self.assertTrue(all("doubanio.com/view/photo" in item.cover for item in items))

    def test_curated_people_photo_map_fills_known_creators_and_cast(self):
        items = [
            MediaItem(
                title="寄生虫",
                douban_id="27010768",
                media_type="电影",
                directors=["奉俊昊"],
                casts=["宋康昊", "李善均"],
            ),
            MediaItem(
                title="漫长的季节",
                douban_id="35465232",
                media_type="电视剧",
                directors=["辛爽"],
                casts=["范伟", "秦昊"],
            ),
            MediaItem(
                title="隐秘的角落",
                douban_id="33404425",
                media_type="电视剧",
                directors=["辛爽"],
                casts=["秦昊", "王景春", "荣梓杉"],
            ),
            MediaItem(
                title="控方证人",
                douban_id="1296141",
                media_type="电影",
                directors=["比利·怀尔德"],
                casts=["泰隆·鲍华", "玛琳·黛德丽"],
            ),
            MediaItem(
                title="孤独摇滚！",
                douban_id="35366293",
                media_type="动漫",
                directors=["斋藤圭一郎"],
                casts=["青山吉能"],
            ),
        ]

        apply_curated_people_photos(items)

        for item in items:
            photos = item.raw.get("people_photos", {})
            self.assertGreaterEqual(len(photos), 2)
            self.assertTrue(all(url.startswith("https://") for url in photos.values()))

        hidden_corner = items[2].raw.get("people_photos", {})
        for name in ["辛爽", "秦昊", "王景春", "荣梓杉"]:
            self.assertIn(name, hidden_corner)

    def test_curated_anime_pool_is_series_not_animated_movies(self):
        items = [item for item in curated_seed_candidates() if item.media_type == "动漫"]
        titles = {item.title for item in items}
        forbidden_animated_movies = {
            "千与千寻",
            "机器人总动员",
            "疯狂动物城",
            "寻梦环游记",
            "头脑特工队",
            "你的名字。",
            "红辣椒",
            "攻壳机动队",
            "天空之城",
            "龙猫",
        }

        self.assertGreaterEqual(len(items), 12)
        self.assertTrue(all("动漫剧集" in item.tags for item in items))
        self.assertFalse(titles & forbidden_animated_movies)
        self.assertNotIn("\u94a2\u4e4b\u70bc\u91d1\u672f\u5e08 FULLMETAL ALCHEMIST", titles)
        for expected in [
            "钢之炼金术师FA",
            "进击的巨人",
            "星际牛仔",
            "虫师",
            "命运石之门",
            "灵能百分百",
        ]:
            self.assertIn(expected, titles)

    def test_curated_and_premium_anime_emit_explicit_series_format_and_remain_eligible(self):
        items = [
            item
            for item in curated_seed_candidates() + premium_expansion_candidates()
            if item.media_type == "动漫"
        ]

        self.assertTrue(items)
        self.assertTrue(all(item.raw.get("format") == "SERIES" for item in items))
        self.assertTrue(all(is_animated_series(item) for item in items))

    def test_backfill_missing_media_types_only_adds_requested_missing_categories(self):
        existing = [
            MediaItem(title="已有电影", douban_id="m1", media_type="电影"),
            MediaItem(title="已有剧集", douban_id="s1", media_type="电视剧"),
        ]

        filled = backfill_missing_media_types(
            existing,
            include_movies=True,
            include_series=True,
            include_anime=True,
        )

        self.assertEqual([item.title for item in filled[:2]], ["已有电影", "已有剧集"])
        self.assertTrue(any(item.media_type == "动漫" for item in filled))
        self.assertFalse(any(item.title == "已有电影" and item.douban_id != "m1" for item in filled))

    def test_backfill_expands_default_pool_to_a_rich_minimum_per_type(self):
        existing = [
            MediaItem(title=f"电影{i}", douban_id=f"m{i}", media_type="电影")
            for i in range(5)
        ] + [
            MediaItem(title=f"剧集{i}", douban_id=f"s{i}", media_type="电视剧")
            for i in range(5)
        ]

        filled = backfill_missing_media_types(
            existing,
            include_movies=True,
            include_series=True,
            include_anime=True,
            minimum_per_type=10,
        )

        counts = {media_type: len([item for item in filled if item.media_type == media_type]) for media_type in ["电影", "电视剧", "动漫"]}
        self.assertGreaterEqual(counts["电影"], 10)
        self.assertGreaterEqual(counts["电视剧"], 10)
        self.assertGreaterEqual(counts["动漫"], 10)


    def test_curated_anime_pool_includes_global_animation_series(self):
        anime = [item for item in curated_seed_candidates() if item.media_type == "动漫"]
        countries = {country for item in anime for country in item.countries}
        titles = {item.title for item in anime}

        self.assertIn("日本", countries)
        self.assertIn("中国大陆", countries)
        self.assertIn("美国", countries)
        self.assertIn("中国奇谭", titles)
        self.assertIn("英雄联盟：双城之战", titles)
        self.assertIn("无敌少侠", titles)

    def test_curated_anime_pool_adds_non_japanese_series_depth(self):
        anime = [item for item in curated_seed_candidates() if item.media_type == "动漫"]
        titles = {item.title for item in anime}

        for title in [
            "伍六七",
            "雾山五行",
            "灵笼",
            "时光代理人",
            "爱，死亡和机器人",
            "降世神通：最后的气宗",
        ]:
            self.assertIn(title, titles)

    def test_curated_global_anime_uses_chinese_titles_and_people_photo_seeds(self):
        anime = [item for item in curated_seed_candidates() if item.media_type == "动漫"]
        items = {item.title: item for item in anime}

        for english_title in ["Arcane", "Invincible", "Love, Death & Robots", "Avatar: The Last Airbender"]:
            self.assertNotIn(english_title, items)

        for title in ["英雄联盟：双城之战", "无敌少侠", "爱，死亡和机器人", "降世神通：最后的气宗"]:
            with self.subTest(title=title):
                self.assertIn(title, items)
                item = items[title]
                self.assertGreaterEqual(len(item.raw.get("people_photos", {})), 2)
                self.assertTrue(str(item.cover).startswith("https://"))

    def test_premium_expansion_pool_can_satisfy_large_recommendation_targets(self):
        items = premium_expansion_candidates()
        media_types = {item.media_type for item in items}

        self.assertGreaterEqual(len(items), 180)
        self.assertIn("电影", media_types)
        self.assertIn("电视剧", media_types)
        self.assertIn("动漫", media_types)
        self.assertTrue(all(item.cover for item in items))
        designed_covers = [item for item in items if item.cover.startswith("data:image/svg+xml")]
        known_real_covers = [
            item
            for item in items
            if item.title in {"记忆碎片", "驾驶我的车", "兹山鱼谱", "我们的父辈", "爱，死亡和机器人"}
        ]
        self.assertGreaterEqual(len(designed_covers), 100)
        self.assertTrue(all(item.cover.startswith("https://") for item in known_real_covers))
        self.assertTrue(all(item.summary for item in items))
        self.assertEqual(len({item.douban_id for item in items}), len(items))

    def test_premium_expansion_never_reuses_other_titles_real_posters(self):
        items = premium_expansion_candidates()
        sampled = [
            item
            for item in items
            if item.title in {"教父", "美丽人生", "英雄", "暴裂无声", "可怜的东西"}
        ]

        self.assertGreaterEqual(len(sampled), 5)
        self.assertTrue(all(item.cover.startswith("data:image/svg+xml") for item in sampled))
        self.assertFalse(any("doubanio.com" in item.cover for item in sampled))

    def test_premium_designed_svg_covers_escape_fragment_markers_for_img_src(self):
        cover = premium_expansion_candidates()[0].cover
        payload = cover.split(",", 1)[1]

        self.assertIn("%23", payload)
        self.assertNotIn("#", payload)

    def test_backfill_deduplicates_titles_even_when_subject_ids_differ(self):
        filled = backfill_missing_media_types(
            [],
            include_movies=True,
            include_series=True,
            include_anime=True,
            minimum_per_type=12,
            target_total=190,
        )

        normalized_titles = [item.title.strip().casefold() for item in filled if item.title]

        self.assertEqual(len(normalized_titles), len(set(normalized_titles)))

    def test_backfill_uses_limit_as_target_when_default_pool_is_too_small(self):
        filled = backfill_missing_media_types(
            [],
            include_movies=True,
            include_series=True,
            include_anime=True,
            minimum_per_type=12,
            target_total=190,
        )

        self.assertGreaterEqual(len(filled), 190)
        counts = {media_type: len([item for item in filled if item.media_type == media_type]) for media_type in ["电影", "电视剧", "动漫"]}
        self.assertGreaterEqual(counts["电影"], 50)
        self.assertGreaterEqual(counts["电视剧"], 50)
        self.assertGreaterEqual(counts["动漫"], 50)

    def test_title_people_metadata_replaces_premium_placeholder_people(self):
        item = MediaItem(
            title="\u6d77\u8857\u65e5\u8bb0",
            douban_id="premium-\u7535\u5f71-001",
            media_type="\u7535\u5f71",
            directors=["\u955c\u5934\u8bed\u8a00\u4e13\u5bb6"],
            casts=["\u620f\u5267\u5f20\u529b\u62c5\u5f53", "\u94f6\u5e55\u7fa4\u50cf\u6838\u5fc3"],
        )

        apply_curated_people_photos([item])

        self.assertEqual(item.douban_id, "25895901")
        self.assertEqual(item.url, "https://movie.douban.com/subject/25895901/")
        self.assertEqual(item.directors, ["\u662f\u679d\u88d5\u548c"])
        self.assertEqual(
            item.casts[:4],
            ["\u7eeb\u6fd1\u9065", "\u957f\u6cfd\u96c5\u7f8e", "\u590f\u5e06", "\u5e7f\u6fd1\u94c3"],
        )
        self.assertGreaterEqual(len(item.raw.get("people_photos", {})), 5)
        self.assertTrue(catalog.is_curated_placeholder_person("\u955c\u5934\u8bed\u8a00\u4e13\u5bb6"))
        self.assertFalse(catalog.is_curated_placeholder_person("\u662f\u679d\u88d5\u548c"))

    def test_better_days_has_curated_people_metadata_and_photos(self):
        from douban_recommender.curated_catalog import apply_curated_people_photos
        from douban_recommender.models import MediaItem

        item = MediaItem(
            title="\u5c11\u5e74\u7684\u4f60",
            media_type="\u7535\u5f71",
            douban_id="30166972",
            url="https://movie.douban.com/subject/30166972/",
            directors=["\u66fe\u56fd\u7965"],
            casts=["\u5468\u51ac\u96e8", "\u6613\u70ca\u5343\u73ba", "\u5c39\u6609", "\u5468\u4e5f"],
        )

        apply_curated_people_photos([item])

        photos = item.raw.get("people_photos", {})
        self.assertGreaterEqual(len(photos), 5)
        for name in ["\u66fe\u56fd\u7965", "\u5468\u51ac\u96e8", "\u6613\u70ca\u5343\u73ba", "\u5c39\u6609", "\u5468\u4e5f"]:
            self.assertIn(name, photos)
            self.assertTrue(photos[name].startswith("http"))


    def test_premium_expansion_uses_real_titles_not_numbered_placeholders(self):
        import re

        items = premium_expansion_candidates()
        bad_titles = [item.title for item in items if re.match(r"^(?:\u7535\u5f71\u7b56\u5c55|\u5267\u96c6\u7b56\u5c55|\u52a8\u6f2b\u5267\u96c6\u7b56\u5c55)\d+$", item.title or "")]

        self.assertEqual(bad_titles, [])
        self.assertGreaterEqual(len(items), 180)
        self.assertGreaterEqual(len({item.title for item in items if item.title}), 180)

    def test_large_backfill_does_not_emit_numbered_placeholder_titles(self):
        import re

        filled = backfill_missing_media_types(
            [],
            include_movies=True,
            include_series=True,
            include_anime=True,
            minimum_per_type=12,
            target_total=190,
        )
        bad_titles = [item.title for item in filled if re.match(r"^(?:\u7535\u5f71\u7b56\u5c55|\u5267\u96c6\u7b56\u5c55|\u52a8\u6f2b\u5267\u96c6\u7b56\u5c55)\d+$", item.title or "")]

        self.assertEqual(bad_titles, [])
        self.assertGreaterEqual(len(filled), 190)



    def test_premium_expansion_uses_mainland_common_titles_for_known_international_items(self):
        items = {item.raw.get("aliases", [item.title])[0]: item for item in premium_expansion_candidates()}
        expected = {
            "Burning": "\u71c3\u70e7",
            "Rashomon": "\u7f57\u751f\u95e8",
            "The Prestige": "\u81f4\u547d\u9b54\u672f",
            "Signal": "\u4fe1\u53f7",
            "The Good Wife": "\u50b2\u9aa8\u8d24\u59bb",
            "Eat Drink Man Woman": "\u996e\u98df\u7537\u5973",
            "Hospital Playlist": "\u673a\u667a\u533b\u751f\u751f\u6d3b",
            "Attack on Titan": "\u8fdb\u51fb\u7684\u5de8\u4eba",
        }
        for original, display in expected.items():
            self.assertIn(original, items)
            self.assertEqual(items[original].title, display)

        forbidden_fragments = [
            "\u4fe1\u606f\u8bba",
            "\u7f85\u751f",
            "\u9802\u5c16",
            "\u71c3\u71d2",
            "\u300c\u6cd5\u300d",
            "\u6a5f\u667a",
            "\u9032\u64ca",
            "\u96fb\u5f71)",
        ]
        titles = [item.title for item in premium_expansion_candidates()]
        for fragment in forbidden_fragments:
            self.assertFalse(
                any(fragment in title for title in titles),
                f"premium title still contains stale display fragment {fragment!r}: {titles}",
            )

    def test_premium_expansion_uses_simplified_titles_for_visible_tail_items(self):
        items = {item.raw.get("aliases", [item.title])[0]: item for item in premium_expansion_candidates()}
        expected = {
            "The Dark Knight": "\u9ed1\u6697\u9a91\u58eb",
            "Tokyo Story": "\u4e1c\u4eac\u7269\u8bed",
            "La La Land": "\u7231\u4e50\u4e4b\u57ce",
            "Cinema Paradiso": "\u5929\u5802\u7535\u5f71\u9662",
            "Fight Club": "\u640f\u51fb\u4ff1\u4e50\u90e8",
            "The French Dispatch": "\u6cd5\u5170\u897f\u7279\u6d3e",
            "Green Book": "\u7eff\u76ae\u4e66",
            "Cowboy Bebop": "\u661f\u9645\u725b\u4ed4",
            "Kino's Journey": "\u5947\u8bfa\u4e4b\u65c5",
            "Mushishi": "\u866b\u5e08",
            "Spy x Family": "\u95f4\u8c0d\u8fc7\u5bb6\u5bb6",
            "Fullmetal Alchemist Brotherhood": "\u94a2\u4e4b\u70bc\u91d1\u672f\u5e08FA",
            "Dennou Coil": "\u7535\u8111\u7ebf\u5708",
        }

        for original, display in expected.items():
            with self.subTest(original=original):
                self.assertIn(original, items)
                self.assertEqual(items[original].title, display)

        forbidden_fragments = [
            "\u9a0e\u58eb",
            "\u6771\u4eac",
            "\u6a02\u4f86",
            "\u65b0\u5929\u5802",
            "\u9b25\u9663",
            "\u6cd5\u862d\u897f",
            "\u7da0\u76ae",
            "\u661f\u969b",
            "\u5947\u8afe",
            "\u87f2\u5e2b",
            "\u9593\u8adc",
            "FULLMETAL ALCHEMIST",
            "\u96fb\u8166\u7dda\u5708",
        ]
        titles = [item.title for item in premium_expansion_candidates()]
        for fragment in forbidden_fragments:
            self.assertFalse(
                any(fragment in title for title in titles),
                f"premium title still contains non-mainland fragment {fragment!r}: {titles}",
            )

    def test_corrected_premium_titles_receive_real_people_metadata(self):
        items = {item.title: item for item in premium_expansion_candidates()}
        expected = {
            "\u81f4\u547d\u9b54\u672f": ("\u514b\u91cc\u65af\u6258\u5f17\u00b7\u8bfa\u5170", "\u4f11\u00b7\u6770\u514b\u66fc", 2006, "\u82f1\u56fd"),
            "\u71c3\u70e7": ("\u674e\u6ca7\u4e1c", "\u5218\u4e9a\u4ec1", 2018, "\u97e9\u56fd"),
        }
        placeholder_people = {"\u955c\u5934\u8bed\u8a00\u4e13\u5bb6", "\u620f\u5267\u5f20\u529b\u62c5\u5f53", "\u94f6\u5e55\u7fa4\u50cf\u6838\u5fc3"}
        for title, (director, cast, year, country) in expected.items():
            with self.subTest(title=title):
                item = items[title]
                self.assertIn(director, item.directors)
                self.assertIn(cast, item.casts)
                self.assertEqual(item.year, year)
                self.assertIn(country, item.countries)
                self.assertTrue(item.raw.get("people_photos", {}).get(director))
                self.assertTrue(item.raw.get("people_photos", {}).get(cast))
                self.assertFalse(placeholder_people.intersection(item.directors + item.casts))

    def test_more_visible_premium_titles_replace_placeholder_people_and_seed_photos(self):
        items = {item.title: item for item in premium_expansion_candidates()}
        expected = {
            "\u7f57\u751f\u95e8": ("\u9ed1\u6cfd\u660e", "\u4e09\u8239\u654f\u90ce"),
            "\u4e03\u6b66\u58eb": ("\u9ed1\u6cfd\u660e", "\u4e09\u8239\u654f\u90ce"),
            "\u996e\u98df\u7537\u5973": ("\u674e\u5b89", "\u90ce\u96c4"),
            "\u4fe1\u53f7": ("\u91d1\u5143\u9521", "\u674e\u5e1d\u52cb"),
            "\u673a\u667a\u533b\u751f\u751f\u6d3b": ("\u7533\u5143\u6d69", "\u66f9\u653f\u595a"),
            "\u50b2\u9aa8\u8d24\u59bb": ("\u7c73\u6b47\u5c14\u00b7\u91d1", "\u6731\u4e3d\u5b89\u5a1c\u00b7\u739b\u683c\u4e3d\u4e1d"),
            "\u51b0\u8840\u66b4": ("\u8bfa\u4e9a\u00b7\u970d\u5229", "\u9a6c\u4e01\u00b7\u5f17\u745e\u66fc"),
            "\u771f\u63a2": ("\u5c3c\u514b\u00b7\u76ae\u4f50\u62c9\u6258", "\u9a6c\u4fee\u00b7\u9ea6\u5eb7\u7eb3"),
        }
        placeholder_people = set(catalog._placeholder_names_from_pools())

        for title, (director, cast) in expected.items():
            with self.subTest(title=title):
                item = items[title]
                people = item.directors + item.casts
                photos = item.raw.get("people_photos", {})
                self.assertIn(director, item.directors)
                self.assertIn(cast, item.casts)
                self.assertFalse(placeholder_people.intersection(people))
                self.assertTrue(photos.get(director), f"missing director photo for {title}")
                self.assertTrue(photos.get(cast), f"missing cast photo for {title}")
                self.assertTrue(all(str(url).startswith("https://") for url in photos.values()))
                self.assertTrue(str(item.cover).startswith("https://"), f"missing real cover for {title}")

    def test_premium_expansion_prefers_chinese_display_titles(self):
        items = premium_expansion_candidates()
        titles = {item.title for item in items}
        ascii_only_titles = [
            item.title
            for item in items
            if item.title and all(ord(char) < 128 for char in item.title if char.strip())
        ]

        self.assertLess(
            len(ascii_only_titles) / len(items),
            0.20,
            f"Too many English-only display titles: {ascii_only_titles[:25]}",
        )
        for english_title in [
            "Memento",
            "Drive My Car",
            "The Book of Fish",
            "Generation War",
            "Love Death and Robots",
            "Fog Hill of Five Elements",
            "Yao Chinese Folktales",
            "Steins Gate",
            "Girls Last Tour",
        ]:
            self.assertNotIn(english_title, titles)
        for chinese_title in [
            "\u8bb0\u5fc6\u788e\u7247",
            "\u9a7e\u9a76\u6211\u7684\u8f66",
            "\u5179\u5c71\u9c7c\u8c31",
            "\u6211\u4eec\u7684\u7236\u8f88",
            "\u7231\uff0c\u6b7b\u4ea1\u548c\u673a\u5668\u4eba",
            "\u96fe\u5c71\u4e94\u884c",
            "\u4e2d\u56fd\u5947\u8c2d",
            "\u547d\u8fd0\u77f3\u4e4b\u95e8",
            "\u5c11\u5973\u7ec8\u672b\u65c5\u884c",
        ]:
            self.assertIn(chinese_title, titles)

    def test_premium_expansion_emits_no_mojibake_titles_or_summaries(self):
        items = premium_expansion_candidates()

        mojibake = [
            (item.title, item.summary)
            for item in items
            if "?" in (item.title or "") or "?" in (item.summary or "")
        ]

        self.assertEqual(mojibake, [])

    def test_premium_expansion_applies_known_metadata_to_generated_items(self):
        items = {item.title: item for item in premium_expansion_candidates()}

        for title in [
            "\u8bb0\u5fc6\u788e\u7247",
            "\u9a7e\u9a76\u6211\u7684\u8f66",
            "\u5179\u5c71\u9c7c\u8c31",
            "\u6211\u4eec\u7684\u7236\u8f88",
            "\u7231\uff0c\u6b7b\u4ea1\u548c\u673a\u5668\u4eba",
        ]:
            with self.subTest(title=title):
                item = items[title]
                self.assertTrue(item.douban_id and item.douban_id.isdigit())
                self.assertGreaterEqual(len(item.raw.get("people_photos", {})), 2)
                self.assertTrue(item.url.endswith(f"/subject/{item.douban_id}/"))
                self.assertTrue(item.cover.startswith("https://"))
                self.assertFalse(item.cover.startswith("data:image/svg+xml"))

    def test_expansion_title_metadata_replaces_placeholder_people_for_common_titles(self):
        items = [
            MediaItem(
                title=title,
                douban_id=f"premium-\u6d4b\u8bd5-{index}",
                media_type=media_type,
                directors=["\u955c\u5934\u8bed\u8a00\u4e13\u5bb6"],
                casts=["\u620f\u5267\u5f20\u529b\u62c5\u5f53", "\u94f6\u5e55\u7fa4\u50cf\u6838\u5fc3"],
            )
            for index, (title, media_type) in enumerate([
                ("\u8bb0\u5fc6\u788e\u7247", "\u7535\u5f71"),
                ("\u9a7e\u9a76\u6211\u7684\u8f66", "\u7535\u5f71"),
                ("\u5179\u5c71\u9c7c\u8c31", "\u7535\u5f71"),
                ("\u6211\u4eec\u7684\u7236\u8f88", "\u7535\u89c6\u5267"),
                ("\u7231\uff0c\u6b7b\u4ea1\u548c\u673a\u5668\u4eba", "\u52a8\u6f2b"),
            ])
        ]

        apply_curated_people_photos(items)

        for item in items:
            with self.subTest(title=item.title):
                self.assertTrue(item.douban_id and item.douban_id.isdigit())
                self.assertFalse(any(catalog.is_curated_placeholder_person(name) for name in item.directors))
                self.assertFalse(any(catalog.is_curated_placeholder_person(name) for name in item.casts))
                photos = item.raw.get("people_photos", {})
                self.assertGreaterEqual(len(photos), 2)
                self.assertTrue(all(str(url).startswith("https://") for url in photos.values()))

    def test_current_high_frequency_recommendations_have_people_photo_seeds(self):
        items = [
            MediaItem(title="\u5341\u4e8c\u6012\u6c49", douban_id="1293182", media_type="\u7535\u5f71", directors=["\u897f\u5fb7\u5c3c\u00b7\u5415\u7f8e\u7279"], casts=["\u4ea8\u5229\u00b7\u65b9\u8fbe"]),
            MediaItem(title="\u8fa9\u62a4\u4eba", douban_id="21937445", media_type="\u7535\u5f71", directors=["\u6768\u5b87\u7855"], casts=["\u5b8b\u5eb7\u660a"]),
            MediaItem(title="\u5760\u843d\u7684\u5ba1\u5224", douban_id="35633650", media_type="\u7535\u5f71", directors=["\u8339\u65af\u6c40\u00b7\u7279\u91cc\u8036"], casts=["\u6851\u5fb7\u62c9\u00b7\u60e0\u52d2"]),
            MediaItem(title="\u6a21\u8303\u51fa\u79df\u8f66", douban_id="35206444", media_type="\u7535\u89c6\u5267", directors=["\u6734\u4fca\u5b87"], casts=["\u674e\u5e1d\u52cb"]),
        ]

        apply_curated_people_photos(items)

        for item in items:
            with self.subTest(title=item.title):
                photos = item.raw.get("people_photos", {})
                self.assertGreaterEqual(len(photos), 1)
                self.assertTrue(all(str(url).startswith("http") for url in photos.values()))

    def test_high_visibility_anime_have_real_people_photo_seeds(self):
        items = {item.title: item for item in curated_seed_candidates()}

        for title in ["\u661f\u9645\u725b\u4ed4", "\u6df7\u6c8c\u6b66\u58eb", "\u866b\u5e08"]:
            with self.subTest(title=title):
                item = items[title]
                photos = item.raw.get("people_photos", {})
                self.assertGreaterEqual(len(photos), 2)
                self.assertIn(item.directors[0], photos)
                self.assertTrue(any(cast in photos for cast in item.casts[:3]))
                self.assertTrue(all(str(url).startswith("https://") for url in photos.values()))

    def test_anime_title_metadata_replaces_placeholder_people_for_restored_rows(self):
        items = [
            MediaItem(
                title=title,
                douban_id=f"premium-anime-{index}",
                media_type="\u52a8\u6f2b",
                directors=["\u52a8\u753b\u76d1\u7763"],
                casts=["\u58f0\u4f18A", "\u58f0\u4f18B"],
            )
            for index, title in enumerate(["\u661f\u9645\u725b\u4ed4", "\u6df7\u6c8c\u6b66\u58eb", "\u866b\u5e08"])
        ]

        apply_curated_people_photos(items)

        for item in items:
            with self.subTest(title=item.title):
                self.assertTrue(item.douban_id.isdigit())
                self.assertFalse(any(catalog.is_curated_placeholder_person(name) for name in item.directors + item.casts))
                photos = item.raw.get("people_photos", {})
                self.assertGreaterEqual(len(photos), 2)
                self.assertIn(item.directors[0], photos)


if __name__ == "__main__":
    unittest.main()
