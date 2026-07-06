import unittest

from douban_recommender.crawler import (
    build_user_collection_url,
    normalize_douban_user_id,
    parse_user_collection_html,
)


COLLECT_HTML = """
<html><body>
  <div class="item">
    <div class="pic">
      <a href="https://movie.douban.com/subject/33404425/">
        <img alt="隐秘的角落" src="https://img.example/cover.jpg">
      </a>
    </div>
    <div class="info">
      <ul>
        <li class="title">
          <a href="https://movie.douban.com/subject/33404425/"><em>隐秘的角落</em></a>
        </li>
        <li class="intro">2020 / 中国大陆 / 剧情 悬疑 犯罪 / 辛爽 / 秦昊 王景春</li>
        <li>
          <span class="rating5-t"></span>
          <span class="date">2024-01-01</span>
        </li>
        <li><span class="comment">孩子、家庭与犯罪的阴影</span></li>
      </ul>
    </div>
  </div>
  <div class="item">
    <div class="pic">
      <a href="https://movie.douban.com/subject/30468961/">
        <img alt="想见你" src="https://img.example/want.jpg">
      </a>
    </div>
    <div class="info">
      <ul>
        <li class="title">
          <a href="https://movie.douban.com/subject/30468961/"><em>想见你</em></a>
        </li>
        <li class="intro">2019 / 中国台湾 / 爱情 悬疑 奇幻 / 黄天仁 / 柯佳嬿 许光汉</li>
        <li><span class="date">2024-02-02</span></li>
      </ul>
    </div>
  </div>
</body></html>
"""


class CrawlerParserTests(unittest.TestCase):
    def test_normalize_douban_user_id_accepts_plain_id(self):
        self.assertEqual(normalize_douban_user_id("moviefan123"), "moviefan123")

    def test_normalize_douban_user_id_extracts_people_url(self):
        url = "https://www.douban.com/people/moviefan123/collect"
        self.assertEqual(normalize_douban_user_id(url), "moviefan123")

    def test_build_user_collection_url_for_collect(self):
        url = build_user_collection_url("moviefan123", "collect", 30)
        self.assertEqual(url, "https://movie.douban.com/people/moviefan123/collect?start=30&sort=time&rating=all&filter=all&mode=grid")

    def test_parse_user_collection_html_extracts_title_rating_and_url(self):
        items = parse_user_collection_html(COLLECT_HTML, status="collect")

        self.assertEqual(len(items), 2)
        first = items[0]
        self.assertEqual(first.title, "隐秘的角落")
        self.assertEqual(first.my_rating, 5)
        self.assertEqual(first.year, 2020)
        self.assertEqual(first.media_type, "电影")
        self.assertIn("剧情", first.genres)
        self.assertIn("悬疑", first.genres)
        self.assertIn("犯罪", first.genres)
        self.assertIn("中国大陆", first.countries)
        self.assertIn("看过", first.tags)
        self.assertEqual(first.douban_id, "33404425")
        self.assertEqual(first.cover, "https://img.example/cover.jpg")
        self.assertEqual(first.summary, "孩子、家庭与犯罪的阴影")

    def test_parse_user_collection_html_handles_no_rating(self):
        items = parse_user_collection_html(COLLECT_HTML, status="wish")

        second = items[1]
        self.assertEqual(second.title, "想见你")
        self.assertIsNone(second.my_rating)
        self.assertIn("想看", second.tags)


if __name__ == "__main__":
    unittest.main()
