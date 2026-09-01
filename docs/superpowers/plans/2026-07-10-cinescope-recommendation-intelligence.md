# CineScope Recommendation Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a grounded Command Lens domain model, seven-layer ranking, independent channel batches, nuanced feedback, and persistent recommendation sessions without breaking the existing recommendation API.

**Architecture:** Existing `score_item()` remains the baseline quality/taste scorer and is wrapped by additive eligibility, context, calibration, diversity, and batch services. SQLite stores recommendation sessions and feedback events. `/api/v2/recommend/*` exposes the new model while `/api/recommend` remains compatible during migration.

**Tech Stack:** Python 3.10+, dataclasses, SQLite, standard-library JSON/HTTP, `unittest`.

## Global Constraints

- Local deterministic ranking is the source of truth.
- Optional language models may parse or phrase results but may not invent titles, people, ratings, or facts.
- Anime channel means animated series only.
- Costume series remain downranked unless the current intent opts in.
- Candidate pool size, matched size, and visible batch size are distinct values.
- Session-only feedback must not silently become a permanent taste preference.

---

### Task 1: Structured Command Lens Intent Parser

**Files:**
- Create: `src/douban_recommender/intent_parser.py`
- Create: `tests/test_intent_parser.py`

**Interfaces:**
- Produces: `RecommendationIntent`
- Produces: `IntentChip(key: str, label: str, value: object, removable: bool = True)`
- Produces: `parse_recommendation_intent(text: str, base: RecommendationIntent | None = None) -> RecommendationIntent`
- Produces: `intent_to_chips(intent: RecommendationIntent) -> list[IntentChip]`

- [ ] **Step 1: Write failing Chinese intent tests**

```python
def test_parses_anime_runtime_mood_and_avoidance():
    intent = parse_recommendation_intent(
        "浠婃櫄鎯崇湅鑱槑銆佹偓鐤戙€佺兢鍍忥紝浣嗕笉瑕佸お鍘嬫姂鐨勫姩鐢诲墽闆嗭紝鏈€濂戒竴闆?0鍒嗛挓浠ュ唴"
    )
    self.assertEqual(intent.media_types, ("鍔ㄦ极",))
    self.assertEqual(intent.episode_runtime_max, 30)
    self.assertIn("鎮枒", intent.genres)
    self.assertIn("缇ゅ儚", intent.moods)
    self.assertIn("杩囧害鍘嬫姂", intent.avoid)

def test_not_tonight_is_session_only():
    intent = parse_recommendation_intent("浠婃櫄涓嶆兂鐪嬫參鐑殑")
    self.assertIn("鎱㈢儹", intent.session_only_adjustments)
    self.assertNotIn("鎱㈢儹", intent.permanent_avoid)
```

- [ ] **Step 2: Run and confirm missing module**

Run: `python -m unittest tests.test_intent_parser -v`

Expected: import failure.

- [ ] **Step 3: Implement normalized dataclass and rule parser**

```python
@dataclass(frozen=True)
class RecommendationIntent:
    media_types: tuple[str, ...] = ()
    genres: tuple[str, ...] = ()
    moods: tuple[str, ...] = ()
    pace: str = ""
    complexity: str = ""
    intensity_max: str = ""
    runtime_max: int | None = None
    episode_runtime_max: int | None = None
    countries: tuple[str, ...] = ()
    year_min: int | None = None
    year_max: int | None = None
    quality_floor: float | None = None
    avoid: tuple[str, ...] = ()
    exploration_level: float = 0.35
    surprise_level: float = 0.20
    session_only_adjustments: tuple[str, ...] = ()
    permanent_avoid: tuple[str, ...] = ()
```

Implement ordered phrase dictionaries and regex extraction. Unknown words remain in `free_text` rather than being discarded.

- [ ] **Step 4: Run tests**

Run: `python -m unittest tests.test_intent_parser -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/douban_recommender/intent_parser.py tests/test_intent_parser.py
git commit -m "feat: parse grounded recommendation intents"
```

### Task 2: Eligibility and Media-Type Guards

**Files:**
- Create: `src/douban_recommender/eligibility.py`
- Create: `tests/test_eligibility.py`
- Modify: `src/douban_recommender/models.py`

