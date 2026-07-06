import unittest

from douban_recommender.web_ui import INDEX_HTML


class UiHtmlTests(unittest.TestCase):
    def test_ui_uses_three_clear_steps(self):
        self.assertIn("第一步：连接豆瓣", INDEX_HTML)
        self.assertIn("第二步：确认口味", INDEX_HTML)
        self.assertIn("第三步：查看推荐", INDEX_HTML)

    def test_ui_contains_cookie_tutorial_and_privacy_copy(self):
        self.assertIn("Cookie 教程", INDEX_HTML)
        self.assertIn("Cookie 只用于本机请求豆瓣页面", INDEX_HTML)
        self.assertIn("不会保存到磁盘", INDEX_HTML)

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
        self.assertIn("展开详情", INDEX_HTML)

    def test_html_does_not_contain_legacy_test_marker_comment(self):
        for text in [
            "Legacy",
            "mis-encoded brief",
            "existing tests authored",
        ]:
            self.assertNotIn(text, INDEX_HTML)


if __name__ == "__main__":
    unittest.main()
