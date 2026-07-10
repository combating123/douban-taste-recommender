import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from douban_recommender.database import AppDatabase
from douban_recommender.media.store import MediaStore
from douban_recommender.media.validator import MediaValidationError, validate_image_bytes


def image_bytes(size=(160, 240), image_format="PNG", color="navy"):
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format=image_format)
    return output.getvalue()


class MediaValidatorTests(unittest.TestCase):
    def test_rejects_antibot_html(self):
        with self.assertRaisesRegex(MediaValidationError, "not an image"):
            validate_image_bytes(b"<html><title>captcha</title></html>", "text/html")

    def test_rejects_json_error_payload(self):
        with self.assertRaisesRegex(MediaValidationError, "not an image"):
            validate_image_bytes(b'{"error":"rate limited"}', "application/json")

    def test_decodes_dimensions_format_and_hash(self):
        result = validate_image_bytes(image_bytes())
        self.assertEqual((result.width, result.height), (160, 240))
        self.assertEqual((result.extension, result.mime_type), (".png", "image/png"))
        self.assertEqual(len(result.sha256), 64)

    def test_rejects_undersized_image(self):
        with self.assertRaisesRegex(MediaValidationError, "too small"):
            validate_image_bytes(image_bytes(size=(32, 32)))

    def test_rejects_declared_non_image_even_when_bytes_decode(self):
        with self.assertRaisesRegex(MediaValidationError, "declared content type"):
            validate_image_bytes(image_bytes(), "text/html")


class MediaStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.database = AppDatabase(root / "cinescope.db")
        self.database.initialize()
        self.store = MediaStore(root / "media", self.database)

    def tearDown(self):
        self.temp.cleanup()

    def test_same_bytes_share_one_local_asset(self):
        validated = validate_image_bytes(image_bytes())
        first = self.store.put(validated, "https://a.example/poster", "poster")
        second = self.store.put(validated, "https://b.example/poster", "poster")
        self.assertEqual(first.asset_id, second.asset_id)
        self.assertEqual(first.local_url, f"/media/{first.asset_id}.png")
        self.assertTrue(self.store.path_for(first.asset_id).is_file())
        with self.database.connection() as connection:
            count = connection.execute("SELECT COUNT(*) FROM asset_files").fetchone()[0]
        self.assertEqual(count, 1)

    def test_lookup_accepts_route_filename_and_returns_metadata(self):
        stored = self.store.put(
            validate_image_bytes(image_bytes(image_format="JPEG")),
            "https://img.example/person.jpg",
            "portrait",
        )
        loaded = self.store.lookup(f"{stored.asset_id}.jpg")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.kind, "portrait")
        self.assertEqual(loaded.mime_type, "image/jpeg")
        self.assertEqual(loaded.path, self.store.path_for(stored.asset_id))

    def test_unknown_or_unsafe_asset_id_returns_none(self):
        self.assertIsNone(self.store.lookup("../web.py"))
        self.assertIsNone(self.store.lookup("not-a-sha"))


if __name__ == "__main__":
    unittest.main()