**Interfaces:**
- Produces: `EligibilityDecision(eligible: bool, reasons: tuple[str, ...], penalties: tuple[ScoreSignal, ...])`
- Produces: `evaluate_eligibility(item: MediaItem, seen_keys: set[str], intent: RecommendationIntent) -> EligibilityDecision`
- Produces: `is_animated_series(item: MediaItem) -> bool`

- [ ] **Step 1: Write strict channel tests**

```python
def test_anime_movie_is_ineligible_for_anime_series_channel():
    item = MediaItem(title="鍗冧笌鍗冨", media_type="鍔ㄦ极", raw={"format": "MOVIE"})
    intent = RecommendationIntent(media_types=("鍔ㄦ极",))
    self.assertFalse(evaluate_eligibility(item, set(), intent).eligible)

def test_costume_series_is_penalized_not_removed_by_default():
    item = MediaItem(title="鍙よ娴嬭瘯", media_type="鐢佃鍓?, genres=["鍙よ"])
    decision = evaluate_eligibility(item, set(), RecommendationIntent(media_types=("鐢佃鍓?,)))
    self.assertTrue(decision.eligible)
    self.assertTrue(any(signal.code == "costume-series" and signal.value < 0 for signal in decision.penalties))
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_eligibility -v`

Expected: missing eligibility module.

- [ ] **Step 3: Implement canonical media metadata**

Add optional normalized fields to `MediaItem.raw` helpers rather than changing CSV compatibility. `is_animated_series()` accepts `TV`, `ONA`, `SERIES`, or a positive episode count and rejects `MOVIE`.

- [ ] **Step 4: Run eligibility and existing recommender tests**

Run: `python -m unittest tests.test_eligibility tests.test_recommender -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/douban_recommender/eligibility.py src/douban_recommender/models.py tests/test_eligibility.py
git commit -m "feat: enforce recommendation channel eligibility"
```

### Task 3: Seven-Layer Score Breakdown

**Files:**
- Create: `src/douban_recommender/ranking.py`
- Create: `tests/test_ranking.py`
- Modify: `src/douban_recommender/recommender.py`

**Interfaces:**
- Produces: `ScoreSignal(code, label, value, evidence)`
- Produces: `ScoreBreakdown(quality, taste, context, exploration, total, confidence, signals, conflicts)`
- Produces: `rank_candidates(rated, candidates, profile, intent, limit=None) -> list[Recommendation]`

- [ ] **Step 1: Write ranking behavior tests**

```python
def test_high_vote_quality_beats_tiny_vote_perfect_rating():
    stable = media("绋冲畾楂樺垎", rating=9.1, votes=200000)
    tiny = media("灏忔牱鏈弧鍒?, rating=9.8, votes=12)
    ranked = rank_candidates([], [tiny, stable], empty_profile(), RecommendationIntent())
    self.assertEqual(ranked[0].title, "绋冲畾楂樺垎")

def test_context_changes_current_order_without_mutating_profile():
    short = media("鐭墽", episode_runtime=24, rating=9.0)
    long = media("闀垮墽", episode_runtime=60, rating=9.2)
    intent = RecommendationIntent(episode_runtime_max=30)
    ranked = rank_candidates([], [long, short], empty_profile(), intent)
    self.assertEqual(ranked[0].title, "鐭墽")
```

- [ ] **Step 2: Run focused test and verify failure**

Run: `python -m unittest tests.test_ranking -v`

Expected: missing ranking module.

- [ ] **Step 3: Wrap existing score_item with calibrated layers**

```python
def rank_candidates(rated, candidates, profile, intent, limit=None):
    rows = []
    for item in candidates:
        eligibility = evaluate_eligibility(item, seen_item_keys(rated), intent)
        if not eligibility.eligible:
            continue
        baseline = score_item(item, profile)
        quality = calibrated_quality(item)
        taste = clamp(baseline.score, 0.0, 100.0)
        context, context_signals = context_score(item, intent)
        exploration = exploration_score(item, profile)
        total = 0.30 * quality + 0.35 * taste + 0.20 * context + 0.15 * exploration
        total += sum(signal.value for signal in eligibility.penalties)
        rows.append(with_breakdown(baseline, quality, taste, context, exploration, total, context_signals))
    return diversity_rerank(rows, limit or len(rows), lambda_value=0.72)
```

