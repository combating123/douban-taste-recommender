import io
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from douban_recommender.database import AppDatabase
from douban_recommender.identity_service import WorkIdentity
from douban_recommender.media.orchestrator import (
    MediaOrchestrator,
    MediaResolutionRequest,
    _default_fetch,
)
from douban_recommender.media.providers.base import AssetCandidate, AssetQuery
from douban_recommender.media.providers.inline import InlineProvider
from douban_recommender.media.store import MediaStore
from douban_recommender.media.validator import validate_image_bytes


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
            "https://minimal/poster.png": (png_bytes("purple"), "image/png"),
            "https://upload.wikimedia.org/actor.png": (png_bytes("orange"), "image/png"),
        }
        self.orchestrators = []

    def tearDown(self):
        for orchestrator in self.orchestrators:
            orchestrator.close()
        self.temp.cleanup()

    def make_orchestrator(self, providers, fetch=None):
        orchestrator = MediaOrchestrator(
            store=self.store,
            providers=providers,
            fetch=fetch or (lambda url: self.payloads[url]),
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

    def test_exact_title_and_year_are_sufficient_identity_evidence(self):
        minimal = AssetCandidate(
            url="https://minimal/poster.png",
            source="minimal",
            kind="poster",
            work_identity=WorkIdentity(
                title="奇巧计程车",
                year=2021,
                media_type="动漫",
            ),
            declared_type="image/png",
        )

        result = self.make_orchestrator([FakeProvider("minimal", [minimal])]).resolve(anime_request())

        self.assertEqual(result.status, "ready")
        self.assertIn("exact-title-year", result.attempts[-1]["reasons"])

    def test_embedded_portrait_is_accepted_from_visible_person_context(self):
        request = MediaResolutionRequest(
            identity_key="person:actor-a",
            kind="portrait",
            priority=100,
            query=AssetQuery(
                kind="portrait",
                person_name="演员甲",
                source_urls=("https://upload.wikimedia.org/actor.png",),
            ),
        )

        result = self.make_orchestrator([InlineProvider()]).resolve(request)

        self.assertEqual((result.status, result.source), ("ready", "inline"))
        self.assertTrue(result.local_url.startswith("/media/"))

    def test_douban_image_hosts_fail_over_before_abandoning_candidate(self):
        original = "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p616779645.jpg"
        seen = []

        def fetch(url):
            seen.append(url)
            if "img9.doubanio.com" in url or "img1.doubanio.com" in url:
                raise OSError("host unavailable")
            return png_bytes("green"), "image/png"

        provider = FakeProvider("douban", [candidate("douban", original)])
        result = self.make_orchestrator([provider], fetch=fetch).resolve(anime_request())

        self.assertEqual(result.status, "ready")
        self.assertEqual(
            seen[:3],
            [
                original,
                original.replace("img9.doubanio.com", "img1.doubanio.com"),
                original.replace("img9.doubanio.com", "img2.doubanio.com"),
            ],
        )

    def test_default_fetch_builds_source_specific_browser_request(self):
        class Response:
            headers = {"Content-Type": "image/png"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return png_bytes()

        class Opener:
            def __init__(self):
                self.requests = []

            def open(self, request, timeout):
                self.requests.append((request, timeout))
                return Response()

        opener = Opener()
        with patch("douban_recommender.media.orchestrator.build_url_opener", return_value=opener):
            _default_fetch("https://img9.doubanio.com/poster.png")

        request, timeout = opener.requests[0]
        self.assertEqual(timeout, 12)
        self.assertTrue(request.get_header("User-agent").startswith("Mozilla/5.0"))
        self.assertEqual(request.get_header("Referer"), "https://movie.douban.com/")

    def test_all_sources_fail_returns_degraded_without_broken_url(self):
        result = self.make_orchestrator(
            [FakeProvider("offline", error=OSError("offline"))]
        ).resolve(anime_request())
        self.assertEqual(result.status, "degraded")
        self.assertEqual(result.local_url, "")
        self.assertEqual(result.asset_id, "")

    def test_ready_result_binds_candidate_and_selected_override(self):
        result = self.make_orchestrator(
            [FakeProvider("right", [candidate("right", "https://right/poster.png")])]
        ).resolve(anime_request())

        self.assertEqual(result.status, "ready")
        with self.database.connection() as connection:
            candidate_row = connection.execute(
                """
                SELECT source, status, metadata_json
                FROM asset_candidates
                WHERE entity_kind = 'media' AND entity_id = 'title:odd-taxi' AND kind = 'poster'
                """
            ).fetchone()
            override_row = connection.execute(
                """
                SELECT asset_id, decision
                FROM user_asset_overrides
                WHERE entity_kind = 'media' AND entity_id = 'title:odd-taxi' AND kind = 'poster'
                """
            ).fetchone()

        self.assertIsNotNone(candidate_row)
        self.assertIsNotNone(override_row)
        self.assertEqual((candidate_row["source"], candidate_row["status"]), ("right", "ready"))
        self.assertIn(result.local_url, candidate_row["metadata_json"])
        self.assertEqual((override_row["asset_id"], override_row["decision"]), (result.asset_id, "selected"))

    def test_non_local_store_result_can_never_be_reported_ready(self):
        stored = self.store.put(
            validate_image_bytes(png_bytes("green")),
            "https://right/poster.png",
            "poster",
        )
        external = replace(stored, local_url="https://right/poster.png")
        orchestrator = self.make_orchestrator(
            [FakeProvider("right", [candidate("right", "https://right/poster.png")])]
        )

        with patch.object(self.store, "put", return_value=external):
            result = orchestrator.resolve(anime_request())

        self.assertEqual(result.status, "degraded")
        self.assertEqual(result.local_url, "")
        self.assertEqual(result.attempts[-1]["status"], "asset-rejected")

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
