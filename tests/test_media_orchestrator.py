import io
import tempfile
import time
import unittest
from pathlib import Path

from PIL import Image

from douban_recommender.database import AppDatabase
from douban_recommender.identity_service import WorkIdentity
from douban_recommender.media.orchestrator import (
    MediaOrchestrator,
    MediaResolutionRequest,
)
from douban_recommender.media.providers.base import AssetCandidate, AssetQuery
from douban_recommender.media.store import MediaStore


def png_bytes(color="navy"):
    output = io.BytesIO()
    Image.new("RGB", (180, 270), color).save(output, format="PNG")
    return output.getvalue()


def work_identity(year=2021, director="木下麦"):
    return WorkIdentity(
        title="奇巧计程车",
        original_titles=("ODDTAXI",),
        year=year,
        media_type="动漫",
        countries=("日本",),
        directors=(director,) if director else (),
        episode_count=13,
    )


def candidate(source, url, year=2021, director="木下麦"):
    return AssetCandidate(
        url=url,
        source=source,
        kind="poster",
        work_identity=work_identity(year, director),
        declared_type="image/png",
    )


def anime_request(priority=100):
    return MediaResolutionRequest(
        identity_key="title:odd-taxi",
        kind="poster",
        priority=priority,
        query=AssetQuery(
            kind="poster",
            title="奇巧计程车",
            original_titles=("ODDTAXI",),
            year=2021,
            media_type="动漫",
            countries=("日本",),
            directors=("木下麦",),
            episode_count=13,
        ),
    )


class FakeProvider:
    def __init__(self, name, candidates=None, error=None):
        self.name = name
        self.candidates = list(candidates or [])
        self.error = error

    def search(self, query):
        if self.error:
            raise self.error
        return list(self.candidates)


class MediaOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.database = AppDatabase(root / "cinescope.db")
        self.database.initialize()
        self.store = MediaStore(root / "media", self.database)
        self.payloads = {
            "https://wrong/poster.png": (png_bytes("red"), "image/png"),
            "https://right/poster.png": (png_bytes("green"), "image/png"),
            "https://broken/poster.png": (b"<html>captcha</html>", "text/html"),
        }
        self.orchestrators = []

    def tearDown(self):
        for orchestrator in self.orchestrators:
            orchestrator.close()
        self.temp.cleanup()

    def make_orchestrator(self, providers):
        orchestrator = MediaOrchestrator(
            store=self.store,
            providers=providers,
            fetch=lambda url: self.payloads[url],
            max_workers=1,
        )
        self.orchestrators.append(orchestrator)
        return orchestrator

    def test_rejects_wrong_first_candidate_and_accepts_verified_second(self):
        wrong = FakeProvider("first", [candidate("first", "https://wrong/poster.png", year=1990)])
        right = FakeProvider("second", [candidate("second", "https://right/poster.png")])
        result = self.make_orchestrator([wrong, right]).resolve(anime_request())
        self.assertEqual((result.status, result.source), ("ready", "second"))
        self.assertTrue(result.local_url.startswith("/media/"))
        self.assertEqual(result.attempts[0]["status"], "identity-rejected")

    def test_invalid_image_falls_through_to_next_provider(self):
        broken = FakeProvider("broken", [candidate("broken", "https://broken/poster.png")])
        right = FakeProvider("second", [candidate("second", "https://right/poster.png")])
        result = self.make_orchestrator([broken, right]).resolve(anime_request())
        self.assertEqual(result.source, "second")
        self.assertIn("not an image", result.attempts[0]["error"])

    def test_all_sources_fail_returns_degraded_without_broken_url(self):
        result = self.make_orchestrator(
            [FakeProvider("offline", error=OSError("offline"))]
        ).resolve(anime_request())
        self.assertEqual(result.status, "degraded")
        self.assertEqual(result.local_url, "")
        self.assertEqual(result.asset_id, "")

    def test_enqueued_job_reaches_ready_and_is_persisted(self):
        orchestrator = self.make_orchestrator(
            [FakeProvider("right", [candidate("right", "https://right/poster.png")])]
        )
        job_id = orchestrator.enqueue(anime_request())
        deadline = time.time() + 3
        job = orchestrator.job(job_id)
        while job["state"] not in {"ready", "degraded"} and time.time() < deadline:
            time.sleep(0.02)
            job = orchestrator.job(job_id)
        self.assertEqual(job["state"], "ready")
        self.assertTrue(job["result"]["local_url"].startswith("/media/"))
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT state, attempts_json FROM resolution_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        self.assertEqual(row["state"], "ready")
        self.assertIn("right", row["attempts_json"])


if __name__ == "__main__":
    unittest.main()