Preserve existing `recommend()` behavior by delegating to the new function with a neutral intent after regression tests prove parity within documented ordering tolerances.

- [ ] **Step 4: Run ranking and regression tests**

Run: `python -m unittest tests.test_ranking tests.test_recommender tests.test_web_api -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/douban_recommender/ranking.py src/douban_recommender/recommender.py tests/test_ranking.py
git commit -m "feat: add explainable seven-layer ranking"
```

### Task 4: Persistent Recommendation Sessions and Independent Batches

**Files:**
- Create: `src/douban_recommender/recommendation_service.py`
- Create: `tests/test_recommendation_service.py`
- Modify: `src/douban_recommender/database.py`

**Interfaces:**
- Produces: `RecommendationSessionService`
- Produces: `create_session(profile_key, intent, ranked_by_channel, batch_size_by_channel) -> RecommendationSession`
- Produces: `next_batch(session_id: str, channel: str, reason: str = "") -> RecommendationBatch`
- Produces: `previous_batch(session_id: str, channel: str) -> RecommendationBatch`
- Produces: `restore_session(session_id: str) -> RecommendationSession`

- [ ] **Step 1: Write independent-cursor tests**

```python
def test_movie_and_anime_batches_have_independent_cursors():
    session = service.create_session("p", neutral_intent(), pools(), {"鐢靛奖": 3, "鐢佃鍓?: 3, "鍔ㄦ极": 3})
    first_movie = service.next_batch(session.id, "鐢靛奖")
    first_anime = service.next_batch(session.id, "鍔ㄦ极")
    second_movie = service.next_batch(session.id, "鐢靛奖")
    self.assertEqual(first_anime.index, 1)
    self.assertEqual(second_movie.index, 2)
    self.assertFalse(set(first_movie.item_keys) & set(second_movie.item_keys))

def test_pool_match_and_visible_counts_are_distinct():
    batch = service.next_batch(seed_session(pool_size=160, matched_size=47, batch_size=9), "鍔ㄦ极")
    self.assertEqual((batch.pool_size, batch.matched_size, len(batch.items)), (160, 47, 9))
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_recommendation_service -v`

Expected: missing service.

- [ ] **Step 3: Implement versioned sessions and batch history**

Store ranked item snapshots and per-channel cursors in SQLite JSON. Batch generation must be transactional, append a history row, and only reset after the channel pool is exhausted. `reason` modifies session-only weights before selecting the next batch.

- [ ] **Step 4: Run tests**

Run: `python -m unittest tests.test_recommendation_service tests.test_database -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/douban_recommender/recommendation_service.py src/douban_recommender/database.py tests/test_recommendation_service.py
git commit -m "feat: persist independent recommendation batches"
```

### Task 5: Nuanced Feedback and Taste Drift

**Files:**
- Create: `src/douban_recommender/feedback_service.py`
- Create: `tests/test_feedback_service.py`
- Modify: `src/douban_recommender/profiler.py`

**Interfaces:**
- Produces: `FeedbackEvent(event_type, item_key, session_id, payload, created_at)`
- Produces: `record_feedback(event: FeedbackEvent) -> str`
- Produces: `undo_feedback(event_id: str) -> None`
- Produces: `feedback_signals(profile_key: str, at: datetime) -> FeedbackSignals`

- [ ] **Step 1: Write scope and undo tests**

```python
def test_not_tonight_does_not_change_permanent_profile():
    event_id = service.record_feedback(event("not-tonight", session_id="s1"))
    signals = service.feedback_signals("p1", now())
    self.assertEqual(signals.permanent_negative, ())
    self.assertTrue(signals.session_adjustments["s1"])

def test_undo_removes_feedback_effect():
    event_id = service.record_feedback(event("less-like-this", payload={"pace": "slow"}))
    service.undo_feedback(event_id)
    self.assertNotIn("slow", service.feedback_signals("p1", now()).weak_negative)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_feedback_service -v`

