import io
import hashlib
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

    def test_put_sanitizes_source_url_before_persisting(self):
        stored = self.store.put(
            validate_image_bytes(image_bytes()),
            "https://user:pass@img.example/poster.png?api_key=secret-token&width=200#frag",
            "poster",
        )

        self.assertEqual(stored.source_url, "https://img.example/poster.png")
        with self.database.connection() as connection:
            source_url = connection.execute(
                "SELECT source_url FROM asset_files WHERE asset_id = ?",
                (stored.asset_id,),
            ).fetchone()[0]
        self.assertEqual(source_url, "https://img.example/poster.png")
        self.assertNotIn("user:pass", source_url)
        self.assertNotIn("secret-token", source_url)
        self.assertNotIn("?", source_url)
        self.assertNotIn("#", source_url)

    def test_unknown_or_unsafe_asset_id_returns_none(self):
        self.assertIsNone(self.store.lookup("../web.py"))
        self.assertIsNone(self.store.lookup("not-a-sha"))

    def test_lookup_rejects_manifest_pointing_at_another_asset_file(self):
        first = self.store.put(validate_image_bytes(image_bytes(color="navy")), "https://img.example/a.png", "poster")
        second_validated = validate_image_bytes(image_bytes(color="green"))
        second_relative = Path(second_validated.sha256[:2]) / f"{second_validated.sha256}{second_validated.extension}"
        second_path = self.store.root / second_relative
        second_path.parent.mkdir(parents=True, exist_ok=True)
        second_path.write_bytes(second_validated.data)

        with self.database.connection() as connection:
            connection.execute(
                "UPDATE asset_files SET relative_path = ? WHERE asset_id = ?",
                (second_relative.as_posix(), first.asset_id),
            )

        self.assertIsNone(self.store.lookup(first.asset_id))

    def test_lookup_rejects_sha256_column_that_does_not_match_asset_id(self):
        stored = self.store.put(validate_image_bytes(image_bytes(color="navy")), "https://img.example/a.png", "poster")
        wrong_hash = hashlib.sha256(b"not the stored image").hexdigest()

        with self.database.connection() as connection:
            connection.execute("UPDATE asset_files SET sha256 = ? WHERE asset_id = ?", (wrong_hash, stored.asset_id))

        self.assertIsNone(self.store.lookup(stored.asset_id))

    def test_lookup_rejects_relative_path_name_that_does_not_match_manifest(self):
        validated = validate_image_bytes(image_bytes(color="navy"))
        stored = self.store.put(validated, "https://img.example/a.png", "poster")
        wrong_relative = Path(stored.asset_id[:2]) / f"copy-{stored.asset_id}.png"
        wrong_path = self.store.root / wrong_relative
        wrong_path.parent.mkdir(parents=True, exist_ok=True)
        wrong_path.write_bytes(validated.data)

        with self.database.connection() as connection:
            connection.execute(
                "UPDATE asset_files SET relative_path = ? WHERE asset_id = ?",
                (wrong_relative.as_posix(), stored.asset_id),
            )

        self.assertIsNone(self.store.lookup(stored.asset_id))

    def test_lookup_rejects_file_content_replaced_after_manifest_write(self):
        stored = self.store.put(validate_image_bytes(image_bytes(color="navy")), "https://img.example/a.png", "poster")
        replacement = validate_image_bytes(image_bytes(color="green"))
        stored.path.write_bytes(replacement.data)

        self.assertIsNone(self.store.lookup(stored.asset_id))

    def test_lookup_rejects_self_consistent_manifest_when_bytes_are_not_decodable_image(self):
        payload = b"not an image"
        asset_id = hashlib.sha256(payload).hexdigest()
        relative = Path(asset_id[:2]) / f"{asset_id}.png"
        path = self.store.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO asset_files(
                    asset_id, sha256, relative_path, mime_type, extension,
                    width, height, byte_size, source_url, kind, status,
                    created_at, last_verified_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', 0, 0)
                """,
                (
                    asset_id,
                    asset_id,
                    relative.as_posix(),
                    "image/png",
                    ".png",
                    1,
                    1,
                    len(payload),
                    "https://img.example/forged.png",
                    "poster",
                ),
            )

        self.assertIsNone(self.store.lookup(asset_id))

    def test_lookup_rejects_manifest_metadata_that_does_not_match_decoded_image(self):
        validated = validate_image_bytes(image_bytes(size=(160, 240), color="navy"))
        stored = self.store.put(validated, "https://img.example/a.png", "poster")
        cases = (
            ("mime_type", "image/jpeg"),
            ("extension", ".jpg"),
            ("width", validated.width + 1),
            ("height", validated.height + 1),
            ("byte_size", len(validated.data) + 1),
        )

        for column, wrong_value in cases:
            with self.subTest(column=column):
                with self.database.connection() as connection:
                    connection.execute(
                        f"UPDATE asset_files SET {column} = ? WHERE asset_id = ?",
                        (wrong_value, stored.asset_id),
                    )

                self.assertIsNone(self.store.lookup(stored.asset_id))

                with self.database.connection() as connection:
                    connection.execute(
                        f"UPDATE asset_files SET {column} = ? WHERE asset_id = ?",
                        (getattr(validated, column, len(validated.data)), stored.asset_id),
                    )

    def test_lookup_rejects_disallowed_manifest_extension(self):
        validated = validate_image_bytes(image_bytes(color="navy"))
        stored = self.store.put(validated, "https://img.example/a.png", "poster")
        gif_relative = Path(stored.asset_id[:2]) / f"{stored.asset_id}.gif"
        gif_path = self.store.root / gif_relative
        gif_path.parent.mkdir(parents=True, exist_ok=True)
        gif_path.write_bytes(validated.data)

        with self.database.connection() as connection:
            connection.execute(
                "UPDATE asset_files SET extension = '.gif', relative_path = ? WHERE asset_id = ?",
                (gif_relative.as_posix(), stored.asset_id),
            )

        self.assertIsNone(self.store.lookup(stored.asset_id))


if __name__ == "__main__":
    unittest.main()
