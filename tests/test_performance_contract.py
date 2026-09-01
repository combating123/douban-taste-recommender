import re
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
        self.assertRegex(js, r"MAX_INITIAL_CARDS\s*=\s*12")

    def test_each_initial_shelf_applies_the_card_bound_without_hiding_source_counts(self):
        tonight = ui_text("js/features/tonight.js")
        shelf = ui_text("js/components/shelf.js")

        self.assertGreaterEqual(
            len(re.findall(r"itemLimit:\s*MAX_INITIAL_CARDS", tonight)),
            2,
        )
        self.assertRegex(
            shelf,
            r"filterItems\(safeItems,\s*activeFilter\)\.slice\(0,\s*safeItemLimit\)",
        )
        self.assertIn("counts.all = safeItems.length", shelf)
        self.assertNotRegex(
            tonight,
            r"batchItems\(state\)\.slice\(0,\s*MAX_INITIAL_CARDS\)",
        )

    def test_library_virtual_rows_use_a_bounded_cinematic_height(self):
        js = ui_text("js/features/library.js")
        css = ui_text("styles/spaces.css")
        match = re.search(r"ROW_HEIGHT\s*=\s*(\d+)", js)
        self.assertIsNotNone(match)
        row_height = int(match.group(1))
        self.assertGreaterEqual(row_height, 360)
        self.assertLessEqual(row_height, 400)
        overscan = re.search(r"OVERSCAN_ROWS\s*=\s*(\d+)", js)
        self.assertIsNotNone(overscan)
        self.assertGreaterEqual(int(overscan.group(1)), 3)
        self.assertRegex(
            css,
            r"\.library-window\s*\{[^}]*overflow-anchor:\s*none",
            "分页在哨兵前扩展虚拟高度时必须禁用浏览器滚动锚定，避免滚动位置瞬间贴底",
        )

    def test_people_prefetch_is_limited_to_director_and_eight_cast(self):
        js = ui_text("js/features/detail.js")
        self.assertIn("const directors = listValue(item.directors)", js)
        self.assertIn("casts.slice(0, 8)", js)
        self.assertRegex(
            js,
            r"requestedNames\s*=\s*\[\.\.\.directors\.slice\(0,\s*2\),\s*\.\.\.casts\.slice\(0,\s*8\)\]",
        )
        self.assertIn("function portraitJobPriority", js)
        self.assertRegex(js, r"kind:\s*[\"']portrait[\"'][\s\S]*?priority:\s*portraitJobPriority\(person,\s*item\)")

    def test_library_detail_warmup_is_bounded_and_detail_reuses_v2_cache(self):
        library = ui_text("js/features/library.js")
        detail = ui_text("js/features/detail.js")

        self.assertRegex(library, r"DETAIL_WARM_CONCURRENCY\s*=\s*2")
        for event_name in ("pointerenter", "focus", "pointerdown"):
            self.assertIn(f'addEventListener("{event_name}"', library)
        self.assertIn("detailWarmQueue", library)
        self.assertIn("activeDetailWarmKeys", library)
        self.assertRegex(
            detail,
            r"const title\s*=\s*await detailApiGet\(`/api/v2/titles/\$\{cleanId\}`,[\s\S]*?signal:\s*options\.signal",
        )
        self.assertNotRegex(
            library,
            r"for\s*\([^)]*\bitems\b[^)]*\)[\s\S]{0,240}fetchJson\(`/api/v2/titles/",
            "详情预热只能由用户意图触发，不能遍历整个片库无界预取",
        )


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
        self.assertIn('typeof image.decode === "function" ? image.decode() : null', core)
        self.assertIn("Promise.resolve(decoding).then", core)
        self.assertIn("queueMicrotask", core)
        self.assertIn("image.naturalWidth > 0 ? image : null", core)
        self.assertRegex(
            frame,
            r"const request = preloadLocalMedia\(normalized\.localUrl,\s*frame,\s*\{"
            r"\s*priority:\s*options\.priority,"
            r"\s*coordinator:\s*options\.coordinator,"
            r"\s*backgroundOnly:\s*options\.backgroundOnly,"
            r"\s*\}\);"
            r"[\s\S]*?request\.then\(\(image\)\s*=>\s*\{"
            r"[\s\S]*?frame\.replaceChildren\(image\)",
        )
        self.assertIn("activePreload?.cancel?.()", frame)

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
