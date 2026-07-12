import unittest

from douban_recommender.models import MediaItem
from douban_recommender.profiler import build_taste_profile


class WishlistTasteTests(unittest.TestCase):
    def test_unrated_wishlist_item_adds_bounded_positive_taste_signal(self):
        profile = build_taste_profile([
            MediaItem(
                title="想看的科幻剧",
                media_type="电视剧",
                genres=["科幻", "悬疑"],
                countries=["英国"],
                directors=["导演甲"],
                tags=["想看"],
            )
        ])

        self.assertEqual(profile.rated_count, 0)
        self.assertEqual(profile.liked_count, 0)
        self.assertGreater(profile.positive["genre:科幻"], 0)
        self.assertLess(profile.positive["genre:科幻"], 1)
        self.assertGreater(profile.positive["country:英国"], 0)


if __name__ == "__main__":
    unittest.main()
