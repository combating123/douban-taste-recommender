import threading
import time
import unittest
from unittest import mock

from douban_recommender.models import MediaItem


class CatalogEnrichmentTests(unittest.TestCase):
    def test_parallel_enrichment_is_bounded_and_preserves_item_order(self):
        from douban_recommender.catalog_enrichment import enrich_media_items_parallel

        items = [MediaItem(title=f"Title {index}", douban_id=str(index)) for index in range(8)]
        active = 0
        peak = 0
        lock = threading.Lock()

        def fake_enrich(selected, **_kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.03)
            selected[0].summary = f"summary-{selected[0].douban_id}"
            with lock:
                active -= 1
            return selected

        with mock.patch("douban_recommender.catalog_enrichment.enrich_media_items", side_effect=fake_enrich):
            returned = enrich_media_items_parallel(items, limit=5, max_workers=3)

        self.assertIs(returned, items)
        self.assertGreaterEqual(peak, 2)
        self.assertLessEqual(peak, 3)
        self.assertEqual([item.summary for item in items[:5]], [f"summary-{index}" for index in range(5)])
        self.assertEqual([item.summary for item in items[5:]], ["", "", ""])


if __name__ == "__main__":
    unittest.main()
