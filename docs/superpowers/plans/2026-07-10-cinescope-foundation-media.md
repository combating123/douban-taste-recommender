# CineScope Foundation and Trusted Media Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add versioned local persistence and a verified local media pipeline so posters, backdrops, actors, and directors can be delivered without browser hotlinks or broken-image states.

**Architecture:** New focused modules own runtime paths, SQLite, identity confidence, byte validation, content-addressed storage, and media orchestration. Existing source fetchers are wrapped rather than rewritten. `web.py` gains additive `/api/v2/media/*` and `/media/*` routes while all legacy routes remain available.

**Tech Stack:** Python 3.10+, SQLite, Pillow 10+, standard-library HTTP server, `unittest`.

## Global Constraints

- Preserve every pre-existing uncommitted file change.
- Never persist or log Douban Cookie values.
- Browser-facing media URLs must be local `/media/<sha256>.<ext>` URLs.
- Reject HTML, anti-bot responses, undecodable bytes, undersized images, and ambiguous identities.
- Use designed fallbacks when verification fails; never substitute an uncertain image.
- Do not store proxy subscription URLs; only use local endpoint configuration.

---

### Task 1: Runtime Data Paths and SQLite Schema

**Files:**
- Create: `src/douban_recommender/runtime_paths.py`
- Create: `src/douban_recommender/database.py`
- Create: `tests/test_database.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `resolve_data_dir(env: Mapping[str, str] | None = None) -> Path`
- Produces: `AppDatabase(path: Path)`, `AppDatabase.initialize()`, `AppDatabase.connection()`
- Produces: `AppDatabase.upsert_ui_snapshot(key: str, payload: dict) -> None`
- Produces: `AppDatabase.get_ui_snapshot(key: str) -> dict | None`

- [ ] **Step 1: Write failing path and schema tests**

```python
class RuntimePathTests(unittest.TestCase):
    def test_explicit_data_dir_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(resolve_data_dir({"CINESCOPE_DATA_DIR": tmp}), Path(tmp))

class DatabaseTests(unittest.TestCase):
    def test_initialize_creates_versioned_core_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = AppDatabase(Path(tmp) / "cinescope.db")
            db.initialize()
            names = {row[0] for row in db.connection().execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            self.assertTrue({
                "schema_meta", "ui_snapshots", "recommendation_sessions",
                "recommendation_batches", "feedback_events", "media_identities",
                "person_identities", "provider_identities", "asset_files",
                "asset_candidates", "resolution_jobs", "user_asset_overrides",
            } <= names)

    def test_ui_snapshot_round_trip_uses_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = AppDatabase(Path(tmp) / "cinescope.db")
            db.initialize()
            db.upsert_ui_snapshot("primary", {"space": "tonight", "batch": 3})
            self.assertEqual(db.get_ui_snapshot("primary"), {"space": "tonight", "batch": 3})
```

- [ ] **Step 2: Run focused tests and confirm missing imports**

Run: `python -m unittest tests.test_database -v`

Expected: import failure for `douban_recommender.runtime_paths` or `douban_recommender.database`.

- [ ] **Step 3: Implement deterministic paths and schema version 1**

```python
def resolve_data_dir(env=None) -> Path:
    values = dict(os.environ if env is None else env)
    if values.get("CINESCOPE_DATA_DIR"):
        return Path(values["CINESCOPE_DATA_DIR"]).expanduser().resolve()
    if os.name == "nt" and values.get("LOCALAPPDATA"):
        return Path(values["LOCALAPPDATA"]) / "CineScope"
    return Path.home() / ".local" / "share" / "cinescope"

class AppDatabase:
    SCHEMA_VERSION = 1

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript(SCHEMA_V1)
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('version', ?)",
                (str(self.SCHEMA_VERSION),),
            )
