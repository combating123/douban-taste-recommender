import unittest

from douban_recommender.web_ui import INDEX_HTML


class UiHtmlTests(unittest.TestCase):
    def test_ui_contains_cinescope_dashboard_landmarks(self):
        html = INDEX_HTML

        self.assertIn("CineScope Studio", html)
        self.assertIn("cinematic-hero", html)
        self.assertIn("syncTimeline", html)
        self.assertIn("poster-grid", html)
        self.assertIn("detailDrawer", html)
        self.assertIn("评分高，剧情好，叙事强", html)
        self.assertIn("电视剧古装", html)
        self.assertIn("includeAnime", html)
        self.assertIn("/api/sync-douban", html)
        self.assertIn("/api/cache", html)

    def test_ui_has_no_legacy_plain_title_only_experience(self):
        html = INDEX_HTML

        self.assertNotIn("豆瓣口味影视推荐器</h1>", html)
        self.assertIn("私人影视策展器", html)

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

    def test_checkbox_controls_are_not_full_width(self):
        self.assertIn('input[type="checkbox"]', INDEX_HTML)
        self.assertIn("accent-color:var(--gold)", INDEX_HTML)

    def test_filtered_section_detail_uses_visible_recommendations(self):
        self.assertIn("visibleRecommendations", INDEX_HTML)
        self.assertIn("state.visibleRecommendations = items", INDEX_HTML)
        self.assertIn("const r = state.visibleRecommendations[index]", INDEX_HTML)

    def test_ui_restores_csv_paste_workflow(self):
        self.assertIn("评分 CSV", INDEX_HTML)
        self.assertIn("候选 CSV", INDEX_HTML)
        self.assertIn('id="ratingsCsv"', INDEX_HTML)
        self.assertIn('id="candidatesCsv"', INDEX_HTML)
        self.assertIn("ratings_csv:", INDEX_HTML)
        self.assertIn("candidates_csv:", INDEX_HTML)

    def test_ui_displays_crawl_breakdown_and_error_summary(self):
        for text in ["看过数量", "想看数量", "成功页", "失败页", "停止原因", "错误摘要"]:
            self.assertIn(text, INDEX_HTML)
        self.assertIn("collect_count", INDEX_HTML)
        self.assertIn("wish_count", INDEX_HTML)
        self.assertIn("stopped_reason", INDEX_HTML)
        self.assertIn("errors", INDEX_HTML)

    def test_html_does_not_contain_legacy_test_marker_comment(self):
        for text in [
            "Legacy",
            "mis-encoded brief",
            "existing tests authored",
        ]:
            self.assertNotIn(text, INDEX_HTML)


if __name__ == "__main__":
    unittest.main()
