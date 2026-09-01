from __future__ import annotations

import unittest

from douban_recommender.localization import (
    is_reliable_chinese_title,
    localize_genre,
    localize_people_names,
    localize_summary,
    to_simplified_chinese,
)
from douban_recommender.curated_catalog import curated_display_title_for_provider, curated_summary_for_provider


class LocalizationTests(unittest.TestCase):
    def test_traditional_chinese_is_converted_without_damaging_latin_brand_names(self):
        self.assertEqual(
            "穿着Prada的恶魔2",
            to_simplified_chinese("穿著Prada的惡魔2"),
        )

    def test_context_sensitive_zhu_character_keeps_mainland_wording(self):
        self.assertEqual("穿着Prada的恶魔2，由著名导演执导。", to_simplified_chinese("穿著Prada的惡魔2，由著名導演執導。"))

    def test_anilist_genres_are_localized_instead_of_leaking_english_badges(self):
        self.assertEqual("心理", localize_genre("Psychological"))

    def test_verified_apple_provider_titles_use_mainland_names(self):
        self.assertEqual("星际穿越", curated_display_title_for_provider("apple_movies", "965491522"))
        self.assertEqual("蜘蛛侠：英雄无归", curated_display_title_for_provider("apple_movies", "1598961641"))
        self.assertEqual("轻度成人向", localize_genre("Ecchi"))

    def test_verified_people_names_are_localized_and_compound_credits_are_split(self):
        self.assertEqual(
            ["达伦·阿伦诺夫斯基", "亚伦·霍瓦斯", "迈克尔·杰勒尼克"],
            localize_people_names([
                "Darren Aronofsky",
                "Aaron Horvath & Michael Jelenic",
            ], verified_only=True),
        )
        self.assertEqual([], localize_people_names(["Unverified Latin Name"], verified_only=True))

    def test_provider_copy_uses_mainland_wording_and_curated_concise_summaries(self):
        self.assertEqual("揭秘日", curated_display_title_for_provider("apple_movies", "1896826363"))
        self.assertIn("外星生命", curated_summary_for_provider("apple_movies", "1896826363"))
        self.assertEqual(
            "主演阵容包括史蒂文·斯皮尔伯格，并进入霍格沃茨。",
            localize_summary("卡司包括史蒂芬·史匹柏，並進入霍格華茲。"),
        )

    def test_reliable_chinese_title_rejects_japanese_native_text(self):
        self.assertTrue(is_reliable_chinese_title("葬送的芙莉蓮"))
        self.assertFalse(is_reliable_chinese_title("葬送のフリーレン"))


if __name__ == "__main__":
    unittest.main()
