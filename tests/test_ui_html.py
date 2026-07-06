import unittest

from douban_recommender.web_ui import INDEX_HTML


class UiHtmlTests(unittest.TestCase):
    def test_ui_uses_three_clear_steps(self):
        self.assertIn("绗竴姝ワ細杩炴帴璞嗙摚", INDEX_HTML)
        self.assertIn("绗簩姝ワ細纭鍙ｅ懗", INDEX_HTML)
        self.assertIn("绗笁姝ワ細鏌ョ湅鎺ㄨ崘", INDEX_HTML)

    def test_ui_contains_cookie_tutorial_and_privacy_copy(self):
        self.assertIn("Cookie 鏁欑▼", INDEX_HTML)
        self.assertIn("Cookie 鍙敤浜庢湰鏈鸿姹傝眴鐡ｉ〉闈", INDEX_HTML)
        self.assertIn("涓嶄細淇濆瓨鍒扮鐩", INDEX_HTML)

    def test_ui_contains_required_render_functions(self):
        for name in [
            "renderStepNav",
            "renderCrawlerPanel",
            "renderTastePanel",
            "renderRecommendations",
            "renderCookieGuide",
        ]:
            self.assertIn(f"function {name}", INDEX_HTML)

    def test_recommendation_cards_are_expandable(self):
        self.assertIn("<details", INDEX_HTML)
        self.assertIn("灞曞紑璇︽儏", INDEX_HTML)


if __name__ == "__main__":
    unittest.main()
