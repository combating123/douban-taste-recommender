import unittest

from douban_recommender.curated_catalog import backfill_missing_media_types, curated_seed_candidates
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
        for expected in [
            "钢之炼金术师 FULLMETAL ALCHEMIST",
            "进击的巨人",
            "星际牛仔",
            "虫师",
            "命运石之门",
            "灵能百分百",
        ]:
            self.assertIn(expected, titles)

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


if __name__ == "__main__":
    unittest.main()
