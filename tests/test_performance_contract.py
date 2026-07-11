import unittest
from pathlib import Path

from douban_recommender import diagnostics


ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "src" / "douban_recommender" / "ui"


def ui_text(relative_path: str) -> str:
    return (UI_ROOT / relative_path).read_text(encoding="utf-8")


class PerformanceContractTests(unittest.TestCase):
    def test_initial_channel_render_is_bounded(self):
        js = ui_text("js/features/tonight.js")
        self.assertIn("MAX_INITIAL_CARDS", js)
        self.assertRegex(js, r"MAX_INITIAL_CARDS\s*=\s*(?:9|10|11|12)")

    def test_each_initial_shelf_applies_the_card_bound(self):
        js = ui_text("js/features/tonight.js")
        self.assertRegex(
            js,
            r"batchItems\(state\)\.slice\(0,\s*MAX_INITIAL_CARDS\)",
        )

    def test_people_prefetch_is_limited_to_director_and_eight_cast(self):
        js = ui_text("js/features/detail.js")
        self.assertIn("const directors = listValue(item.directors)", js)
        self.assertIn("casts.slice(0, 8)", js)
        self.assertRegex(
            js,
            r"requestedNames\s*=\s*\[\.\.\.directors,\s*\.\.\.casts\.slice\(0,\s*8\)\]",
        )
        self.assertRegex(js, r"kind:\s*[\"']portrait[\"'][\s\S]*?priority:\s*0")

    def test_visible_images_remain_local_and_replace_fallback_only_after_decode(self):
        core = ui_text("js/core/media.js")
        frame = ui_text("js/components/media-frame.js")

        self.assertIn('const MEDIA_PREFIX = "/media/"', core)
        self.assertIn("url.origin === location.origin", core)
        self.assertIn("url.pathname.startsWith(MEDIA_PREFIX)", core)
        self.assertIn(
            'normalized.status !== "ready" || !isLocalMediaUrl(normalized.localUrl)',
            frame,
        )
        self.assertIn("await image.decode()", core)
        self.assertIn("image.naturalWidth > 0 ? image : null", core)
        self.assertRegex(
            frame,
            r"preloadLocalMedia\(normalized\.localUrl\)\.then\(\(image\)\s*=>\s*\{"
            r"[\s\S]*?frame\.replaceChildren\(image\)",
        )

    def test_diagnostics_scopes_do_not_imply_visible_session_attribution(self):
        self.assertEqual(diagnostics.MEDIA_AUDIT_SCOPE, "recent_recommendation_batches")
        self.assertEqual(diagnostics.MEDIA_AUDIT_BATCH_LIMIT, 32)
        self.assertEqual(diagnostics.MEDIA_AUDIT_ROW_LIMIT, 256)
        self.assertEqual(
            diagnostics.WRONG_IDENTITY_SCOPE,
            "global_historical_identity_rejected_hard_conflicts",
        )
        self.assertEqual(
            diagnostics.MISSING_IDENTITY_FOREIGN_KEY,
            "unavailable_without_stable_foreign_key",
        )


if __name__ == "__main__":
    unittest.main()
