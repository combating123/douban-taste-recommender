from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class WorkIdentity:
    title: str
    original_titles: tuple[str, ...] = ()
    year: int | None = None
    media_type: str = ""
    countries: tuple[str, ...] = ()
    directors: tuple[str, ...] = ()
    casts: tuple[str, ...] = ()
    episode_count: int | None = None
    provider_ids: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PersonIdentity:
    name: str
    aliases: tuple[str, ...] = ()
    occupations: tuple[str, ...] = ()
    known_works: tuple[str, ...] = ()
    provider_ids: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MatchDecision:
    accepted: bool
    confidence: float
    reasons: tuple[str, ...]
    ambiguous: bool = False


def _normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    text = re.sub(r"\s*\(\d{4}\)\s*$", "", text)
    return "".join(character for character in text if character.isalnum())


def _normalized_values(values) -> set[str]:
    return {normalized for value in values for normalized in [_normalize_text(value)] if normalized}


def _work_titles(identity: WorkIdentity) -> set[str]:
    return _normalized_values((identity.title, *identity.original_titles))


def _person_names(identity: PersonIdentity) -> set[str]:
    return _normalized_values((identity.name, *identity.aliases))


def _canonical_media_type(value: str) -> str:
    normalized = _normalize_text(value)
    if normalized in {"电影", "movie", "film", "featurefilm"}:
        return "movie"
    if normalized in {"动漫", "动画", "anime", "animation", "animatedseries"}:
        return "anime"
    if normalized in {"电视剧", "剧集", "tv", "television", "series", "tvseries", "show"}:
        return "series"
    return normalized


def _media_types_compatible(expected: WorkIdentity, candidate: WorkIdentity) -> bool:
    expected_type = _canonical_media_type(expected.media_type)
    candidate_type = _canonical_media_type(candidate.media_type)
    if not expected_type or not candidate_type:
        return True
    if expected_type == candidate_type:
        return True
    animated_series_pair = {expected_type, candidate_type} == {"anime", "series"}
    if animated_series_pair and (expected.episode_count or candidate.episode_count):
        return True
    return False


def _shared_provider_id(left: Mapping[str, str], right: Mapping[str, str]) -> bool:
    for provider, identifier in (left or {}).items():
        clean_identifier = str(identifier or "").strip()
        if clean_identifier and clean_identifier == str((right or {}).get(provider) or "").strip():
            return True
    return False


def _overlap(left, right) -> bool:
    return bool(_normalized_values(left) & _normalized_values(right))


def match_work_identity(expected: WorkIdentity, candidate: WorkIdentity) -> MatchDecision:
    if _shared_provider_id(expected.provider_ids, candidate.provider_ids):
        return MatchDecision(True, 0.995, ("provider-id",), False)

    if not (_work_titles(expected) & _work_titles(candidate)):
        return MatchDecision(False, 0.0, ("title-conflict",), False)
    if not _media_types_compatible(expected, candidate):
        return MatchDecision(False, 0.1, ("media-type-conflict",), False)
    if expected.year and candidate.year and abs(int(expected.year) - int(candidate.year)) > 1:
        return MatchDecision(False, 0.2, ("year-conflict",), False)

    confidence = 0.64
    reasons = ["title"]
    confidence += 0.08
    reasons.append("media-type")

    if expected.year and candidate.year:
        confidence += 0.08
        reasons.append("year")
    if _overlap(expected.directors, candidate.directors):
        confidence += 0.12
        reasons.append("director")
    if _overlap(expected.countries, candidate.countries):
        confidence += 0.04
        reasons.append("country")
    if _overlap(expected.casts, candidate.casts):
        confidence += 0.05
        reasons.append("cast")
    if (
        expected.episode_count
        and candidate.episode_count
        and int(expected.episode_count) == int(candidate.episode_count)
    ):
        confidence += 0.04
        reasons.append("episode-count")

    confidence = min(confidence, 1.0)
    accepted = confidence >= 0.92
    return MatchDecision(accepted, confidence, tuple(reasons), not accepted)


OCCUPATION_ALIASES = {
    "director": "director",
    "导演": "director",
    "filmdirector": "director",
    "actor": "actor",
    "actress": "actor",
    "voiceactor": "actor",
    "voiceactress": "actor",
    "演员": "actor",
    "主演": "actor",
    "声优": "actor",
    "writer": "writer",
    "screenwriter": "writer",
    "编剧": "writer",
}


def _occupations(identity: PersonIdentity) -> set[str]:
    values: set[str] = set()
    for occupation in identity.occupations:
        normalized = _normalize_text(occupation)
        if normalized:
            values.add(OCCUPATION_ALIASES.get(normalized, normalized))
    return values


def match_person_identity(
    expected: PersonIdentity,
    candidate: PersonIdentity,
    work_context: set[str],
) -> MatchDecision:
    if _shared_provider_id(expected.provider_ids, candidate.provider_ids):
        return MatchDecision(True, 0.995, ("provider-id",), False)

    expected_names = _person_names(expected)
    candidate_names = _person_names(candidate)
    if not (expected_names & candidate_names):
        return MatchDecision(False, 0.0, ("name-conflict",), False)

    confidence = 0.52
    reasons = ["name-or-alias"]
    if _normalize_text(expected.name) != _normalize_text(candidate.name):
        confidence += 0.08
        reasons.append("alias")

    expected_occupations = _occupations(expected)
    candidate_occupations = _occupations(candidate)
    if expected_occupations and candidate_occupations and expected_occupations & candidate_occupations:
        confidence += 0.16
        reasons.append("occupation")

    expected_works = _normalized_values(expected.known_works)
    candidate_works = _normalized_values(candidate.known_works)
    context = _normalized_values(work_context)
    shared_works = expected_works & candidate_works
    contextual_works = shared_works & context if context else shared_works
    if contextual_works:
        confidence += 0.28 if context else 0.20
        reasons.append("work-context")

    confidence = min(confidence, 1.0)
    accepted = confidence >= 0.88
    return MatchDecision(accepted, confidence, tuple(reasons), not accepted)
