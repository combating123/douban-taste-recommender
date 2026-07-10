import unittest

from douban_recommender.identity_service import (
    PersonIdentity,
    WorkIdentity,
    match_person_identity,
    match_work_identity,
)


class WorkIdentityTests(unittest.TestCase):
    def test_same_title_wrong_year_is_rejected(self):
        expected = WorkIdentity(
            title="英雄",
            year=2002,
            media_type="电影",
            countries=("中国大陆",),
            directors=("张艺谋",),
        )
        candidate = WorkIdentity(
            title="英雄",
            year=1997,
            media_type="电影",
            countries=("香港",),
        )
        decision = match_work_identity(expected, candidate)
        self.assertFalse(decision.accepted)
        self.assertIn("year-conflict", decision.reasons)

    def test_same_title_wrong_media_type_is_rejected(self):
        expected = WorkIdentity(title="三体", year=2023, media_type="电视剧")
        candidate = WorkIdentity(title="三体", year=2023, media_type="电影")
        decision = match_work_identity(expected, candidate)
        self.assertFalse(decision.accepted)
        self.assertIn("media-type-conflict", decision.reasons)

    def test_original_and_local_title_with_year_country_director_is_accepted(self):
        expected = WorkIdentity(
            title="奇巧计程车",
            original_titles=("ODDTAXI",),
            year=2021,
            media_type="动漫",
            countries=("日本",),
            directors=("木下麦",),
            episode_count=13,
        )
        candidate = WorkIdentity(
            title="ODDTAXI",
            original_titles=("奇巧计程车",),
            year=2021,
            media_type="TV",
            countries=("日本",),
            directors=("木下麦",),
            episode_count=13,
        )
        decision = match_work_identity(expected, candidate)
        self.assertTrue(decision.accepted)
        self.assertGreaterEqual(decision.confidence, 0.92)

    def test_ambiguous_title_without_secondary_evidence_is_not_accepted(self):
        expected = WorkIdentity(title="人生", year=None, media_type="电影")
        candidate = WorkIdentity(title="人生", year=None, media_type="电影")
        decision = match_work_identity(expected, candidate)
        self.assertFalse(decision.accepted)
        self.assertTrue(decision.ambiguous)


class PersonIdentityTests(unittest.TestCase):
    def test_same_name_person_requires_role_or_work_context(self):
        expected = PersonIdentity(
            name="王伟",
            occupations=("导演",),
            known_works=("作品甲",),
        )
        wrong = PersonIdentity(
            name="王伟",
            occupations=("演员",),
            known_works=("作品乙",),
        )
        decision = match_person_identity(expected, wrong, {"作品甲"})
        self.assertFalse(decision.accepted)
        self.assertTrue(decision.ambiguous)

    def test_alias_role_and_shared_work_context_is_accepted(self):
        expected = PersonIdentity(
            name="宫崎骏",
            aliases=("Hayao Miyazaki",),
            occupations=("导演",),
            known_works=("千与千寻",),
        )
        candidate = PersonIdentity(
            name="Hayao Miyazaki",
            aliases=("宫崎骏",),
            occupations=("Director",),
            known_works=("千与千寻", "龙猫"),
        )
        decision = match_person_identity(expected, candidate, {"千与千寻"})
        self.assertTrue(decision.accepted)
        self.assertGreaterEqual(decision.confidence, 0.88)

    def test_shared_provider_id_is_strong_identity_evidence(self):
        expected = PersonIdentity(name="演员甲", provider_ids={"tmdb": "123"})
        candidate = PersonIdentity(name="Actor A", provider_ids={"tmdb": "123"})
        decision = match_person_identity(expected, candidate, set())
        self.assertTrue(decision.accepted)
        self.assertGreaterEqual(decision.confidence, 0.99)


if __name__ == "__main__":
    unittest.main()
