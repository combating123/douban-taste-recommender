import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from PIL import Image

from douban_recommender.database import AppDatabase
from douban_recommender.media.store import MediaStore
from douban_recommender.media.validator import validate_image_bytes
from douban_recommender.media_api import MediaApi
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
                "cookie": "secret-cookie-value",
            },
        )
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(status, 200)
        self.assertEqual(payload["job_id"], "job-1")
        self.assertNotIn("secret-cookie-value", json.dumps(payload, ensure_ascii=False))
        self.assertEqual(self.orchestrator.requests[0].query.person_name, "演员甲")

    def test_media_job_and_health_routes_report_public_state(self):
        self.orchestrator.jobs["job-2"] = {
            "id": "job-2",
            "state": "ready",
            "result": {"local_url": "/media/example.png"},
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


if __name__ == "__main__":
    unittest.main()
