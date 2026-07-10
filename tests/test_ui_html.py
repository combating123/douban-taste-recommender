import unittest

from douban_recommender.web_ui import INDEX_HTML, _canonical_poster_by_title


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
            "function displayPosterUrl",
            "posterUrl(r) || canonical",
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

    def test_recommendation_stage_explains_target_vs_actual_count(self):
        for token in [
            "targetCount",
            "actualCount",
            "目标",
            "实际返回",
            "候选池",
            "limit:Number",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_recommendation_generation_status_explains_deferred_enrichment(self):
        for token in [
            "deferred_enrichment",
            "deferred_douban_fetch",
            "poster_rescue_pending",
            "推荐已生成",
            "补图会在后台修复台继续",
            "实时豆瓣探索已延后",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_recommendation_metrics_prevent_number_wrapping(self):
        for token in [
            "recommend-metrics",
            "metric-value",
            "font-variant-numeric:tabular-nums",
            "white-space:nowrap",
            "word-break:keep-all",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_hero_carousel_uses_rich_accessible_navigation(self):
        for token in [
            "hero-dot-strip",
            "hero-progress",
            "hero-thumb",
            "aria-pressed",
            "data-hero-index",
            "scrollIntoView",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_recommendation_page_uses_dense_cards_and_sticky_left_rail(self):
        for token in [
            "results-control-rail",
            "position:fixed",
            "dense-poster-grid",
            "compact-poster-card",
            "poster-quicklook",
            "grid-template-columns:repeat(auto-fill,minmax(min(100%,220px),1fr))",
            "min-height:0",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_recommendation_page_limits_vertical_scroll_with_cinema_wall(self):
        for token in [
            "results-shell",
            "recommendation-stage",
            "cinema-wall",
            "cinema-tile",
            "poster-body-overlay",
            "activeGridLimit",
            "showMoreRecommendations",
            "当前显示",
            "再展开",
            "展开当前分类全部",
            "gridLimitBySection",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_recommendation_left_rail_has_persistent_compass_not_empty_space(self):
        for token in [
            "renderResultCompass",
            "result-compass",
            "section-mini-map",
            "section-mini",
            "result-progress",
            "scrollToResults",
            "回到焦点",
            "片单遥控器",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_recommendation_initial_wall_is_not_too_tall_after_generation(self):
        for token in [
            "gridBaseLimit(name) { return name === '全部' ? 48 : 36; }",
            "aspect-ratio:3/4",
            "scrollToResults('workspace')",
            "setTimeout(() => scrollToResults('heroShowcase'), 0)",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_secondary_rails_are_collapsed_to_keep_page_short(self):
        for token in [
            "rail-collapse",
            "compact-rail-wall",
            "展开横向频道",
            "分类速览",
            "railDeck",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_left_results_rail_sticks_while_inner_content_scrolls(self):
        for token in [
            "results-control-inner",
            "overflow:visible",
            "height:calc(100vh - 40px)",
            ".results-control-inner {",
            "overflow:auto",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_left_results_rail_is_viewport_fixed_on_desktop(self):
        for token in [
            "position:fixed",
            "left:max(20px,calc((100vw - min(1880px,calc(100vw - 20px))) / 2 + 20px))",
            "width:min(330px,calc(100vw - 40px))",
            ".workspace.recommendation-stage #mainPanel",
            "grid-column:2",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_results_rail_can_be_hidden_so_main_wall_becomes_primary(self):
        for token in [
            "results-rail-hidden",
            "rail-hidden-shell",
            "rail-toggle-fab",
            "toggleResultsRail",
            "hideResultsRail",
            "showResultsRail",
            "显示片单遥控器",
            "隐藏侧栏",
            "aria-expanded",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_hidden_rail_toggle_fab_stays_out_of_main_header_flow(self):
        fab_slice = INDEX_HTML[INDEX_HTML.index(".rail-toggle-fab {"):INDEX_HTML.index(".rail-toggle-fab.visible")]
        for token in ["right:22px", "bottom:22px", "left:auto", "top:auto"]:
            self.assertIn(token, fab_slice)

    def test_hidden_rail_toggle_fab_is_compact_icon_only(self):
        for token in [
            "width:52px",
            "height:52px",
            "font-size:0",
            ".rail-toggle-fab:before",
            'content:"☰"',
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_frontend_ignores_stale_mismatched_premium_doubanio_covers(self):
        for token in [
            "isSyntheticPremiumId",
            "hasPotentiallyMismatchedPoster",
            "id.startsWith('premium-')",
            "return ''; // stale premium poster can belong to another title",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_recommendation_results_restore_after_browser_refresh_without_cookie_storage(self):
        for token in [
            "CINESCOPE_LAST_RECOMMENDATION_V1",
            "persistRecommendationSnapshot",
            "restoreRecommendationSnapshot",
            "tryRestoreRecommendationSnapshot",
            "savedAt",
            "recommendations",
            "sections",
            "profile",
            "lastCounts",
            "activeSection",
            "gridLimitBySection",
            "heroBySection",
            "railHidden",
            "if (!tryRestoreRecommendationSnapshot()) renderCrawlerPanel();",
        ]:
            self.assertIn(token, INDEX_HTML)

        snapshot_slice = INDEX_HTML[
            INDEX_HTML.index("function persistRecommendationSnapshot"):
            INDEX_HTML.index("function restoreRecommendationSnapshot")
        ]
        self.assertNotIn("doubanCookie", snapshot_slice)
        self.assertNotIn("COOKIE_SESSION_KEY", snapshot_slice)

    def test_designed_covers_are_labeled_as_intentional_not_broken_images(self):
        for token in [
            "isDesignedPoster",
            "designedPosterCount",
            "posterSourceBadge",
            "designed-cover",
            "设计封面",
            "暂无精确海报",
            "不是图片加载失败",
            "真实海报",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_ui_exposes_force_poster_rescue_for_stale_snapshots(self):
        for token in [
            "POSTER_RESCUE_VERSION",
            "rescuePosterImages",
            "/api/enrich-posters",
            "/api/poster-jobs",
            "强制修复海报",
            "正在修复海报",
            "海报修复完成",
            "mergePosterRescueItems",
            "maybeAutoRescuePosters",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_ui_has_configurable_free_poster_sources_and_live_repair_feed(self):
        for token in [
            "CINESCOPE_POSTER_SOURCE_PREFS_V1",
            "posterSourcePayload",
            "TMDb API Key",
            "OMDb API Key",
            "AniList",
            "Jikan",
            "TVMaze",
            "enableTvmazePoster",
            "MyAnimeList",
            "https://www.themoviedb.org/settings/api",
            "https://www.omdbapi.com/apikey.aspx",
            "海报修复现场",
            "posterJobDock",
            "pollPosterJob",
            "豆瓣 CDN · 待换源",
            "IMDb",
            "缺图补救台",
            "copyMissingPosterTitles",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_poster_error_handler_does_not_auto_loop_after_current_rescue_version(self):
        handler_slice = INDEX_HTML[INDEX_HTML.index("function handlePosterImageError"):INDEX_HTML.index("function safePosterImg")]

        self.assertIn("state.posterRescueVersion < POSTER_RESCUE_VERSION", handler_slice)
        self.assertIn("!state.posterRescueInFlight", handler_slice)
        self.assertIn("rescuePosterImages(false)", handler_slice)

    def test_restored_snapshots_drop_unrated_douban_noise_before_rendering(self):
        for token in [
            "cleanupLowConfidenceRecommendations",
            "isLowConfidencePublicCandidate",
            "douban_explore:",
            "douban_plan:",
            "filteredLowConfidence",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_rescue_metrics_do_not_count_rows_with_canonical_display_poster(self):
        for token in [
            "function hasCanonicalPoster",
            "&& !hasCanonicalPoster(r)",
            "isDoubanCdnPosterRaw(raw) && hasCanonicalPoster(r)",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_frontend_canonical_backfill_includes_static_public_poster_sources(self):
        posters = _canonical_poster_by_title()

        social_network = "社交网络"
        big_white_duel = "白色强人"
        universe = "比宇宙更远的地方"
        self.assertIn(social_network, posters)
        self.assertIn("themoviedb", posters[social_network])
        self.assertIn(big_white_duel, posters)
        self.assertIn("themoviedb", posters[big_white_duel])
        self.assertIn(universe, posters)
        self.assertIn("anilist", posters[universe])

    def test_poster_repair_feed_is_a_live_source_theater_not_passive_progress(self):
        for token in [
            "poster-source-theater",
            "source-lane",
            "实时命中",
            "当前搜索",
            "不是干等",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_frontend_static_backfill_covers_current_stale_snapshot_missing_titles(self):
        posters = _canonical_poster_by_title()
        for title in [
            "去他妈的世界",
            "人生切割术",
            "3月的狮子",
            "少女歌剧 Revue Starlight",
            "末日三问",
            "赛马娘 Road to the Top",
            "Fate/stay night UBW",
            "PSYCHO-PASS 心理测量者",
        ]:
            with self.subTest(title=title):
                self.assertIn(title, posters)
                self.assertTrue(posters[title].startswith("https://"))

    def test_detail_drawer_has_cinematic_interactions_and_motion(self):
        for token in [
            "detail-cinematic",
            "detail-backdrop",
            "poster-parallax",
            "detail-orbit",
            "story-timeline",
            "reason-stack",
            "magnetic-person",
            "openPersonSpotlight",
            "detail-tab",
            "同导演",
            "同主演",
            "@keyframes detailFloat",
            "@keyframes shimmerSweep",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_people_photo_lookup_falls_back_by_person_name(self):
        for token in [
            "canonicalPeoplePhotoByName",
            "canonicalPeoplePhotoForName",
            "canonicalPeoplePhotoByName[name]",
            "canonicalPeoplePhotoByName[`${role}:${name}`]",
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

    def test_sync_success_is_rendered_as_completion_not_cookie_recovery(self):
        for token in [
            "renderSyncSuccess",
            "sync-success-brief",
            "同步完成",
            "空白分页是豆瓣列表的正常结束信号",
            "recovery.status === 'ok' || recovery.status === 'complete'",
            "继续确认口味",
        ]:
            self.assertIn(token, INDEX_HTML)

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

    def test_cookie_import_assistant_extracts_request_headers_and_clipboard_cookie(self):
        for token in [
            "normalizeCookieInput",
            "importCookieFromClipboard",
            "setCookieBoxValue",
            "Cookie 快速导入",
            "一键读取剪贴板 Cookie",
            "粘贴完整 Request Headers 会自动提取 Cookie",
            "自动启用本次会话记忆",
        ]:
            self.assertIn(token, INDEX_HTML)


    def test_people_portraits_have_status_badges_and_no_broken_image_experience(self):
        for token in [
            "personPortraitStatus",
            "人物图源",
            "真实资料图",
            "设计肖像",
            "portrait-fallback",
            'onerror="this.onerror=null;this.src=',
            "people-spotlight-rail",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_hero_carousel_is_full_width_cinematic_banner_not_left_strip(self):
        for token in [
            "cinematic-banner",
            "banner-backdrop",
            "banner-poster-float",
            "banner-filmstrip",
            "banner-controls",
            "\u4e0a\u4e00\u90e8",
            "\u4e0b\u4e00\u90e8",
        ]:
            self.assertIn(token, INDEX_HTML)
        self.assertNotIn("grid-template-columns:minmax(180px,280px) 1fr", INDEX_HTML)

    def test_hero_carousel_has_bounded_landscape_height(self):
        self.assertIn("height:clamp(460px,50vw,620px)", INDEX_HTML)
        self.assertIn("grid-template-rows:1fr auto auto", INDEX_HTML)

    def test_hero_carousel_copy_has_no_question_mark_mojibake(self):
        hero_slice = INDEX_HTML[INDEX_HTML.index("function renderHeroCarousel"):INDEX_HTML.index("function renderHeroShowcase")]
        self.assertNotIn("???", hero_slice)
        self.assertIn("\u4eca\u65e5\u6700\u503c\u5f97\u770b", hero_slice)
        self.assertIn("\u4e0a\u4e00\u90e8", hero_slice)
        self.assertIn("\u4e0b\u4e00\u90e8", hero_slice)

    def test_results_toolbar_copy_has_no_question_mark_mojibake(self):
        toolbar_slice = INDEX_HTML[INDEX_HTML.index("function resultsMainToolbar"):INDEX_HTML.index("function renderRecommendations")]
        self.assertNotIn("???", toolbar_slice)
        self.assertIn("主舞台", toolbar_slice)
        self.assertIn("显示片单遥控器", toolbar_slice)
        self.assertIn("强制修复海报", toolbar_slice)

    def test_hero_filmstrip_hides_native_scrollbar_and_keeps_copy_compact(self):
        self.assertIn(".banner-filmstrip::-webkit-scrollbar { display:none; }", INDEX_HTML)
        self.assertIn("scrollbar-width:none", INDEX_HTML)
        self.assertIn(".banner-copy p { margin:0; }", INDEX_HTML)

    def test_ui_exposes_global_anime_channels(self):
        for token in ["动漫 · 国创动画", "动漫 · 欧美动画", "动漫 · 日漫精品", "全球动画剧集"]:
            self.assertIn(token, INDEX_HTML)

    def test_results_surface_uses_figma_grade_focus_mode_visual_system(self):
        for token in [
            "figma-grade-stage",
            "ambient-orb",
            "stage-command-bar",
            "signal-stack",
            "spotlight-lens",
            "poster-lift",
            "grid-template-columns:repeat(auto-fill,minmax(min(100%,210px),1fr))",
            "railHidden:true",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_detail_drawer_auto_enriches_people_photos_on_open(self):
        for token in [
            "needsPeoplePhotoEnrichment",
            "enrichPeopleForDetail",
            "/api/enrich-people",
            "people-photo-enriching",
            "人物图库补全",
            "mergePeopleEnrichment",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_people_enrichment_payload_filters_to_visible_cast_and_director_names(self):
        for token in [
            "function visiblePeoplePhotoPayload",
            "people_photos:visiblePeoplePhotoPayload(r)",
            "new Set(peopleForItem(r).map(person => person.name))",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_people_photo_enrichment_reuses_session_cookie_for_douban_detail(self):
        for token in [
            "peopleCookieForRequest",
            "normalizeCookieInput(sessionStorage.getItem(COOKIE_SESSION_KEY)",
            "cookie:peopleCookieForRequest()",
            "人物详情补图会复用本次会话 Cookie",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_detail_drawer_opens_with_safe_main_stage_area(self):
        for token in [
            "function closeDetailDrawer",
            "document.body.classList.add('detail-open')",
            "document.body.classList.remove('detail-open')",
            ".detail-open .banner-poster-float",
            ".detail-open .workspace.recommendation-stage #mainPanel",
            "drawer-safe-stage",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_hero_carousel_poster_uses_contain_fit_to_avoid_cropping(self):
        for token in [
            ".banner-poster-float img { width:100%; height:100%; object-fit:contain;",
            "background:linear-gradient(145deg,rgba(255,255,255,.10),rgba(255,255,255,.02));",
            ".banner-poster-float { justify-self:end;",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_people_enrichment_distinguishes_curated_placeholder_identity(self):
        for token in [
            "function isCuratedPlaceholderPerson",
            "function needsPeopleIdentityEnrichment",
            "镜头语言专家",
            "戏剧张力担当",
            "人物身份待绑定",
            "策展占位肖像",
            "绑定真实演职员",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_html_does_not_contain_legacy_test_marker_comment(self):
        for text in [
            "Legacy",
            "mis-encoded brief",
            "existing tests authored",
        ]:
            self.assertNotIn(text, INDEX_HTML)

    def test_recommendation_sections_have_shuffle_batch_controls(self):
        for token in [
            "batchOffsetBySection",
            "function shuffleSectionBatch",
            "\u6362\u4e00\u6279",
            "visibleBatchItems",
            "batch-shuffle",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_detail_people_enrichment_has_skeleton_and_smooth_actions(self):
        for token in [
            "people-skeleton-strip",
            "detail-action-row",
            "function detailScrollTo",
            "requestAnimationFrame",
            "\u8865\u56fe\u4e2d",
        ]:
            self.assertIn(token, INDEX_HTML)


    def test_restored_snapshots_drop_numbered_curated_placeholder_titles(self):
        for token in [
            "isNumberedCuratedPlaceholder",
            "cleanupStalePlaceholderRecommendations",
            "????",
            "??????",
            "???",
            "????",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_restored_snapshots_normalize_stale_premium_display_titles(self):
        for token in [
            "stalePremiumDisplayTitleMap",
            "normalizeRecommendationTitle",
            "normalizeRecommendationDisplayData",
            "titleRepairs",
            "\u4fe1\u53f7 (\u4fe1\u606f\u8bba)",
            "\u7f85\u751f\u9580 (\u96fb\u5f71)",
            "\u9802\u5c16\u5c0d\u6c7a",
            "\u71c3\u71d2\u70c8\u611b",
            "\u300c\u6cd5\u300d\u59bb",
            "\u673a\u667a\u533b\u751f\u751f\u6d3b",
            "已修正",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_detail_drawer_has_premium_scrim_and_spring_motion(self):
        for token in [
            "detailScrim",
            "detail-scrim",
            "spring-drawer",
            "translateX(105%) scale(.98)",
            "drawer.open { transform:translateX(0) scale(1);",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_restored_snapshots_backfill_canonical_title_metadata(self):
        for token in [
            "canonicalTitleMetadataMap",
            "applyCanonicalTitleMetadata",
            "metadataRepairs",
            "\u81f4\u547d\u9b54\u672f",
            "\u4f11\u00b7\u6770\u514b\u66fc",
            "\u71c3\u70e7",
            "\u674e\u6ca7\u4e1c",
        ]:
            self.assertIn(token, INDEX_HTML)


    def test_restored_snapshots_normalize_global_anime_and_traditional_titles(self):
        for token in [
            "Arcane",
            "\u82f1\u96c4\u8054\u76df\uff1a\u53cc\u57ce\u4e4b\u6218",
            "Invincible",
            "\u65e0\u654c\u5c11\u4fa0",
            "Love, Death & Robots",
            "\u7231\uff0c\u6b7b\u4ea1\u548c\u673a\u5668\u4eba",
            "Avatar: The Last Airbender",
            "\u964d\u4e16\u795e\u901a\uff1a\u6700\u540e\u7684\u6c14\u5b97",
            "\u9ed1\u6697\u9a91\u58eb",
            "\u4e1c\u4eac\u7269\u8bed",
            "\u7231\u4e50\u4e4b\u57ce",
            "\u5929\u5802\u7535\u5f71\u9662",
            "\u640f\u51fb\u4ff1\u4e50\u90e8",
            "\u6cd5\u5170\u897f\u7279\u6d3e",
            "\u7eff\u76ae\u4e66",
            "\u661f\u9645\u725b\u4ed4",
            "\u5947\u8bfa\u4e4b\u65c5",
            "\u866b\u5e08",
            "\u95f4\u8c0d\u8fc7\u5bb6\u5bb6",
            "\u7535\u8111\u7ebf\u5708",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_restored_snapshots_repair_designed_covers_even_without_metadata(self):
        for token in [
            "const canonicalOnly = canonicalPosterRawFor(r);",
            "if (canonicalOnly && isDesignedPoster(r))",
            "assignBoth('cover', canonicalOnly);",
        ]:
            self.assertIn(token, INDEX_HTML)

    def test_display_poster_prefers_canonical_for_known_stale_external_sources(self):
        for token in [
            "knownBrokenPosterUrls",
            "function isLikelyStaleExternalPoster",
            "canonicalRaw && isLikelyStaleExternalPoster(raw, canonicalRaw)",
            "lYpHeSm7BcUxAbBx1ucuEH7oGAe.jpg",
        ]:
            self.assertIn(token, INDEX_HTML)


    def test_recommendation_snapshot_uses_versioned_key_and_clears_legacy_keys(self):
        self.assertIn("CINESCOPE_LAST_RECOMMENDATION_V4", INDEX_HTML)
        self.assertIn("OLD_RECOMMENDATION_KEYS", INDEX_HTML)
        self.assertIn("cleanupOldRecommendationSnapshots", INDEX_HTML)
        self.assertIn("localStorage.removeItem(key)", INDEX_HTML)
        self.assertIn("CINESCOPE_LAST_RECOMMENDATION_V1", INDEX_HTML)
        self.assertIn("CINESCOPE_LAST_RECOMMENDATION_V2", INDEX_HTML)
        self.assertIn("CINESCOPE_LAST_RECOMMENDATION_V3", INDEX_HTML)

    def test_frontend_static_backfill_covers_latest_missing_titles(self):
        posters = _canonical_poster_by_title()
        for title in [
            "\u602a\u5316\u732b",
            "\u4f0d\u516d\u4e03",
            "\u7231\uff0c\u6b7b\u4ea1\u548c\u673a\u5668\u4eba",
            "\u96fe\u5c71\u4e94\u884c",
            "\u4e2d\u56fd\u5947\u8c2d",
            "\u547d\u8fd0\u77f3\u4e4b\u95e8",
            "\u5c11\u5973\u7ec8\u672b\u65c5\u884c",
            "\u6211\u4eec\u7684\u7236\u8f88",
            "\u5179\u5c71\u9c7c\u8c31",
            "\u9a7e\u9a76\u6211\u7684\u8f66",
            "\u8bb0\u5fc6\u788e\u7247",
            "\u6d77\u76d7\u6218\u8bb0",
            "\u5947\u8bfa\u4e4b\u65c5",
            "\u7535\u8111\u7ebf\u5708",
            "\u79d1\u62c9\u4f20\u5947",
        ]:
            with self.subTest(title=title):
                self.assertIn(title, posters)
                self.assertTrue(posters[title].startswith("https://"))



if __name__ == "__main__":
    unittest.main()
