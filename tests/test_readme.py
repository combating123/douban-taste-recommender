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
        self.assertIn("F12", text)
        self.assertIn("Network / 网络", text)
        self.assertIn("Cookie 只用于本机请求豆瓣页面", text)
        self.assertIn("不会保存到磁盘", text)

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


if __name__ == "__main__":
    unittest.main()
