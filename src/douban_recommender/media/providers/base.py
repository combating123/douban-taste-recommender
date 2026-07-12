from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol

from ...identity_service import PersonIdentity, WorkIdentity


@dataclass(frozen=True)
class AssetQuery:
    kind: str
    title: str = ""
    original_titles: tuple[str, ...] = ()
    year: int | None = None
    media_type: str = ""
    countries: tuple[str, ...] = ()
    directors: tuple[str, ...] = ()
    casts: tuple[str, ...] = ()
    episode_count: int | None = None
    person_name: str = ""
    aliases: tuple[str, ...] = ()
    occupations: tuple[str, ...] = ()
    work_context: tuple[str, ...] = ()
    source_urls: tuple[str, ...] = ()
    provider_ids: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AssetCandidate:
    url: str
    source: str
    kind: str
    work_identity: WorkIdentity | None = None
    person_identity: PersonIdentity | None = None
    declared_type: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)


class MediaProvider(Protocol):
    name: str

    def search(self, query: AssetQuery) -> list[AssetCandidate]: ...