```

`SCHEMA_V1` must define every table asserted by the test, use foreign keys where identities own candidates, and give JSON payload columns the `TEXT NOT NULL` type.

- [ ] **Step 4: Add Pillow runtime dependency**

```toml
dependencies = ["Pillow>=10"]
```

- [ ] **Step 5: Run focused and existing storage tests**

Run: `python -m unittest tests.test_database tests.test_web_api -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add pyproject.toml src/douban_recommender/runtime_paths.py src/douban_recommender/database.py tests/test_database.py
git commit -m "feat: add versioned local app database"
```

### Task 2: Image Byte Validation and Content-Addressed Store

**Files:**
- Create: `src/douban_recommender/media/__init__.py`
- Create: `src/douban_recommender/media/models.py`
- Create: `src/douban_recommender/media/validator.py`
- Create: `src/douban_recommender/media/store.py`
- Create: `tests/test_media_store.py`

**Interfaces:**
- Produces: `ValidatedImage(data, mime_type, extension, width, height, sha256)`
- Produces: `validate_image_bytes(data: bytes, declared_type: str = "", min_width: int = 80, min_height: int = 80) -> ValidatedImage`
- Produces: `MediaStore(root: Path, database: AppDatabase)`
- Produces: `MediaStore.put(validated: ValidatedImage, source_url: str, kind: str) -> StoredAsset`
- Produces: `MediaStore.path_for(asset_id: str) -> Path | None`
- Produces: `MediaStore.lookup(asset_id: str) -> StoredAsset | None`

- [ ] **Step 1: Write failing validator and deduplication tests**

```python
def png_bytes(size=(160, 240)):
    output = io.BytesIO()
    Image.new("RGB", size, "navy").save(output, format="PNG")
    return output.getvalue()

class MediaValidatorTests(unittest.TestCase):
    def test_rejects_antibot_html(self):
        with self.assertRaisesRegex(MediaValidationError, "image"):
            validate_image_bytes(b"<html>captcha</html>", "text/html")

    def test_decodes_dimensions_and_hash(self):
        result = validate_image_bytes(png_bytes())
        self.assertEqual((result.width, result.height, result.extension), (160, 240, ".png"))
        self.assertEqual(len(result.sha256), 64)

class MediaStoreTests(unittest.TestCase):
    def test_same_bytes_share_one_local_asset(self):
        first = self.store.put(validate_image_bytes(png_bytes()), "https://a/poster", "poster")
        second = self.store.put(validate_image_bytes(png_bytes()), "https://b/poster", "poster")
        self.assertEqual(first.asset_id, second.asset_id)
        self.assertTrue(self.store.path_for(first.asset_id).is_file())
```

- [ ] **Step 2: Run test and confirm failures**

Run: `python -m unittest tests.test_media_store -v`

Expected: missing media modules.

- [ ] **Step 3: Implement strict Pillow validation**

```python
def validate_image_bytes(data, declared_type="", min_width=80, min_height=80):
    if not data or data.lstrip().startswith((b"<html", b"<!DOCTYPE", b"{")):
        raise MediaValidationError("response is not an image")
    with Image.open(io.BytesIO(data)) as image:
        image.verify()
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        width, height = image.size
        image_format = str(image.format or "").upper()
    if image_format not in {"JPEG", "PNG", "WEBP"}:
        raise MediaValidationError(f"unsupported image format: {image_format}")
    if width < min_width or height < min_height:
        raise MediaValidationError(f"image too small: {width}x{height}")
    extension, mime = FORMAT_MAP[image_format]
    return ValidatedImage(data, mime, extension, width, height, hashlib.sha256(data).hexdigest())
