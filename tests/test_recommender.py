import unittest

from douban_recommender.models import MediaItem
from douban_recommender.profiler import build_taste_profile
from douban_recommender.recommender import recommend


class CineScopeRecommendationTests(unittest.TestCase):
    def test_quality_first_includes_anime_and_downranks_costume_series(self):
        rated = [
            MediaItem(
                title="已看电影",
                douban_id="seen1",
                media_type="电影",
                tags=["看过"],
                my_rating=5,
            )
        ]
        candidates = [
            MediaItem(
                title="高分剧情片",
                douban_id="m1",
                media_type="电影",
                douban_rating=9.0,
                genres=["剧情"],
                summary="人物塑造扎实",
            ),
            MediaItem(
                title="高分动画",
                douban_id="a1",
                media_type="动漫",
                douban_rating=9.1,
                genres=["动画", "剧情"],
                summary="叙事强",
            ),
            MediaItem(
                title="古装大剧",
                douban_id="s1",
                media_type="电视剧",
                douban_rating=9.2,
                genres=["古装", "剧情"],
                summary="宫廷 权谋",
            ),
        ]
        profile = build_taste_profile(
            rated,
            like_terms="评分高，剧情好，叙事强",
            dislike_terms="电视剧古装，注水剧",
        )

        recs = recommend(
            rated,
            candidates,
            profile,
            limit=10,
            include_movies=True,
            include_series=True,
            include_anime=True,
        )
        titles = [rec.item.title for rec in recs]

        self.assertIn("高分动画", titles)
        self.assertGreater(
            recs[titles.index("高分剧情片")].score,
            recs[titles.index("古装大剧")].score,
        )
        self.assertTrue(any("古装" in warning for warning in recs[titles.index("古装大剧")].warnings))
        self.assertTrue(recs[0].section)
        self.assertTrue(recs[0].short_reason)

    def test_wishlist_item_is_tagged_not_excluded(self):
        rated = [MediaItem(title="想看的动画", douban_id="wish1", media_type="动漫", tags=["想看"])]
        candidates = [
            MediaItem(
                title="想看的动画",
                douban_id="wish1",
                media_type="动漫",
                douban_rating=8.8,
                genres=["动画"],
            )
        ]
        profile = build_taste_profile(rated, like_terms="动画", dislike_terms="")

        recs = recommend(rated, candidates, profile, limit=5, include_anime=True)

        self.assertEqual(len(recs), 1)
        self.assertTrue(recs[0].is_wishlist)
        self.assertIn("想看", recs[0].badges)

    def test_seen_and_wishlist_matching_use_canonical_item_key(self):
        rated = [
            MediaItem(title="同名作品", year=1999, media_type="电影", tags=["看过"]),
            MediaItem(title="想看的同名作品", year=2024, media_type="电影", tags=["想看"]),
        ]
        candidates = [
            MediaItem(title="同名作品", year=1999, media_type="movie", douban_rating=9.0),
            MediaItem(title="同名作品", year=2024, media_type="电影", douban_rating=8.8),
            MediaItem(title="想看的同名作品", year=2024, media_type="film", douban_rating=8.7),
        ]
        profile = build_taste_profile(rated, like_terms="电影", dislike_terms="")

        recs = recommend(rated, candidates, profile, limit=5)
        by_title_year = {(rec.item.title, rec.item.year): rec for rec in recs}

        self.assertNotIn(("同名作品", 1999), by_title_year)
        self.assertIn(("同名作品", 2024), by_title_year)
        self.assertTrue(by_title_year[("想看的同名作品", 2024)].is_wishlist)


    def test_recommendation_rerank_reduces_country_and_media_type_monotony(self):
        candidates = [
            MediaItem(
                title=f"日本动画{i}",
                douban_id=f"jp{i}",
                media_type="动漫",
                douban_rating=9.2,
                countries=["日本"],
                genres=["动画", "剧情"],
            )
            for i in range(8)
        ] + [
            MediaItem(
                title="中国奇谭",
                douban_id="cn1",
                media_type="动漫",
                douban_rating=8.9,
                countries=["中国大陆"],
                genres=["动画", "剧情"],
            ),
            MediaItem(
                title="Arcane",
                douban_id="us1",
                media_type="动漫",
                douban_rating=9.0,
                countries=["美国"],
                genres=["动画", "剧情"],
            ),
        ]
        profile = build_taste_profile([], like_terms="评分高，剧情好", dislike_terms="")

        recs = recommend([], candidates, profile, limit=6, include_anime=True)
        countries = [rec.item.countries[0] for rec in recs if rec.item.countries]

        self.assertIn("中国大陆", countries)
        self.assertIn("美国", countries)

    def test_recommendation_ranking_prefers_complete_real_metadata_over_placeholder_premium(self):
        candidates = [
            MediaItem(
                title="占位高分片",
                douban_id="premium-电影-999",
                media_type="电影",
                douban_rating=9.2,
                directors=["镜头语言专家"],
                casts=["戏剧张力担当"],
                cover="data:image/svg+xml;charset=utf-8,%3Csvg%3E%3C/svg%3E",
                summary="高分但资料待绑定",
                source="premium_expansion",
            ),
            MediaItem(
                title="真实资料片",
                douban_id="real1",
                media_type="电影",
                douban_rating=8.9,
                directors=["导演甲"],
                casts=["演员乙"],
                cover="https://img.example/poster.jpg",
                summary="剧情完整，人物塑造扎实",
                raw={"people_photos": {"导演甲": "https://img.example/director.jpg", "演员乙": "https://img.example/cast.jpg"}},
            ),
        ]
        profile = build_taste_profile([], like_terms="评分高，剧情好", dislike_terms="")

        recs = recommend([], candidates, profile, limit=2)

        self.assertEqual(recs[0].item.title, "真实资料片")
        self.assertIn("资料完整", recs[0].reasons)
        self.assertTrue(any("资料待绑定" in warning for warning in recs[1].warnings))

    def test_recommendation_dict_exposes_public_people_photo_map(self):
        rated = []
        candidates = [
            MediaItem(
                title="人物图测试",
                douban_id="people1",
                media_type="电影",
                douban_rating=8.8,
                directors=["辛爽"],
                casts=["秦昊"],
                raw={"people_photos": {"辛爽": "https://img.example/director.jpg", "秦昊": "https://img.example/cast.jpg"}},
            )
        ]
        profile = build_taste_profile(rated, like_terms="高分", dislike_terms="")

        recs = recommend(rated, candidates, profile, limit=1)

        self.assertEqual(
            recs[0].to_dict()["people_photos"],
            {"辛爽": "https://img.example/director.jpg", "秦昊": "https://img.example/cast.jpg"},
        )


if __name__ == "__main__":
    unittest.main()
