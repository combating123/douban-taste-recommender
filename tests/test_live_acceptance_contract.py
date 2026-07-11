import unittest

from douban_recommender.network_policy import (
    DEFAULT_SYNC_SAFETY_CAP,
    normalize_douban_user,
)


class LiveAcceptanceContractTests(unittest.TestCase):
    def test_profile_url_normalizes_known_user(self):
        value = "https://www.douban.com/people/272042071/?_dtcc=1&_i=fixture"

        self.assertEqual(normalize_douban_user(value), "272042071")

    def test_auto_pagination_safety_cap_is_not_user_visible_limit(self):
        self.assertGreaterEqual(DEFAULT_SYNC_SAFETY_CAP, 250)


if __name__ == "__main__":
    unittest.main()