Expected: missing feedback module.

- [ ] **Step 3: Implement append-only feedback with reversible tombstones**

Never delete the original event. `undo_feedback()` writes a linked `undo` event. `profiler.py` consumes only active permanent events and computes recent 30/90-day drift separately from stable signals.

- [ ] **Step 4: Run profiler and feedback tests**

Run: `python -m unittest tests.test_feedback_service tests.test_recommender -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/douban_recommender/feedback_service.py src/douban_recommender/profiler.py tests/test_feedback_service.py
git commit -m "feat: add reversible contextual feedback"
```

### Task 6: V2 Recommendation and Feedback APIs

**Files:**
- Create: `src/douban_recommender/recommendation_api.py`
- Create: `tests/test_recommendation_api_v2.py`
- Modify: `src/douban_recommender/web.py:Handler.do_GET`
- Modify: `src/douban_recommender/web.py:Handler.do_POST`

**Interfaces:**
- Produces: `POST /api/v2/recommend/sessions`
- Produces: `GET /api/v2/recommend/sessions/<id>`
- Produces: `POST /api/v2/recommend/sessions/<id>/batch`
- Produces: `POST /api/v2/recommend/sessions/<id>/previous`
- Produces: `POST /api/v2/feedback`
- Produces: `POST /api/v2/feedback/<id>/undo`

- [ ] **Step 1: Write API contract tests**

```python
def test_create_session_returns_three_distinct_counts():
    response = self.post_json("/api/v2/recommend/sessions", session_payload(limit=160))
    anime = response["channels"]["鍔ㄦ极"]
    self.assertIn("pool_size", anime)
    self.assertIn("matched_size", anime)
    self.assertIn("visible_size", anime)

def test_feedback_api_does_not_accept_unknown_permanent_scope():
    status, payload = self.post_json_status("/api/v2/feedback", {
        "event_type": "not-tonight", "scope": "permanent", "item_key": "x"
    })
    self.assertEqual(status, 400)
```

- [ ] **Step 2: Run and verify 404 failures**

Run: `python -m unittest tests.test_recommendation_api_v2 -v`

Expected: 404.

- [ ] **Step 3: Implement schema validation and routing**

Reject unknown event types and invalid scope combinations. Return `schema_version: 2`, stable channel keys, score breakdowns, short reason, conflicts, media status, and restore metadata.

- [ ] **Step 4: Run V2 and legacy API tests**

Run: `python -m unittest tests.test_recommendation_api_v2 tests.test_web_api -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/douban_recommender/recommendation_api.py src/douban_recommender/web.py tests/test_recommendation_api_v2.py
git commit -m "feat: expose recommendation session api"
```

### Task 7: Title, Person, Library, Taste, and Universe Query APIs

**Files:**
- Create: `src/douban_recommender/exploration_service.py`
- Create: `src/douban_recommender/catalog_api.py`
- Create: `tests/test_catalog_api_v2.py`
- Modify: `src/douban_recommender/web.py`

**Interfaces:**
- Produces: `GET /api/v2/titles/<id>`
- Produces: `GET /api/v2/people/<id>`
- Produces: `GET /api/v2/library?state=<state>&cursor=<cursor>`
- Produces: `GET /api/v2/taste`
- Produces: `GET /api/v2/universe?focus=<id>&limit=<n>`
- Produces: `build_universe_graph(focus_id: str, limit: int = 9) -> dict`

- [ ] **Step 1: Write query contract tests**

```python
def test_title_detail_returns_separate_poster_backdrop_and_people_assets():
    payload = self.get_json("/api/v2/titles/title-1")
    self.assertIn("poster", payload)
    self.assertIn("backdrop", payload)
    self.assertIn("people", payload)
    self.assertTrue(all("media_status" in person for person in payload["people"]))

def test_universe_is_bounded_and_edges_are_explained():
    payload = self.get_json("/api/v2/universe?focus=title-1&limit=9")
    self.assertLessEqual(len(payload["nodes"]), 9)
    self.assertTrue(all(edge.get("reason") for edge in payload["edges"]))
```

- [ ] **Step 2: Run and verify 404 failures**

Run: `python -m unittest tests.test_catalog_api_v2 -v`

