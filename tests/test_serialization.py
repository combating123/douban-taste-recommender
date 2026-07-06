import unittest

from douban_recommender.models import MediaItem
from douban_recommender.serialization import media_item_from_dict, media_item_to_dict, redact_cookie


class SerializationTests(unittest.TestCase):
    def test_media_item_round_trips_through_json_dict(self):
        item = MediaItem(
            title="隐秘的角落",
            my_rating=5,
            douban_rating=8.8,
            year=2020,
            media_type="电视剧",
            genres=["剧情", "悬疑", "犯罪"],
            countries=["中国大陆"],
            directors=["辛爽"],
            casts=["秦昊", "王景春"],
            tags=["看过", "现实主义"],
            url="https://movie.douban.com/subject/33404425/",
            douban_id="33404425",
            cover="https://img.example/poster.jpg",
            summary="孩子、家庭与犯罪的阴影",
            source="douban_user:collect",
        )

        payload = media_item_to_dict(item)
        restored = media_item_from_dict(payload)

        self.assertEqual(restored.title, "隐秘的角落")
        self.assertEqual(restored.my_rating, 5)
        self.assertEqual(restored.douban_rating, 8.8)
        self.assertEqual(restored.genres, ["剧情", "悬疑", "犯罪"])
        self.assertEqual(restored.tags, ["看过", "现实主义"])
        self.assertEqual(restored.douban_id, "33404425")

    def test_redact_cookie_removes_sensitive_values(self):
        raw = "bid=abc123; dbcl2=\"999:user\"; ck=secret; push_noty_num=0"

        redacted = redact_cookie(raw)

        self.assertNotIn("abc123", redacted)
        self.assertNotIn("secret", redacted)
        self.assertIn("bid=<redacted>", redacted)
        self.assertIn("ck=<redacted>", redacted)


if __name__ == "__main__":
    unittest.main()
