import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReadmeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
