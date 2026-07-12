import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReadmeTests(unittest.TestCase):
    def test_readme_contains_readable_chinese_title(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("豆瓣", text)
        self.assertIn("CineScope Studio", text)
        self.assertNotIn("璞嗙摚", text)
        self.assertNotIn("鎶撳彇", text)

    def test_readme_explains_direct_douban_crawler(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("直接抓取豆瓣数据", text)
        self.assertIn("豆瓣用户 ID 或主页链接", text)
        self.assertIn("Cookie 是可选项", text)

    def test_readme_contains_cookie_tutorial_and_privacy_copy(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Cookie 获取教程", text)
        self.assertIn("同步页的 Cookie 输入框", text)
        self.assertIn("Cookie 只由可见输入获得", text)
        self.assertIn("当前标签页 sessionStorage", text)
        self.assertIn("Cookie 只用于本机请求豆瓣页面", text)
        self.assertIn("不会保存到磁盘", text)
        self.assertNotIn("Request Headers", text)

    def test_readme_matches_visible_cookie_same_tab_lifecycle(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertNotIn("同步请求发出后 Cookie 输入框会自动清空", text)
        self.assertIn("同步请求发出后，Cookie 会继续保留在当前同步面板的输入框", text)
        self.assertIn("离开或销毁同步面板时，可见输入框会清空", text)
        self.assertIn("返回同步页时会从同一标签页的 sessionStorage 恢复", text)
        self.assertIn("关闭标签页后该会话值失效", text)
        for boundary in (
            "Cookie 只由可见输入获得",
            "不会将 Cookie 写入数据库、磁盘、缓存、日志或报告",
            "不读取浏览器 Profile、请求头或任何隐藏存储",
        ):
            with self.subTest(boundary=boundary):
                self.assertIn(boundary, text)

    def test_readme_privacy_promise_covers_v3_and_legacy_visible_input_only(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")

        for promise in (
            "V3 与显式 legacy 回滚界面",
            "都只接受可见 Cookie 输入框中手动粘贴的 Cookie 字符串",
            "不调用剪贴板读取",
            "不解析整段请求头",
            "多行文本、带字段名前缀的内容或其他说明文字会被拒绝",
        ):
            with self.subTest(promise=promise):
                self.assertIn(promise, text)

    def test_readme_explains_profile_url_is_not_cookie(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("主页链接不是 Cookie", text)
        self.assertIn("https://www.douban.com/people/272042071/?_dtcc=1&_i=33953249Yxbr5m", text)
        self.assertIn("链接识别成功但仍需要 Cookie", text)

    def test_readme_matches_web_csv_paste_workflow(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("粘贴评分 CSV", text)
        self.assertIn("粘贴候选 CSV", text)
        self.assertIn("如果已经粘贴候选 CSV，就不会重复加入本地示例候选", text)

    def test_user_visible_text_has_no_known_mojibake_fragments(self):
        fragments = [
            "璇疯緭",
            "璞嗙摚",
            "鎶撳彇",
            "鐢ㄦ埛",
            "绗竴",
            "灞曞紑",
            "鏁欑▼",
            "鍙ｅ懗",
        ]
        paths = [ROOT / "README.md", ROOT / "src" / "douban_recommender" / "crawler.py", ROOT / "src" / "douban_recommender" / "web_ui.py"]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for fragment in fragments:
                with self.subTest(path=str(path), fragment=fragment):
                    self.assertNotIn(fragment, text)

    def test_readme_documents_cinescope_workflow(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("CineScope Studio", text)
        self.assertIn("242", text)
        self.assertIn("34", text)
        self.assertIn("电影、电视剧、动漫", text)
        self.assertIn("Cookie 获取教程", text)
        self.assertIn("python -m unittest discover -s tests -v", text)
        self.assertIn("不保存 Cookie", text)

    def test_readme_documents_image_proxy_and_local_clash_without_subscription_url(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("DOUBAN_RECOMMENDER_HTTP_PROXY", text)
        self.assertIn("Clash", text)
        self.assertIn("V2Ray", text)
        self.assertIn("不要粘贴订阅地址", text)
        self.assertNotIn("liangxin.xyz/api/v1", text)

    def test_readme_documents_no_key_tvmaze_and_free_api_fallbacks(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("TVMaze", text)
        self.assertIn("无需 Key", text)
        self.assertIn("TMDb API", text)
        self.assertIn("OMDb / IMDb", text)
        self.assertIn("AniList", text)
        self.assertIn("Jikan / MyAnimeList", text)

    def test_readme_documents_v3_foundation_media_and_privacy_boundaries(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("CINESCOPE_DATA_DIR", text)
        self.assertIn("/api/v2/media/health", text)
        self.assertIn("/api/v2/sync/jobs", text)
        self.assertIn("/media/<hash>", text)
        self.assertIn("Cookie 只保存在 sessionStorage", text)
        self.assertIn("自动抓取到末页", text)
        self.assertIn("250 页", text)

    def test_readme_documents_v3_default_launch_and_legacy_rollback(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")

        for token in (
            "V3 是默认界面",
            "不要求设置环境变量",
            "首次同步",
            "CINESCOPE_UI_VERSION=legacy",
            "DOUBAN_RECOMMENDER_HTTP_PROXY",
            "API Key 通过环境变量",
            "媒体健康",
            "清空缓存",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)

    def test_readme_documents_command_lens_channels_and_batch_terms(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("Command Lens", text)
        self.assertIn("自然语言", text)
        self.assertIn("可编辑条件", text)
        self.assertIn("本地确定性排序为事实源", text)
        self.assertIn("语言模型只做可选结构化/解释", text)
        self.assertIn("三个独立频道", text)
        self.assertIn("电影 / 电视剧 / 动画剧集", text)
        self.assertIn("动漫仅动画剧集、排除动画电影", text)
        self.assertIn("电视剧默认古装降权", text)
        self.assertIn("候选池", text)
        self.assertIn("条件命中", text)
        self.assertIn("当前批次", text)
        self.assertIn("`limit=160` 仅在未提供自定义候选时作为候选回填目标", text)
        self.assertIn("不是推荐会话上限、频道库存上限或当前批次数量", text)
        self.assertIn("自定义 candidates 可使 `pool_size` 超过或不同于 `limit`", text)
        self.assertIn("每频道独立换一批/上一批/耗尽恢复", text)

    def test_readme_documents_per_channel_batch_size_clamp_and_visual_shelf_default(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("\u6bcf\u4e2a\u9891\u9053\u7684 `batch_size` \u4f1a clamp \u5230 `1..24`", text)
        self.assertIn('"batch_size": 24', text)
        self.assertNotIn("`batch_size=30` \u624d\u63a7\u5236", text)
        self.assertIn("\u8f83\u77ed\u7684\u9ed8\u8ba4\u6279\u6b21\u66f4\u9002\u5408\u89c6\u89c9\u8d27\u67b6", text)

    def test_readme_documents_feedback_scope_and_append_only_undo(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("want / watched / permanent", text)
        self.assertIn("not-tonight / tonight-candidate", text)
        self.assertIn("session-only", text)
        self.assertIn("less / more / permanent-avoid", text)
        self.assertIn("可撤销", text)
        self.assertIn("append-only", text)
        self.assertIn("session-only 不写入稳定口味", text)

    def test_readme_documents_v2_api_local_model_and_cookie_boundaries(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("/api/v2/recommend/sessions", text)
        self.assertIn("/api/v2/feedback", text)
        self.assertIn("/api/v2/library", text)
        self.assertIn("schema_version: 2", text)
        self.assertIn("400", text)
        self.assertIn("404", text)
        self.assertIn("仅显式 endpoint 才联网", text)
        self.assertIn("127.0.0.1:11434", text)
        self.assertIn("/v1/chat/completions", text)
        self.assertIn("/v1/responses", text)
        self.assertIn("API key 不回显", text)
        self.assertIn("失败回退本地规则", text)
        self.assertIn("Cookie 只由用户输入", text)
        self.assertIn("仅 sessionStorage/请求内存", text)
        self.assertIn("不落盘不读取浏览器 Profile", text)
        self.assertIn("主页 URL 不是 Cookie", text)
        self.assertIn("本地 HTTP 代理端口允许", text)
        self.assertIn("不接收订阅地址", text)
        self.assertIn("/media/*", text)
        self.assertIn("外链不交付", text)
        self.assertIn("设计兜底", text)
        self.assertIn("演员/导演图片状态与修复任务", text)


if __name__ == "__main__":
    unittest.main()