Expected: routes return 404.

- [ ] **Step 3: Implement bounded query services**

```python
def build_universe_graph(self, focus_id, limit=9):
    limit = max(3, min(int(limit), 25))
    focus = self.repository.require_title(focus_id)
    candidates = self.repository.related_titles(focus, limit=limit * 4)
    ranked = sorted(candidates, key=lambda row: row.relationship_score, reverse=True)[: limit - 1]
    return {
        "nodes": [serialize_node(focus), *[serialize_node(row.title) for row in ranked]],
        "edges": [serialize_edge(focus, row.title, row.reasons) for row in ranked],
    }
```

Title and person payloads must contain only local media URLs or explicit designed-fallback status. Library uses cursor pagination. Taste returns stable, conflicting, recent, negative, and unexplored signal groups with evidence item IDs.

- [ ] **Step 4: Run API and service tests**

Run: `python -m unittest tests.test_catalog_api_v2 tests.test_recommendation_api_v2 tests.test_media_api -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/douban_recommender/exploration_service.py src/douban_recommender/catalog_api.py src/douban_recommender/web.py tests/test_catalog_api_v2.py
git commit -m "feat: expose cinescope catalog exploration api"
```

### Task 8: Optional Grounded Language Adapter

**Files:**
- Create: `src/douban_recommender/language_adapter.py`
- Create: `tests/test_language_adapter.py`

**Interfaces:**
- Produces: `LanguageAdapter.parse(text, evidence_catalog) -> RecommendationIntent`
- Produces: `LanguageAdapter.explain(request, evidence_items) -> str`
- Produces: `LocalRuleLanguageAdapter`
- Produces: `OpenAICompatibleLanguageAdapter(endpoint, model, api_key="")`

- [ ] **Step 1: Write grounding and fallback tests**

```python
def test_explanation_rejects_unknown_title_from_model():
    adapter = fake_model_adapter('{"text":"鎺ㄨ崘涓嶅瓨鍦ㄧ殑鐢靛奖","citations":["missing"]}')
    with self.assertRaisesRegex(UngroundedResponseError, "citation"):
        adapter.explain("鍙暀涓€閮?, {"known": known_item()})

def test_model_failure_falls_back_to_local_rules():
    service = LanguageService(primary=FailingAdapter(), fallback=LocalRuleLanguageAdapter())
    self.assertEqual(service.parse("涓嶈鍙よ鍓?).avoid, ("鍙よ",))
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_language_adapter -v`

Expected: missing module.

- [ ] **Step 3: Implement strict JSON citation contract**

The compatible adapter sends only compact evidence IDs and validates every returned citation. It may auto-detect `http://127.0.0.1:11434` but must not make a remote call unless explicitly configured.

- [ ] **Step 4: Run tests**

Run: `python -m unittest tests.test_language_adapter tests.test_intent_parser -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/douban_recommender/language_adapter.py tests/test_language_adapter.py
git commit -m "feat: add optional grounded language adapter"
```

### Task 9: Recommendation Intelligence Integration Gate

**Files:**
- Modify: `README.md`
- Modify: `tests/test_readme.py`

**Interfaces:**
- Documents Command Lens, count semantics, feedback scope, and optional local model endpoint.

- [ ] **Step 1: Add failing README assertions**

```python
def test_readme_explains_candidate_and_batch_counts():
    text = Path("README.md").read_text(encoding="utf-8")
    self.assertIn("鍊欓€夋睜", text)
    self.assertIn("鏉′欢鍛戒腑", text)
    self.assertIn("褰撳墠鎵规", text)
```

- [ ] **Step 2: Update documentation and run focused tests**

Run: `python -m unittest tests.test_readme tests.test_recommendation_api_v2 -v`

Expected: PASS.

- [ ] **Step 3: Run the complete suite**

Run: `python -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 4: Check formatting and secrets**

Run: `git diff --check; rg -n "Cookie.*(print|log)|api_key.*response" src tests`

Expected: no secret-logging implementation.

- [ ] **Step 5: Commit**

```powershell
git add README.md tests/test_readme.py
git commit -m "docs: explain cinescope recommendation sessions"
```
