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

    def test_premium_media_ui_has_hero_rails_and_poster_fallbacks(self):
        for token in [
            "heroShowcase",
            "railWall",
            "media-rail",
            "posterFallback",
            "safePosterImg",
            "buildMediaRails",
            "renderMediaRail",
            "sectionItems",
            "onerror",
            "/api/image-proxy",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_poster_fallback_is_safe_inside_inline_onerror_handler(self):
        self.assertIn("safeFallback", INDEX_HTML)
        self.assertIn("replace(/'/g, '%27')", INDEX_HTML)
        self.assertNotIn("Arial,'Microsoft YaHei'", INDEX_HTML)

    def test_world_class_ui_contains_category_spotlights_and_image_resilience_guide(self):
        for token in [
            "homepage-studio",
            "tasteDNA",
            "categorySpotlight",
            "renderHeroCarousel",
            "hero-track",
            "hero-dots",
            "heroBySection",
            "spotlightPool",
            "imageResilienceGuide",
            "DOUBAN_RECOMMENDER_HTTP_PROXY",
            "Clash",
            "V2Ray",
            "不要粘贴订阅地址",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_image_resilience_guide_wraps_long_proxy_text(self):
        for token in [
            ".image-resilience",
            "max-width:100%",
            "overflow-wrap:anywhere",
            "word-break:break-word",
            "white-space:pre-wrap",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_image_resilience_guide_uses_inner_scroll_code_block(self):
        for token in [
            ".resilience-card code",
            "overflow-x:auto",
            "white-space:pre",
            "word-break:normal",
            "proxy-command",
            "复制代理命令",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_frontend_backfills_posters_when_api_result_has_empty_cover(self):
        for token in [
            "canonicalPosterMap",
            "canonicalPosterByTitle",
            "function canonicalPosterFor",
            "posterUrl(r) || canonicalPosterFor(r)",
            "控方证人",
            "1296141",
            "p2927451337",
            "图片诊断",
            "旧服务",
            "当前结果缺 cover",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_frontend_backfills_people_photos_when_api_result_has_empty_people_photos(self):
        for token in [
            "canonicalPeoplePhotoMap",
            "function canonicalPeoplePhotosFor",
            "Billy_Wilder.jpg",
            "比利·怀尔德",
            "...canonicalPeoplePhotosFor(r)",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_ui_exposes_local_image_diagnostics_hook_without_cookie_storage(self):
        for token in [
            "window.__CINESCOPE_DIAGNOSTICS__",
            "canonicalPosterFor",
            "peoplePhotoMap",
            "openDetailObject",
        ]:
            self.assertIn(token, INDEX_HTML)
        diagnostics_slice = INDEX_HTML[INDEX_HTML.index("window.__CINESCOPE_DIAGNOSTICS__"):]
        self.assertNotIn("doubanCookie", diagnostics_slice)
        self.assertNotIn("COOKIE_SESSION_KEY", diagnostics_slice)

    def test_premium_media_ui_exposes_rich_metadata_and_people(self):
        for token in [
            "metadataLine",
            "peopleChips",
            "peopleCarousel",
            "person-card",
            "filterByPerson",
            "person-chip",
            "导演",
            "主演",
            "剧情简介",
            "电影",
            "电视剧",
            "动漫",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_people_ui_uses_real_portrait_or_designed_svg_fallback(self):
        for token in [
            "personPortrait",
            "personPhotoSvg",
            "person-photo",
            "portrait-fallback",
            "person.photo",
            "人物肖像",
        ]:
            self.assertIn(token, INDEX_HTML)

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

    def test_sync_screen_has_premium_recovery_workflow_for_douban_403(self):
        for token in [
            "syncCommandCenter",
            "renderSyncRecovery",
            "sync-health",
            "blocked-brief",
            "diagnosis-grid",
            "Cookie 解锁",
            "继续用高质量片库生成推荐",
            "豆瓣要求登录态",
            "recovery",
            "continueWithoutSync",
            "同步作战室",
            "恢复路线",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_ui_has_no_question_mark_mojibake_in_sync_copy(self):
        sync_slice = INDEX_HTML[INDEX_HTML.index("function renderCrawlerPanel"):INDEX_HTML.index("function tasteDNA")]
        self.assertNotIn("????", sync_slice)
        self.assertIn("第一步：连接豆瓣", sync_slice)
        self.assertIn("同步诊断", sync_slice)

    def test_sync_recovery_waits_for_real_recovery_status(self):
        self.assertIn("!recovery.status", INDEX_HTML)

    def test_sync_status_changes_after_cookie_block(self):
        self.assertIn("豆瓣要求登录态：可粘贴 Cookie 重试", INDEX_HTML)

    def test_sync_ui_explains_profile_url_is_not_cookie(self):
        for token in [
            "extractDoubanUserId",
            "state.lastUserInput",
            "state.lastUserId",
            "state.lastCookieProvided",
            "已识别豆瓣用户",
            "主页链接不是 Cookie",
            "链接识别成功",
            "user-input-card",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_global_text_overflow_is_hardened(self):
        for token in [
            ".anti-overflow",
            "min-width:0",
            "overflow-wrap:anywhere",
            "word-break:break-word",
            ".sync-command-center *",
            ".timeline-row",
            ".glass-panel",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_sync_ui_has_live_profile_url_intelligence_and_cookie_block_copy(self):
        for token in [
            "inputInsight",
            "previewDoubanInput",
            "oninput=\"persistCrawlerControls(); previewDoubanInput()\"",
            "不是同步失败",
            "复制的是主页链接，不是授权凭证",
            "response.recovery?.status === 'needs_cookie'",
            "renderNetworkFailureRecovery",
            "input_analysis",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_overflow_hardens_global_layout_hotspots(self):
        for token in [
            "html, body",
            "overflow-x:hidden",
            "p, li, summary, label, h1, h2, h3, h4, a, span",
            ".row > *, .metric-grid > *, .sync-health > *, .recovery-actions > *, .sync-playbook > *, .hero-showcase > *, .hero-track > *, .rail-head > *, .poster-card, .poster-body, .drawer, .drawer *",
            "grid-template-columns:repeat(auto-fit,minmax(min(100%,",
            ".quick-actions button",
            ".poster-body h3",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_crawler_controls_remember_profile_counts_and_session_cookie(self):
        for token in [
            "CINESCOPE_PREFS_V2",
            "CINESCOPE_SESSION_COOKIE",
            "loadUserPrefs",
            "saveUserPrefs",
            "hydrateCrawlerControls",
            "sessionStorage",
            "localStorage",
            "rememberCookieSession",
            "clearSessionCookie",
            "defaultDoubanUser",
            "272042071",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_crawler_controls_bind_prefs_to_visible_inputs(self):
        for token in [
            'id="doubanUser"',
            'oninput="persistCrawlerControls(); previewDoubanInput()"',
            'id="doubanCookie"',
            'oninput="persistCrawlerControls()"',
            'id="expectedCollect"',
            'id="expectedWish"',
            'id="maxPages"',
            'onchange="persistCrawlerControls()"',
            'id="rememberCookieSession"',
            "本次浏览器会话自动填 Cookie",
            "清除会话 Cookie",
            "hydrateCrawlerControls();",
            "const prefs = persistCrawlerControls();",
            "prefs.rememberCookieSession",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_cookie_hint_distinguishes_session_autofill_from_clear_after_sync(self):
        for token in [
            "本次浏览器会话已自动填入 Cookie",
            "Cookie 只保存在 sessionStorage",
            "未勾选会话记忆时同步后输入框会清空",
            "rememberCookieSession",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_html_does_not_contain_legacy_test_marker_comment(self):
        for text in [
            "Legacy",
            "mis-encoded brief",
            "existing tests authored",
        ]:
            self.assertNotIn(text, INDEX_HTML)


if __name__ == "__main__":
    unittest.main()
