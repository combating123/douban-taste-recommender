from pathlib import Path
import tempfile
import unittest

from douban_recommender.models import MediaItem
from douban_recommender.storage import CacheStore


class CacheStoreTests(unittest.TestCase):
    def test_library_round_trips_without_cookie(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CacheStore(Path(tmp))
            store.save_library(
                [MediaItem(title="隐秘的角落", douban_id="33404425", tags=["看过"])],
                sync_report={"status": "ok", "cookie": "bid=secret"},
            )

            loaded_items, report = store.load_library()
            raw = (Path(tmp) / "library.json").read_text(encoding="utf-8") + (
                Path(tmp) / "sync_report.json"
            ).read_text(encoding="utf-8")

            self.assertEqual(loaded_items[0].title, "隐秘的角落")
            self.assertEqual(report["status"], "ok")
            self.assertNotIn("secret", raw)
            self.assertNotIn("bid=", raw)

    def test_broken_cache_returns_empty_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "library.json").write_text("{bad json", encoding="utf-8")

            items, report = CacheStore(Path(tmp)).load_library()

            self.assertEqual(items, [])
            self.assertEqual(report, {})


if __name__ == "__main__":
    unittest.main()
