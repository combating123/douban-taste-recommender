import json
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from douban_recommender.catalog_api import CatalogApi
from douban_recommender.database import AppDatabase
from douban_recommender.exploration_service import (
    ExplorationService,
    LibraryRecord,
    MultiFocusCandidate,
    _select_multi_focus_batch,
)
from douban_recommender.models import MediaItem, recommendation_identity_tokens
from douban_recommender.web import Handler
import douban_recommender.web as web_module

from douban_recommender.intent_parser import (
    RecommendationIntent,
    intent_to_chips,
    parse_recommendation_intent,
)


class DiscoveryIntentTests(unittest.TestCase):
    def test_intent_round_trip_preserves_reference_similarity_and_mood_axes(self):
        original = RecommendationIntent(
            reference_titles=("星际穿越",),
            similarity_mode="balanced",
            pace_axis=0.75,
            atmosphere_axis=-0.5,
            cognitive_load_axis=0.25,
            emotional_intensity_axis=0.6,
        )

        restored = RecommendationIntent.from_dict(original.to_dict())

        self.assertEqual(restored, original)

    def test_parses_quoted_reference_and_relative_mood_language(self):
        intent = parse_recommendation_intent(
            "我想看和《星际穿越》类似，但轻松一点、节奏快一点"
        )

        self.assertEqual(intent.reference_titles, ("星际穿越",))
        self.assertEqual(intent.similarity_mode, "balanced")
        self.assertIn("轻松", intent.moods)
        self.assertEqual(intent.pace, "fast")
        self.assertLess(intent.cognitive_load_axis, 0)
        self.assertGreater(intent.pace_axis, 0)

    def test_parses_unquoted_reference_from_people_who_like_phrase(self):
        intent = parse_recommendation_intent("喜欢三体的还喜欢什么")

        self.assertEqual(intent.reference_titles, ("三体",))

    def test_similarity_mode_phrases_select_recommended_exploration_levels(self):
        faithful = parse_recommendation_intent("更像原作")
        balanced = parse_recommendation_intent("平衡发现")
        surprise = parse_recommendation_intent("给我惊喜")

        self.assertEqual(faithful.similarity_mode, "faithful")
        self.assertEqual(balanced.similarity_mode, "balanced")
        self.assertEqual(surprise.similarity_mode, "surprise")
        self.assertLess(faithful.exploration_level, balanced.exploration_level)
        self.assertLess(balanced.exploration_level, surprise.exploration_level)

    def test_reference_and_mood_axes_are_exposed_as_removable_chips(self):
        intent = parse_recommendation_intent(
            "类似《琅琊榜》，但更明快、节奏快一点"
        )

        chips = intent_to_chips(intent)
        labels = [chip.label for chip in chips]

        self.assertIn("参考：《琅琊榜》", labels)
        self.assertIn("氛围：更明快", labels)
        self.assertIn("节奏：更紧凑", labels)


class DiscoveryServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = AppDatabase(self.root / "discovery.db")
        self.database.initialize()
        self.now = 1_900_000_000.0
        self._seed_catalog()
        self.service = ExplorationService(self.database, media_root=self.root / "media")
        self.api = CatalogApi(self.database, media_root=self.root / "media", service=self.service)

    def tearDown(self):
        self.temp.cleanup()

    def _insert(self, douban_id, title, *, state="candidate", **overrides):
        payload = {
            "title": title,
            "media_type": "电影",
            "year": 2020,
            "douban_rating": 8.0,
            "vote_count": 10000,
            "genres": ["剧情"],
            "countries": ["中国大陆"],
            "directors": [],
            "casts": [],
            "tags": [],
            "douban_id": douban_id,
            "summary": f"{title} 的可靠剧情元数据。",
            "raw": {},
        }
        payload.update(overrides)
        key = f"douban:{douban_id}"
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO library_items(
                    item_key, payload_json, state, source, created_at, updated_at
                ) VALUES(?, ?, ?, 'discovery-fixture', ?, ?)
                """,
                (
                    key,
                    json.dumps(payload, ensure_ascii=False),
                    state,
                    self.now,
                    self.now,
                ),
            )
        self.now += 1
        return key

    def _seed_catalog(self):
        self.three_body_series = self._insert(
            "three-body-series",
            "三体",
            media_type="电视剧",
            year=2023,
            douban_rating=8.7,
            vote_count=520000,
            countries=["中国大陆"],
            genres=["科幻", "剧情"],
            raw={"aliases": ["Three-Body", "三体剧版"]},
        )
        self.three_body_animation = self._insert(
            "three-body-animation",
            "三体",
            media_type="动漫",
            year=2022,
            douban_rating=4.5,
            vote_count=180000,
            countries=["中国大陆"],
            genres=["科幻", "动画"],
        )
        self.space = self._insert(
            "space",
            "星际穿越",
            state="watched",
            year=2014,
            media_type="电影",
            my_rating=5,
            douban_rating=9.4,
            vote_count=2100000,
            genres=["科幻", "剧情", "冒险"],
            countries=["美国", "英国"],
            directors=["克里斯托弗·诺兰"],
            tags=["宏大叙事", "烧脑", "亲情"],
            raw={"discovery": {"pace": 0.35, "atmosphere": 0.15, "cognitive_load": 0.8, "emotional_intensity": 0.75}},
        )
        self.romance = self._insert(
            "romance",
            "花样年华",
            state="watched",
            year=2000,
            media_type="电影",
            my_rating=5,
            douban_rating=8.8,
            vote_count=650000,
            genres=["剧情", "爱情"],
            countries=["中国香港"],
            directors=["王家卫"],
            tags=["克制", "细腻情感", "视觉风格"],
            raw={"discovery": {"pace": -0.65, "atmosphere": 0.35, "cognitive_load": 0.2, "emotional_intensity": 0.55}},
        )
        self.arrival = self._insert(
            "arrival",
            "降临",
            year=2016,
            douban_rating=7.8,
            vote_count=620000,
            genres=["科幻", "剧情"],
            countries=["美国"],
            tags=["语言", "烧脑", "细腻情感"],
            raw={"discovery": {"pace": 0.15, "atmosphere": 0.35, "cognitive_load": 0.85, "emotional_intensity": 0.7}},
        )
        self.mars = self._insert(
            "mars",
            "火星救援",
            year=2015,
            douban_rating=8.5,
            vote_count=900000,
            genres=["科幻", "冒险"],
            countries=["美国", "英国"],
            tags=["太空", "乐观", "求生"],
            raw={"discovery": {"pace": 0.65, "atmosphere": -0.35, "cognitive_load": 0.45, "emotional_intensity": 0.45}},
        )
        self.before_sunrise = self._insert(
            "before-sunrise",
            "爱在黎明破晓前",
            year=1995,
            douban_rating=8.8,
            vote_count=720000,
            genres=["剧情", "爱情"],
            countries=["美国"],
            tags=["对话", "细腻情感", "浪漫"],
            raw={"discovery": {"pace": -0.55, "atmosphere": -0.25, "cognitive_load": 0.15, "emotional_intensity": 0.5}},
        )
        self.source_code = self._insert(
            "source-code",
            "源代码",
            year=2011,
            douban_rating=8.5,
            vote_count=980000,
            genres=["科幻", "悬疑"],
            countries=["美国"],
            tags=["烧脑", "高能", "时间循环"],
            raw={"discovery": {"pace": 0.95, "atmosphere": 0.1, "cognitive_load": 0.9, "emotional_intensity": 0.8}},
        )
        self.slow_drama = self._insert(
            "slow-drama",
            "海边的曼彻斯特",
            year=2016,
            douban_rating=8.6,
            vote_count=620000,
            genres=["剧情"],
            countries=["美国"],
            tags=["缓慢", "压抑"],
            raw={"discovery": {"pace": -0.9, "atmosphere": 0.9, "cognitive_load": 0.1, "emotional_intensity": 0.8}},
        )
        self.seen_candidate = self._insert(
            "seen",
            "盗梦空间",
            state="watched",
            year=2010,
            my_rating=5,
            douban_rating=9.4,
            genres=["科幻", "剧情"],
            tags=["烧脑"],
        )
        self.horror = self._insert(
            "horror",
            "深空惊魂",
            genres=["科幻", "恐怖"],
            tags=["恐怖", "血腥"],
        )

    def test_title_search_prioritizes_exact_match_and_media_hint_with_badge(self):
        response = self.service.search_titles("三体", limit=4, media_hint="电视剧")

        self.assertEqual(response["items"][0]["id"], self.three_body_series)
        self.assertEqual(response["items"][0]["media_badge"]["label"], "剧集")
        self.assertEqual(response["items"][0]["year"], 2023)
        self.assertIn("中国大陆", response["items"][0]["countries"])
        self.assertEqual(len({item["id"] for item in response["items"]}), len(response["items"]))

    def test_title_search_matches_alias_without_weakening_exact_title_order(self):
        response = self.service.search_titles("Three-Body", limit=4)

        self.assertEqual(response["items"][0]["id"], self.three_body_series)
        self.assertEqual(response["items"][0]["match_kind"], "alias")

    def test_similar_titles_exclude_seen_focus_and_permanent_avoid_with_grounded_reason(self):
        intent = RecommendationIntent(permanent_avoid=("恐怖",))

        response = self.service.similar_titles(
            self.space,
            mode="balanced",
            intent=intent,
            limit=8,
        )
        ids = [item["id"] for item in response["items"]]

        self.assertNotIn(self.space, ids)
        self.assertNotIn(self.seen_candidate, ids)
        self.assertNotIn(self.horror, ids)
        self.assertIn(self.arrival, ids)
        self.assertTrue(response["items"][0]["explanation"])
        self.assertNotIn("%", response["items"][0]["explanation"])
        self.assertTrue(response["items"][0]["evidence"])

    def test_similar_titles_expose_candidate_specific_reason_and_structured_evidence(self):
        response = self.service.similar_titles(self.space, mode="balanced", limit=8)

        self.assertGreaterEqual(len(response["items"]), 3)
        reasons = []
        for item in response["items"]:
            with self.subTest(item=item["item_key"]):
                self.assertTrue(item["primary_reason"])
                self.assertEqual(item["primary_reason"], item["explanation"])
                self.assertIn(f"《{item['title']}》", item["primary_reason"])
                self.assertTrue(item["reason_evidence"])
                self.assertTrue(item["reason_chips"])
                self.assertTrue(all(row.get("label") and row.get("value") for row in item["reason_evidence"]))
                reasons.append(item["primary_reason"])
        self.assertEqual(len(reasons), len(set(reasons)))

    def test_similar_titles_collapse_same_visible_title_and_media_type_even_when_years_differ(self):
        first = self._insert(
            "duplicate-visible-a",
            "星海回响",
            year=2024,
            genres=["科幻", "剧情"],
            countries=["美国"],
            directors=["克里斯托弗·诺兰"],
            tags=["宏大叙事", "烧脑"],
        )
        second = self._insert(
            "duplicate-visible-b",
            "星海回响",
            year=None,
            genres=["科幻", "剧情"],
            countries=["美国"],
            directors=["克里斯托弗·诺兰"],
            tags=["宏大叙事", "烧脑"],
        )

        response = self.service.similar_titles(self.space, mode="balanced", limit=30)
        duplicates = [
            item for item in response["items"]
            if item["title"] == "星海回响" and item["media_type"] == "电影"
        ]

        self.assertEqual(1, len(duplicates))
        self.assertIn(duplicates[0]["item_key"], {first, second})

    def test_blend_weight_changes_source_affinity_and_returns_three_part_explanation(self):
        left_heavy = self.service.blend_titles(
            self.space,
            self.romance,
            left_weight=0.85,
            limit=8,
        )
        right_heavy = self.service.blend_titles(
            self.space,
            self.romance,
            left_weight=0.15,
            limit=8,
        )
        left_ids = [item["id"] for item in left_heavy["items"]]
        right_ids = [item["id"] for item in right_heavy["items"]]

        self.assertLess(left_ids.index(self.mars), left_ids.index(self.before_sunrise))
        self.assertLess(right_ids.index(self.before_sunrise), right_ids.index(self.mars))
        fusion = next(item for item in left_heavy["items"] if item["id"] == self.arrival)
        self.assertTrue(fusion["explanation"]["from_left"])
        self.assertTrue(fusion["explanation"]["from_right"])
        self.assertTrue(fusion["explanation"]["fusion"])

    def test_multi_focus_discovery_prioritizes_shared_intersection_and_labels_mixed_fill(self):
        english_only = self._insert(
            "english-only-intersection",
            "English Only Candidate",
            genres=["科幻", "剧情"],
            tags=["烧脑", "细腻情感"],
            cover="https://img3.doubanio.com/view/photo/s_ratio_poster/public/p29990002.jpg",
            raw={"provider_ids": {"tmdb": "29990002"}},
        )
        response = self.service.multi_focus_titles(
            [self.space, self.romance],
            limit=8,
        )

        self.assertEqual([self.space, self.romance], [seed["item_key"] for seed in response["seeds"]])
        self.assertEqual([self.space, self.romance], response["graph"]["focus_ids"])
        self.assertEqual({self.space, self.romance}, {node["id"] for node in response["graph"]["nodes"] if node.get("is_seed")})
        arrival = next(item for item in response["items"] if item["item_key"] == self.arrival)
        self.assertEqual(2, arrival["matched_seed_count"])
        self.assertEqual("intersection", arrival["match_kind"])
        self.assertIn("同时匹配", arrival["explanation"])
        strict_ids = {item["item_key"] for item in response["items"] if item["match_kind"] == "intersection"}
        self.assertEqual({self.arrival}, strict_ids)
        self.assertEqual(1, response["strict_count"])
        self.assertNotIn(english_only, {item["item_key"] for item in response["items"]})
        self.assertTrue(any(edge["target"] == self.arrival and edge["source"] == self.space for edge in response["graph"]["edges"]))
        self.assertTrue(any(edge["target"] == self.arrival and edge["source"] == self.romance for edge in response["graph"]["edges"]))

    def test_multi_focus_response_exposes_non_empty_fusion_recipe_and_candidate_reasons(self):
        response = self.service.multi_focus_titles([self.space, self.romance], limit=8)

        profile = response["fusion_profile"]
        self.assertTrue(profile["headline"])
        self.assertTrue(profile["strategy"])
        self.assertTrue(profile["dimensions"])
        self.assertGreater(profile["weights"]["语义相似"], 0)
        self.assertGreater(profile["weights"]["焦点覆盖"], 0)
        self.assertTrue(response["items"])
        for item in response["items"]:
            with self.subTest(item=item["item_key"]):
                self.assertTrue(item["primary_reason"])
                self.assertTrue(item["reason_evidence"])
                self.assertTrue(item["reason_chips"])
                self.assertEqual(item["primary_reason"], item["explanation"])

    def test_multi_focus_discovery_single_seed_rebuilds_a_centered_similarity_graph(self):
        response = self.service.multi_focus_titles([self.space], limit=6)

        self.assertEqual("single", response["selection_mode"])
        self.assertEqual(self.space, response["graph"]["focus_id"])
        self.assertEqual([self.space], response["graph"]["focus_ids"])
        self.assertEqual(self.space, response["graph"]["nodes"][0]["id"])
        self.assertTrue(response["items"])
        self.assertTrue(all(edge["source"] == self.space for edge in response["graph"]["edges"]))

    def test_multi_focus_uses_curated_metadata_to_bridge_sparse_candidates(self):
        sparse = self._insert(
            "sparse-black-mirror",
            "黑镜",
            year=2011,
            genres=[],
            countries=[],
            directors=[],
            casts=[],
            tags=[],
            summary="",
            raw={"provider_ids": {"douban": "sparse-black-mirror"}},
        )

        response = self.service.multi_focus_titles([self.space], limit=30)
        item = next(
            (candidate for candidate in response["items"] if candidate["item_key"] == sparse),
            None,
        )

        self.assertIsNotNone(item)
        self.assertIn("科幻", item["genres"])
        self.assertTrue(item["explanation"])

    def test_multi_focus_rounds_exclude_duplicate_identity_tokens(self):
        def candidate(key, provider_id, score, title="同一部作品"):
            item = MediaItem(
                title=title,
                year=2024,
                media_type="电影",
                douban_id=key,
                raw={"provider_ids": {"tmdb": provider_id}},
            )
            record = LibraryRecord(key, item, {"title": item.title}, "candidate", "test", 0, 0)
            return MultiFocusCandidate(
                record=record,
                connections=((score, ("共同类型：科幻",), True),),
                matched_count=1,
                score=score,
                quality=0.5,
                is_intersection=True,
            )

        ranked = [
            candidate("external:first", "same-work", 0.99),
            candidate("external:second", "same-work", 0.98),
            candidate("external:third", "different-work", 0.97, title="另一部作品"),
        ]
        first = _select_multi_focus_batch(ranked, batch_size=1, round_index=0, seed_key="identity")
        second = _select_multi_focus_batch(ranked, batch_size=1, round_index=1, seed_key="identity")

        first_tokens = set().union(*(recommendation_identity_tokens(row.record.item) for row in first))
        second_tokens = set().union(*(recommendation_identity_tokens(row.record.item) for row in second))
        self.assertTrue(first)
        self.assertTrue(second)
        self.assertTrue(first_tokens.isdisjoint(second_tokens))

    def test_multi_focus_out_of_range_round_returns_terminal_batch_metadata(self):
        response = self.service.multi_focus_titles([self.space], limit=8, round_index=99)

        self.assertEqual([], response["items"])
        self.assertFalse(response["has_more"])
        self.assertIsNone(response["next_round"])

    def test_real_poster_record_wins_duplicate_collapse_and_repairs_placeholder_detail(self):
        provider = {"provider_ids": {"douban": "29990001"}}
        real = self._insert(
            "poster-real",
            "海报修复测试片",
            cover="https://img3.doubanio.com/view/photo/s_ratio_poster/public/p29990001.jpg",
            raw=provider,
        )
        placeholder = self._insert(
            "poster-placeholder",
            "海报修复测试片",
            cover="data:image/svg+xml,<svg></svg>",
            directors=["资料更完整的导演"],
            casts=["资料更完整的演员"],
            tags=["资料更完整"],
            raw=provider,
        )

        search = self.service.search_titles("海报修复测试片", limit=4)
        detail = self.service.title(placeholder)

        self.assertEqual(real, search["items"][0]["item_key"])
        self.assertEqual("ready", detail["poster"]["media_status"])
        self.assertTrue(detail["poster"]["url"].startswith("/api/image-proxy?url="))

    def test_natural_query_uses_mood_axes_and_returns_structured_chips(self):
        response = self.service.discover_from_query(
            "今晚想看节奏快一点、烧脑、情绪强烈",
            limit=8,
        )
        ids = [item["id"] for item in response["items"]]

        self.assertLess(ids.index(self.source_code), ids.index(self.slow_drama))
        self.assertEqual(response["intent"]["pace_axis"], 0.7)
        self.assertTrue(any(chip["key"] == "pace_axis" for chip in response["chips"]))

    def test_library_collapses_cross_source_records_that_share_provider_identity(self):
        first = self._insert(
            "tvmaze-3415",
            "科幻真史",
            state="wish",
            year=2014,
            media_type="电视剧",
            genres=["纪录片", "科幻"],
            raw={
                "provider_ids": {"douban": "25851561"},
                "original_title": "The Real History of Science Fiction",
            },
        )
        second = self._insert(
            "tvmaze-11054",
            "The Real History of Science Fiction",
            state="wish",
            year=2014,
            media_type="电视剧",
            genres=["纪录片", "科幻"],
            raw={
                "provider_ids": {"douban": "25851561"},
                "original_title": "The Real History of Science Fiction",
            },
        )

        response = self.service.library(limit=100)
        duplicate_ids = {first, second} & {item["item_key"] for item in response["items"]}

        self.assertEqual(1, len(duplicate_ids))

    def test_universe_collapses_cross_source_records_that_share_provider_identity(self):
        first = self._insert(
            "universe-copy-a",
            "科幻真史",
            year=2014,
            media_type="电视剧",
            genres=["科幻", "纪录片"],
            countries=["英国"],
            tags=["太空", "科学史"],
            raw={
                "provider_ids": {"douban": "25851561"},
                "original_title": "The Real History of Science Fiction",
            },
        )
        second = self._insert(
            "universe-copy-b",
            "The Real History of Science Fiction",
            year=2014,
            media_type="电视剧",
            genres=["科幻", "纪录片"],
            countries=["英国"],
            tags=["太空", "科学史"],
            raw={
                "provider_ids": {"douban": "25851561"},
                "original_title": "The Real History of Science Fiction",
            },
        )

        response = self.service.build_universe_graph(self.space, limit=25)
        node_ids = {node["id"] for node in response["nodes"]}
        duplicate_ids = {first, second} & node_ids

        self.assertEqual(1, len(duplicate_ids))
        self.assertTrue(
            all(edge["source"] in node_ids and edge["target"] in node_ids for edge in response["edges"])
        )

    def test_universe_excludes_cross_source_copy_of_focus_identity(self):
        focus = self._insert(
            "universe-focus",
            "黑镜",
            state="watched",
            year=2011,
            media_type="电视剧",
            genres=["科幻", "剧情"],
            countries=["英国"],
            tags=["科技", "反乌托邦"],
            raw={
                "provider_ids": {"imdb": "tt2085059"},
                "original_title": "Black Mirror",
            },
        )
        focus_copy = self._insert(
            "universe-focus-copy",
            "Black Mirror",
            year=2011,
            media_type="电视剧",
            genres=["科幻", "剧情"],
            countries=["英国"],
            tags=["科技", "反乌托邦"],
            raw={
                "provider_ids": {"imdb": "tt2085059"},
                "original_title": "Black Mirror",
                "aliases": ["黑镜"],
            },
        )
        related = self._insert(
            "universe-related",
            "真实人类",
            year=2015,
            media_type="电视剧",
            genres=["科幻", "剧情"],
            countries=["英国"],
            tags=["科技"],
        )

        response = self.service.build_universe_graph(focus, limit=25)
        node_ids = {node["id"] for node in response["nodes"]}

        self.assertNotIn(focus_copy, node_ids)
        self.assertIn(related, node_ids)

    def test_universe_payload_exposes_documentary_series_media_badge(self):
        item_key = self._insert(
            "universe-documentary-series-badge",
            "\u79d1\u5e7b\u771f\u53f2",
            year=2014,
            media_type="\u7535\u89c6\u5267",
            genres=["\u7eaa\u5f55\u7247", "\u79d1\u5e7b"],
            countries=["\u82f1\u56fd"],
            tags=["\u79d1\u5b66\u53f2"],
        )

        response = self.service.build_universe_graph(item_key, limit=9)
        node = next(candidate for candidate in response["nodes"] if candidate["id"] == item_key)

        self.assertEqual(
            {"label": "\u7eaa\u5f55\u7247\u5267\u96c6", "icon": "tv", "tone": "cyan"},
            node["media_badge"],
        )

    def test_similar_titles_collapses_cross_source_records_that_share_provider_identity(self):
        first = self._insert(
            "provider-copy-a",
            "未来科学史",
            year=2014,
            media_type="电视剧",
            genres=["科幻", "纪录片"],
            countries=["英国"],
            tags=["科学史", "太空"],
            raw={
                "provider_ids": {"douban": "25851561"},
                "original_title": "The Real History of Science Fiction",
            },
        )
        second = self._insert(
            "provider-copy-b",
            "The Real History of Science Fiction",
            year=2014,
            media_type="电视剧",
            genres=["科幻", "纪录片"],
            countries=["英国"],
            tags=["科学史", "太空"],
            raw={
                "provider_ids": {"douban": "25851561"},
                "original_title": "The Real History of Science Fiction",
            },
        )

        response = self.service.similar_titles(self.space, limit=30)
        duplicate_ids = {first, second} & {item["id"] for item in response["items"]}

        self.assertEqual(1, len(duplicate_ids))

    def test_search_collapses_cross_source_records_that_share_provider_identity(self):
        first = self._insert(
            "true-detective-copy-a",
            "真探",
            year=2014,
            media_type="电视剧",
            raw={"provider_ids": {"imdb": "tt2356777"}},
        )
        second = self._insert(
            "true-detective-copy-b",
            "真探",
            year=2014,
            media_type="电视剧",
            raw={"provider_ids": {"imdb": "tt2356777"}},
        )

        response = self.service.search_titles("真探", limit=8)
        duplicate_ids = {first, second} & {item["id"] for item in response["items"]}

        self.assertEqual(1, len(duplicate_ids))

    def test_documentary_series_uses_specific_media_badge(self):
        item_key = self._insert(
            "documentary-series",
            "科幻真史",
            year=2014,
            media_type="电视剧",
            genres=["纪录片", "科幻"],
        )

        response = self.service.search_titles("科幻真史", limit=8)
        item = next(candidate for candidate in response["items"] if candidate["id"] == item_key)

        self.assertEqual("纪录片剧集", item["media_badge"]["label"])

    def test_title_payload_exposes_documentary_series_media_badge(self):
        item_key = self._insert(
            "documentary-title-payload",
            "神秘地图",
            year=2017,
            media_type="电视剧",
            genres=["纪录片", "冒险"],
        )

        response = self.service.title(item_key)

        self.assertEqual(
            {"label": "纪录片剧集", "icon": "tv", "tone": "cyan"},
            response["media_badge"],
        )

    def test_library_payload_exposes_documentary_series_media_badge(self):
        item_key = self._insert(
            "documentary-library-payload",
            "神秘地图",
            state="wish",
            year=2017,
            media_type="电视剧",
            genres=["纪录片", "冒险"],
        )

        response = self.service.library(state="wish", limit=100)
        item = next(candidate for candidate in response["items"] if candidate["item_key"] == item_key)

        self.assertEqual(
            {"label": "纪录片剧集", "icon": "tv", "tone": "cyan"},
            item["media_badge"],
        )

    def test_discovery_payload_exposes_verified_localized_title_fields(self):
        item_key = self._insert(
            "localized-discovery-title",
            "Mystery Map",
            year=2017,
            media_type="电视剧",
            genres=["纪录片", "冒险"],
            raw={
                "provider_ids": {"douban": "27000001"},
                "original_title": "Mystery Map",
                "aliases": ["神秘地图"],
            },
        )

        response = self.service.search_titles("Mystery Map", limit=8)
        item = next(candidate for candidate in response["items"] if candidate["id"] == item_key)

        self.assertEqual("Mystery Map", item["title"])
        self.assertEqual("神秘地图", item["display_title"])
        self.assertEqual("Mystery Map", item["original_title"])
        self.assertEqual("douban", item["title_localization_source"])

    def test_catalog_api_exposes_search_similar_query_and_blend_contracts(self):
        search = self.api.search_titles({"q": ["三体"], "limit": ["4"]})
        similar = self.api.similar_titles({"focus": [self.space], "mode": ["balanced"], "limit": ["6"]})
        query = self.api.discovery_query({"text": "类似《星际穿越》，但轻松一点", "limit": 6})
        blend = self.api.blend_titles({"left": self.space, "right": self.romance, "left_weight": 0.5, "limit": 6})
        multi = self.api.multi_focus_titles({"focus": [self.space, self.romance], "limit": ["6"]})

        self.assertEqual(search["schema_version"], 2)
        self.assertEqual(similar["focus"]["id"], self.space)
        self.assertEqual(query["matched_reference"]["id"], self.space)
        self.assertEqual(blend["sources"][0]["id"], self.space)
        self.assertEqual(blend["sources"][1]["id"], self.romance)
        self.assertEqual([self.space, self.romance], multi["graph"]["focus_ids"])

    def test_web_routes_expose_search_similar_query_and_blend(self):
        previous = getattr(web_module, "CATALOG_API", None)
        web_module.CATALOG_API = self.api
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            encoded = urllib.parse.urlencode({"q": "三体", "limit": 4})
            with urllib.request.urlopen(f"{base_url}/api/v2/titles/search?{encoded}", timeout=5) as response:
                search = json.loads(response.read().decode("utf-8"))
            request = urllib.request.Request(
                f"{base_url}/api/v2/discovery/query",
                data=json.dumps({"text": "类似《星际穿越》，但轻松一点", "limit": 5}, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                query = json.loads(response.read().decode("utf-8"))
            blend_request = urllib.request.Request(
                f"{base_url}/api/v2/discovery/blend",
                data=json.dumps({"left": self.space, "right": self.romance, "left_weight": 0.5, "limit": 5}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(blend_request, timeout=5) as response:
                blend = json.loads(response.read().decode("utf-8"))
            multi_query = urllib.parse.urlencode([
                ("focus", self.space),
                ("focus", self.romance),
                ("limit", 5),
            ])
            with urllib.request.urlopen(f"{base_url}/api/v2/discovery/multi?{multi_query}", timeout=5) as response:
                multi = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            web_module.CATALOG_API = previous

        self.assertEqual(search["items"][0]["title"], "三体")
        self.assertEqual(query["matched_reference"]["id"], self.space)
        self.assertEqual(len(blend["sources"]), 2)
        self.assertEqual([self.space, self.romance], multi["graph"]["focus_ids"])


if __name__ == "__main__":
    unittest.main()
