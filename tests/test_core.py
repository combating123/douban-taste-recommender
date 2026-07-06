from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from douban_recommender.io import load_media_csv
from douban_recommender.profiler import build_taste_profile
from douban_recommender.recommender import recommend


def test_sample_recommendations():
    rated = load_media_csv(ROOT / "sample_data" / "ratings_sample.csv", kind="ratings")
    candidates = load_media_csv(ROOT / "sample_data" / "candidates_sample.csv", kind="candidates")
    profile = build_taste_profile(rated, like_terms="悬疑,犯罪,现实主义", dislike_terms="甜宠,狗血")
    recs = recommend(rated, candidates, profile, limit=5)
    assert recs
    titles = [r.item.title for r in recs]
    assert "隐秘的角落" in titles or "坠落的审判" in titles
    assert all(r.score > 0 for r in recs)