```

- [ ] **Step 4: Implement atomic content-addressed writes and SQLite manifest**

Use `tempfile.NamedTemporaryFile(delete=False, dir=root)` followed by `Path.replace()` so interrupted writes never leave a partial final asset. Insert with `INSERT OR IGNORE` keyed by SHA-256.

- [ ] **Step 5: Run tests**

Run: `python -m unittest tests.test_media_store tests.test_database -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/douban_recommender/media tests/test_media_store.py
git commit -m "feat: add verified local media store"
```

### Task 3: Work and Person Identity Confidence

**Files:**
- Create: `src/douban_recommender/identity_service.py`
- Create: `tests/test_identity_service.py`

**Interfaces:**
- Produces: `WorkIdentity(title, original_titles, year, media_type, countries, directors, casts, episode_count)`
- Produces: `PersonIdentity(name, aliases, occupations, known_works, provider_ids)`
- Produces: `MatchDecision(accepted: bool, confidence: float, reasons: tuple[str, ...], ambiguous: bool)`
- Produces: `match_work_identity(expected: WorkIdentity, candidate: WorkIdentity) -> MatchDecision`
- Produces: `match_person_identity(expected: PersonIdentity, candidate: PersonIdentity, work_context: set[str]) -> MatchDecision`

- [ ] **Step 1: Write identity rejection and acceptance tests**

```python
def test_same_title_wrong_year_is_rejected():
    expected = WorkIdentity("鑻遍泟", (), 2002, "鐢靛奖", ("涓浗澶ч檰",), ("寮犺壓璋?,), (), None)
    candidate = WorkIdentity("鑻遍泟", (), 1997, "鐢靛奖", ("棣欐腐",), (), (), None)
    decision = match_work_identity(expected, candidate)
    self.assertFalse(decision.accepted)

def test_exact_title_type_year_and_director_is_accepted():
    expected = WorkIdentity("濂囧阀璁＄▼杞?, ("ODDTAXI",), 2021, "鍔ㄦ极", ("鏃ユ湰",), ("鏈ㄤ笅楹?,), (), 13)
    candidate = WorkIdentity("ODDTAXI", ("濂囧阀璁＄▼杞?,), 2021, "鍔ㄦ极", ("鏃ユ湰",), ("鏈ㄤ笅楹?,), (), 13)
    self.assertGreaterEqual(match_work_identity(expected, candidate).confidence, 0.92)

def test_same_name_person_requires_work_context():
    expected = PersonIdentity("鐜嬩紵", (), ("瀵兼紨",), ("浣滃搧鐢?,), {})
    wrong = PersonIdentity("鐜嬩紵", (), ("婕斿憳",), ("浣滃搧涔?,), {})
    self.assertFalse(match_person_identity(expected, wrong, {"浣滃搧鐢?}).accepted)
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `python -m unittest tests.test_identity_service -v`

Expected: missing module.

- [ ] **Step 3: Implement normalized evidence scoring**

```python
def match_work_identity(expected, candidate):
    title_match = bool(normalized_titles(expected) & normalized_titles(candidate))
    if not title_match or canonical_media_type(expected.media_type) != canonical_media_type(candidate.media_type):
        return MatchDecision(False, 0.0, ("title-or-type-conflict",), False)
    if expected.year and candidate.year and abs(expected.year - candidate.year) > 1:
        return MatchDecision(False, 0.2, ("year-conflict",), False)
    confidence = 0.68
    reasons = ["title", "media-type"]
    confidence += evidence_overlap(expected.directors, candidate.directors, 0.14, reasons, "director")
    confidence += evidence_overlap(expected.countries, candidate.countries, 0.06, reasons, "country")
    confidence += evidence_overlap(expected.casts, candidate.casts, 0.06, reasons, "cast")
    if expected.year and candidate.year:
        confidence += 0.06
        reasons.append("year")
    accepted = confidence >= 0.92 or (confidence >= 0.82 and len(reasons) >= 4)
    return MatchDecision(accepted, min(confidence, 1.0), tuple(reasons), not accepted)
```

Person matching must require either a shared provider ID or name/alias plus occupation/work context evidence.

- [ ] **Step 4: Run identity and existing title normalization tests**

Run: `python -m unittest tests.test_identity_service tests.test_douban_sources -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/douban_recommender/identity_service.py tests/test_identity_service.py
git commit -m "feat: add strict media identity confidence"
```

### Task 4: Provider Adapter Contract and Existing Source Wrappers

**Files:**
- Create: `src/douban_recommender/media/providers/__init__.py`
- Create: `src/douban_recommender/media/providers/base.py`
- Create: `src/douban_recommender/media/providers/existing.py`
- Create: `tests/test_media_providers.py`
- Modify: `src/douban_recommender/douban_sources.py`

**Interfaces:**
- Produces: `AssetQuery(kind, title, year, media_type, person_name, provider_ids, work_context)`
- Produces: `AssetCandidate(url, source, kind, work_identity, person_identity, declared_type)`
- Produces: protocol `MediaProvider.search(query: AssetQuery) -> list[AssetCandidate]`
- Produces wrappers: `TmdbProvider`, `TvMazeProvider`, `AniListProvider`, `JikanProvider`, `WikipediaProvider`, `DoubanProvider`

- [ ] **Step 1: Write routing tests**

```python
def test_anime_series_provider_order():
    names = [provider.name for provider in providers_for("poster", "鍔ㄦ极")]
    self.assertEqual(names[:2], ["anilist", "jikan"])

def test_series_people_provider_order():
    names = [provider.name for provider in providers_for("portrait", "鐢佃鍓?)]
    self.assertEqual(names[:2], ["tvmaze", "wikidata"])
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_media_providers -v`

Expected: missing provider contract.

- [ ] **Step 3: Implement adapters without duplicating network parsers**

Each wrapper must call an existing `fetch_*_suggestions` or public people resolver and convert the result into `AssetCandidate`. Do not move the existing parsers in this task. Add only the minimal public helper needed to expose provider metadata.

```python
def providers_for(kind, media_type):
    if kind == "portrait":
        return PORTRAIT_PROVIDERS.get(canonical_media_type(media_type), PORTRAIT_DEFAULT)
    return POSTER_PROVIDERS.get(canonical_media_type(media_type), POSTER_DEFAULT)
```

- [ ] **Step 4: Run provider and existing source tests**

Run: `python -m unittest tests.test_media_providers tests.test_douban_sources tests.test_web_api -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/douban_recommender/media/providers src/douban_recommender/douban_sources.py tests/test_media_providers.py
git commit -m "refactor: wrap media sources behind provider contract"
```

### Task 5: Priority Media Orchestrator

**Files:**
- Create: `src/douban_recommender/media/orchestrator.py`
- Create: `tests/test_media_orchestrator.py`

**Interfaces:**
- Produces: `MediaResolutionRequest(identity_key, kind, priority, query)`
- Produces: `MediaResolutionResult(status, asset_id, local_url, source, confidence, attempts)`
- Produces: `MediaOrchestrator.resolve(request) -> MediaResolutionResult`
- Produces: `MediaOrchestrator.enqueue(request) -> str`
- Produces: `MediaOrchestrator.job(job_id) -> dict`

- [ ] **Step 1: Write wrong-image rejection and source-fallback tests**

```python
def test_rejects_wrong_first_candidate_and_accepts_verified_second():
    wrong = FakeProvider("first", [candidate(year=1990)])
    right = FakeProvider("second", [candidate(year=2021, director="鏈ㄤ笅楹?)])
    orchestrator = make_orchestrator([wrong, right])
    result = orchestrator.resolve(anime_request())
    self.assertEqual((result.status, result.source), ("ready", "second"))
    self.assertTrue(result.local_url.startswith("/media/"))

def test_all_sources_fail_returns_degraded_not_broken_url():
    result = make_orchestrator([FailingProvider()]).resolve(anime_request())
    self.assertEqual(result.status, "degraded")
    self.assertEqual(result.local_url, "")
```

- [ ] **Step 2: Run and verify failures**

Run: `python -m unittest tests.test_media_orchestrator -v`

Expected: missing orchestrator.

- [ ] **Step 3: Implement resolve pipeline**

```python
for provider in self.providers_for(request.query):
    for candidate in provider.search(request.query):
        decision = self.identity_matcher(request.query, candidate)
        attempts.append({"source": provider.name, "confidence": decision.confidence})
        if not decision.accepted:
            continue
        try:
            data, content_type = self.fetch(candidate.url)
            stored = self.store.put(validate_image_bytes(data, content_type), candidate.url, request.kind)
        except (OSError, ValueError, MediaValidationError) as exc:
            attempts[-1]["error"] = str(exc)
            continue
        return MediaResolutionResult("ready", stored.asset_id, stored.local_url, provider.name, decision.confidence, attempts)
return MediaResolutionResult("degraded", "", "", "", 0.0, attempts)
```

Use a bounded `ThreadPoolExecutor`, priority queue, provider-specific semaphores, and exponential retry timestamps stored in `resolution_jobs`.

- [ ] **Step 4: Run tests**

Run: `python -m unittest tests.test_media_orchestrator tests.test_media_store tests.test_identity_service -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/douban_recommender/media/orchestrator.py tests/test_media_orchestrator.py
git commit -m "feat: add trusted media resolution jobs"
```

### Task 6: Local Media and V2 Media API Routes

**Files:**
- Create: `src/douban_recommender/media_api.py`
- Create: `tests/test_media_api.py`
- Modify: `src/douban_recommender/web.py:Handler.do_GET`
- Modify: `src/douban_recommender/web.py:Handler.do_POST`
- Modify: `src/douban_recommender/web.py:Handler.send_bytes`

**Interfaces:**
- Produces: `POST /api/v2/media/jobs`
- Produces: `GET /api/v2/media/jobs/<id>`
- Produces: `GET /api/v2/media/health`
- Produces: `GET /media/<asset-id>`

- [ ] **Step 1: Write route tests**

```python
def test_local_media_route_returns_immutable_asset(self):
    asset = self.seed_png_asset()
    status, headers, body = self.get_raw(f"/media/{asset.asset_id}.png")
    self.assertEqual(status, 200)
    self.assertEqual(headers["Cache-Control"], "public, max-age=31536000, immutable")
    self.assertTrue(body.startswith(b"\x89PNG"))

def test_media_job_payload_does_not_echo_cookie(self):
    response = self.post_json("/api/v2/media/jobs", {
        "kind": "portrait", "person_name": "婕斿憳鐢?, "cookie": "secret-cookie"
    })
    self.assertNotIn("secret-cookie", json.dumps(response, ensure_ascii=False))
```

- [ ] **Step 2: Run and verify 404 failures**

Run: `python -m unittest tests.test_media_api -v`

Expected: routes return 404.

- [ ] **Step 3: Implement route helpers and immutable headers**

`media_api.py` must translate request dictionaries into `AssetQuery` without retaining unknown fields. `web.py` must resolve asset paths through `MediaStore.path_for()` and never join a user-provided path directly.

```python
if path.startswith("/media/"):
    asset_id = safe_asset_id(path.removeprefix("/media/"))
    asset = media_store.lookup(asset_id)
    if not asset:
        self.send_json({"error": "media not found"}, status=404)
        return
    self.send_bytes(asset.path.read_bytes(), asset.mime_type, cache_control="public, max-age=31536000, immutable")
    return
```

- [ ] **Step 4: Run route and legacy API tests**

Run: `python -m unittest tests.test_media_api tests.test_web_api -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/douban_recommender/media_api.py src/douban_recommender/web.py tests/test_media_api.py
git commit -m "feat: serve verified local media assets"
```

### Task 7: Network Policy and Resumable V2 Sync Jobs

**Files:**
- Create: `src/douban_recommender/network_policy.py`
- Create: `src/douban_recommender/sync_service.py`
- Create: `src/douban_recommender/sync_api.py`
- Create: `tests/test_sync_service.py`
- Modify: `src/douban_recommender/crawler.py`
- Modify: `src/douban_recommender/web.py`

**Interfaces:**
- Produces: `DEFAULT_SYNC_SAFETY_CAP = 250`
- Produces: `normalize_douban_user(value: str) -> str`
- Produces: `detect_local_http_proxy(connect: Callable, ports=(7890, 7897, 10809)) -> str`
- Produces: `SyncService.start(payload: dict, cookie: str = "") -> str`
- Produces: `SyncService.status(job_id: str) -> dict`
- Produces: `SyncService.resume(job_id: str, cookie: str = "") -> str`
- Produces: `POST /api/v2/sync/jobs`, `GET /api/v2/sync/jobs/<id>`, and `POST /api/v2/sync/jobs/<id>/resume`

- [ ] **Step 1: Write user normalization, proxy, and safety-cap tests**

```python
def test_profile_url_normalizes_user_id():
    value = "https://www.douban.com/people/<your-douban-id>/"
    self.assertEqual(normalize_douban_user(value), "<your-douban-id>")

def test_proxy_detection_only_returns_local_http_endpoint():
    endpoint = detect_local_http_proxy(lambda port: port == 7897)
    self.assertEqual(endpoint, "http://127.0.0.1:7897")

def test_default_sync_cap_is_high_safety_valve():
    self.assertGreaterEqual(DEFAULT_SYNC_SAFETY_CAP, 250)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_sync_service -v`

Expected: missing network and sync modules.

- [ ] **Step 3: Implement strict local network policy**

```python
def normalize_douban_user(value):
    text = str(value or "").strip()
    match = re.search(r"douban\.com/people/([^/?#]+)", text)
    return (match.group(1) if match else text).strip("/ ")

def detect_local_http_proxy(connect, ports=(7890, 7897, 10809)):
    for port in ports:
        if connect(port):
            return f"http://127.0.0.1:{port}"
    return ""
```

Reject any configured proxy whose hostname is not loopback. Do not accept fields named `subscription`, `subscribe`, or URLs that are not local proxy endpoints.

- [ ] **Step 4: Implement resumable sync service**

Persist only job metadata, successful rows, failed page numbers, diagnostics, and stop reason. Keep `cookie` in the worker closure only.

```python
def start(self, payload, cookie=""):
    user_id = normalize_douban_user(payload.get("user") or payload.get("url"))
    job_id = uuid.uuid4().hex
    job = SyncJob(job_id, user_id, safety_cap=DEFAULT_SYNC_SAFETY_CAP)
    self.jobs.save(job.redacted_dict())
    self.executor.submit(self._run, job, normalize_cookie(cookie))
    return job_id
```

The crawler stops on empty pages, repeated pages, or authentication interception. A failed page is recorded and can be resumed without re-fetching successful pages.

- [ ] **Step 5: Add V2 routes and cookie redaction tests**

```python
def test_sync_response_never_echoes_cookie(self):
    response = self.post_json("/api/v2/sync/jobs", {
        "user": "<your-douban-id>", "cookie": "secret-cookie"
    })
    self.assertNotIn("secret-cookie", json.dumps(response, ensure_ascii=False))
```

Run: `python -m unittest tests.test_sync_service tests.test_web_api -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/douban_recommender/network_policy.py src/douban_recommender/sync_service.py src/douban_recommender/sync_api.py src/douban_recommender/crawler.py src/douban_recommender/web.py tests/test_sync_service.py
git commit -m "feat: add resumable privacy-safe douban sync"
```

### Task 8: Legacy Snapshot and Canonical Asset Migration

**Files:**
- Create: `src/douban_recommender/migrations.py`
- Create: `tests/test_migrations.py`
- Modify: `src/douban_recommender/database.py`

**Interfaces:**
- Produces: `migrate_legacy_recommendations(rows: list[dict], db: AppDatabase) -> MigrationReport`
- Produces: `MigrationReport(imported, dropped_placeholders, dropped_stale_assets, warnings)`

- [ ] **Step 1: Write stale-data migration tests**

```python
def test_migration_drops_numbered_placeholder_and_stale_premium_cover():
    rows = [
        {"title": "鐢靛奖鍊欓€?17", "source": "curated-placeholder"},
        {"title": "绀句氦缃戠粶", "cover": "https://img.doubanio.com/wrong.jpg", "source": "premium"},
    ]
    report = migrate_legacy_recommendations(rows, self.db)
    self.assertEqual(report.dropped_placeholders, 1)
    self.assertEqual(report.dropped_stale_assets, 1)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_migrations -v`

Expected: missing migration module.

- [ ] **Step 3: Implement idempotent migration**

Use a migration fingerprint stored in `schema_meta`. Never delete the original legacy snapshot. Import only non-sensitive metadata, and never read Cookie keys from legacy storage payloads.

- [ ] **Step 4: Run migration and existing snapshot tests**

Run: `python -m unittest tests.test_migrations tests.test_ui_html -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/douban_recommender/migrations.py src/douban_recommender/database.py tests/test_migrations.py
git commit -m "feat: migrate legacy recommendation metadata safely"
```

### Task 9: Foundation Integration Gate

**Files:**
- Modify: `README.md`
- Modify: `tests/test_readme.py`

**Interfaces:**
- Consumes all foundation interfaces.
- Produces documented data directory, cache clearing, local proxy ports, and media health API.

- [ ] **Step 1: Add failing documentation assertions**

```python
def test_readme_documents_local_media_and_cookie_boundary(self):
    text = Path("README.md").read_text(encoding="utf-8")
    self.assertIn("CINESCOPE_DATA_DIR", text)
    self.assertIn("/api/v2/media/health", text)
    self.assertIn("Cookie 鍙繚瀛樺湪 sessionStorage", text)
```

- [ ] **Step 2: Run documentation test**

Run: `python -m unittest tests.test_readme -v`

Expected: FAIL until README is updated.

- [ ] **Step 3: Document exact commands and privacy behavior**

Add PowerShell examples for `CINESCOPE_DATA_DIR` and `DOUBAN_RECOMMENDER_HTTP_PROXY=http://127.0.0.1:7890`. Explicitly state that subscription URLs are unsupported and should never be pasted.

- [ ] **Step 4: Run the complete foundation gate**

Run: `python -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 5: Run source hygiene checks**

Run: `git diff --check`

Expected: no output.

- [ ] **Step 6: Commit**

```powershell
git add README.md tests/test_readme.py
git commit -m "docs: explain trusted media runtime"
```
