import io
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from PIL import Image

from douban_recommender.catalog_registry import CatalogRegistry
from douban_recommender.catalog_api import CatalogApi
from douban_recommender.database import AppDatabase
from douban_recommender.media.orchestrator import MediaOrchestrator
from douban_recommender.media.providers.inline import InlineProvider
from douban_recommender.media.store import MediaStore
from douban_recommender.media.validator import validate_image_bytes
from douban_recommender.media_api import MediaApi
from douban_recommender.models import MediaItem
from douban_recommender.serialization import media_item_to_dict
from douban_recommender.web import Handler
import douban_recommender.web as web_module


def png_bytes():
    output = io.BytesIO()
    Image.new("RGB", (180, 270), "navy").save(output, format="PNG")
    return output.getvalue()


class FakeOrchestrator:
    def __init__(self):
        self.requests = []
        self.jobs = {}

    def enqueue(self, request):
        self.requests.append(request)
        self.jobs["job-1"] = {"id": "job-1", "state": "queued", "result": {}}
        return "job-1"

    def job(self, job_id):
        return dict(self.jobs.get(job_id) or {})


class MediaApiRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.database = AppDatabase(root / "cinescope.db")
        self.database.initialize()
        self.store = MediaStore(root / "media", self.database)
        self.orchestrator = FakeOrchestrator()
        self.api = MediaApi(self.store, self.orchestrator)
        self.original_media_api = getattr(web_module, "MEDIA_API", None)
        web_module.MEDIA_API = self.api
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        web_module.MEDIA_API = self.original_media_api
        self.thread.join(timeout=5)
        self.temp.cleanup()

    def request(self, path, method="GET", payload=None):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, dict(response.headers.items()), response.read()
        except urllib.error.HTTPError as error:
            try:
                return error.code, dict(error.headers.items()), error.read()
            finally:
                error.close()

    def test_local_media_route_returns_immutable_asset(self):
        asset = self.store.put(
            validate_image_bytes(png_bytes()),
            "https://img.example/poster.png",
            "poster",
        )
        status, headers, body = self.request(asset.local_url)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "public, max-age=31536000, immutable")
        self.assertEqual(headers["Content-Type"], "image/png")
        self.assertTrue(body.startswith(b"\x89PNG"))

    def test_unknown_or_unsafe_media_route_returns_404(self):
        status, _, _ = self.request("/media/not-a-sha.png")
        self.assertEqual(status, 404)

    def test_media_job_payload_does_not_echo_cookie(self):
        status, _, body = self.request(
            "/api/v2/media/jobs",
            method="POST",
            payload={
                "kind": "portrait",
                "identity_key": "person:actor-a",
                "person_name": "演员甲",
                "occupations": ["演员"],
                "work_context": ["作品甲"],
                "source_urls": ["https://upload.wikimedia.org/actor.png"],
                "cookie": "secret-cookie-value",
            },
        )
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(status, 200)
        self.assertEqual(payload["job_id"], "job-1")
        self.assertNotIn("secret-cookie-value", json.dumps(payload, ensure_ascii=False))
        self.assertEqual(self.orchestrator.requests[0].query.person_name, "演员甲")
        self.assertEqual(
            getattr(self.orchestrator.requests[0].query, "source_urls", ()),
            ("https://upload.wikimedia.org/actor.png",),
        )

    def test_media_job_hydrates_registered_work_source_and_provider_identity(self):
        item = MediaItem(
            title="Registered work",
            year=2024,
            media_type="电影",
            douban_id="9911",
            cover="https://img9.doubanio.com/view/photo/s_ratio_poster/public/p9911.jpg",
            source="douban_user:collect",
        )
        now = time.time()
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO library_items(item_key, payload_json, state, source, created_at, updated_at)
                VALUES('douban:9911', ?, 'watched', 'douban-sync:user:watched', ?, ?)
                """,
                (json.dumps(media_item_to_dict(item), ensure_ascii=False), now, now),
            )
            connection.execute(
                """
                INSERT INTO media_identities(id, title, original_titles_json, year, media_type, countries_json, metadata_json, created_at, updated_at)
                VALUES('douban:9911', 'Registered work', '[]', 2024, '电影', '[]', ?, ?, ?)
                """,
                (json.dumps({"item_key": "douban:9911", "cover_url": item.cover}), now, now),
            )
            connection.execute(
                """
                INSERT INTO provider_identities(entity_kind, entity_id, provider, provider_id, confidence, metadata_json, created_at, updated_at)
                VALUES('media', 'douban:9911', 'douban', '9911', 1, '{}', ?, ?)
                """,
                (now, now),
            )

        created = self.api.create_job({"kind": "poster", "identity_key": "douban:9911"})

        request = self.orchestrator.requests[-1]
        self.assertEqual(created["identity_key"], "douban:9911")
        self.assertEqual(request.query.title, "Registered work")
        self.assertEqual(request.query.year, 2024)
        self.assertEqual(request.query.source_urls, (item.cover,))
        self.assertEqual(request.query.provider_ids, {"douban": "9911"})

    def test_media_job_hydrates_registered_person_portrait_sources(self):
        now = time.time()
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO person_identities(id, name, aliases_json, metadata_json, created_at, updated_at)
                VALUES('person:actor', '演员甲', '[]', ?, ?, ?)
                """,
                (json.dumps({"roles": ["cast"], "known_works": ["作品甲"], "portrait_source_urls": ["https://upload.wikimedia.org/actor.jpg"]}), now, now),
            )

        self.api.create_job({"kind": "portrait", "identity_key": "person:actor"})

        query = self.orchestrator.requests[-1].query
        self.assertEqual(query.person_name, "演员甲")
        self.assertEqual(query.occupations, ("cast",))
        self.assertEqual(query.work_context, ("作品甲",))
        self.assertEqual(query.source_urls, ("https://upload.wikimedia.org/actor.jpg",))

    def test_portrait_job_needs_only_registered_person_identity_key(self):
        item = MediaItem(
            title="Registered portrait work",
            directors=["导演甲"],
            casts=["演员乙"],
            source="douban_user:collect",
            raw={
                "people_photos": {
                    "导演:导演甲": "https://img9.doubanio.com/director-real.jpg",
                    "演员乙": "https://upload.wikimedia.org/actor-real.jpg",
                    "无关剧照": "https://img9.doubanio.com/unrelated.jpg",
                }
            },
        )
        with self.database.connection() as connection:
            CatalogRegistry.register_sync_items(connection, "272042071", [item], time.time())
            person_id = connection.execute(
                "SELECT id FROM person_identities WHERE name='导演甲'"
            ).fetchone()["id"]

        self.api.create_job({"kind": "portrait", "identity_key": person_id})

        query = self.orchestrator.requests[-1].query
        self.assertEqual(query.person_name, "导演甲")
        self.assertEqual(query.source_urls, ("https://img9.doubanio.com/director-real.jpg",))

    def test_media_job_and_health_routes_report_public_state(self):
        asset = self.store.put(
            validate_image_bytes(png_bytes()),
            "https://img.example/ready.png",
            "poster",
        )
        self.orchestrator.jobs["job-2"] = {
            "id": "job-2",
            "state": "ready",
            "result": {"status": "ready", "asset_id": asset.asset_id, "local_url": asset.local_url},
        }
        status, _, body = self.request("/api/v2/media/jobs/job-2")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["state"], "ready")

        status, _, body = self.request("/api/v2/media/health")
        health = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(health["schema_version"], 2)
        self.assertIn("assets", health)
        self.assertIn("jobs", health)

    def test_media_job_never_exposes_external_url_as_ready(self):
        self.orchestrator.jobs["job-external"] = {
            "id": "job-external",
            "state": "ready",
            "result": {"status": "ready", "local_url": "https://img.example/not-local.png"},
        }

        status, _, body = self.request("/api/v2/media/jobs/job-external")
        payload = json.loads(body.decode("utf-8"))

        self.assertEqual(status, 200)
        self.assertEqual(payload["state"], "degraded")
        self.assertEqual(payload["result"]["status"], "degraded")
        self.assertNotIn("https://img.example", json.dumps(payload))

    def test_media_job_accepts_shared_asset_for_requested_kind(self):
        validated = validate_image_bytes(png_bytes())
        self.store.put(validated, "https://img.example/poster.png", "poster")
        shared = self.store.put(validated, "https://img.example/backdrop.png", "backdrop")
        self.orchestrator.jobs["job-shared"] = {
            "id": "job-shared",
            "kind": "backdrop",
            "state": "ready",
            "result": {
                "status": "ready",
                "asset_id": shared.asset_id,
                "local_url": shared.local_url,
            },
        }

        status, _, body = self.request("/api/v2/media/jobs/job-shared")
        payload = json.loads(body.decode("utf-8"))

        self.assertEqual(status, 200)
        self.assertEqual(payload["state"], "ready")

    def test_inline_job_is_immediately_visible_through_catalog_local_media(self):
        now = time.time()
        item = MediaItem(
            title="奇巧计程车",
            year=2021,
            media_type="动漫",
            douban_id="46102",
            source="douban_sync",
        )
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO library_items(item_key, payload_json, state, source, created_at, updated_at)
                VALUES('douban:46102', ?, 'watched', 'douban_sync', ?, ?)
                """,
                (json.dumps(media_item_to_dict(item), ensure_ascii=False), now, now),
            )
            connection.execute(
                """
                INSERT INTO media_identities(
                    id, title, original_titles_json, year, media_type,
                    countries_json, metadata_json, created_at, updated_at
                ) VALUES('media-odd-taxi', '奇巧计程车', '[]', 2021, '动漫', '[]',
                         '{"item_key":"douban:46102"}', ?, ?)
                """,
                (now, now),
            )

        orchestrator = MediaOrchestrator(
            self.store,
            providers=[InlineProvider()],
            fetch=lambda _url: (png_bytes(), "image/png"),
            max_workers=1,
        )
        api = MediaApi(self.store, orchestrator)
        try:
            created = api.create_job(
                {
                    "kind": "poster",
                    "identity_key": "media-odd-taxi",
                    "title": "奇巧计程车",
                    "year": 2021,
                    "media_type": "动漫",
                    "source_urls": ["https://img9.doubanio.com/poster.png"],
                    "priority": 100,
                }
            )
            deadline = time.time() + 3
            job = api.get_job(created["job_id"])
            while job["state"] not in {"ready", "degraded"} and time.time() < deadline:
                time.sleep(0.02)
                job = api.get_job(created["job_id"])

            self.assertEqual(job["state"], "ready")
            self.assertTrue(job["result"]["local_url"].startswith("/media/"))
            title = CatalogApi(self.database, media_root=self.store.root).get_title("media-odd-taxi")
            self.assertEqual(title["poster"]["media_status"], "ready")
            self.assertEqual(title["poster"]["url"], job["result"]["local_url"])
        finally:
            orchestrator.close()


if __name__ == "__main__":
    unittest.main()
