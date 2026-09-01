from __future__ import annotations

from urllib.parse import urlsplit

from ...identity_service import PersonIdentity, WorkIdentity
from ..url_candidates import is_placeholder_image_url
from .base import AssetCandidate, AssetQuery


class InlineProvider:
    name = "inline"

    def search(self, query: AssetQuery) -> list[AssetCandidate]:
        urls = _source_urls(query.source_urls)
        if not urls:
            return []
        if query.kind == "portrait":
            if not query.person_name:
                return []
            identity = PersonIdentity(
                name=query.person_name,
                aliases=tuple(query.aliases),
                occupations=tuple(query.occupations),
                known_works=tuple(query.work_context),
                provider_ids=dict(query.provider_ids),
            )
            return [
                AssetCandidate(
                    url=url,
                    source=self.name,
                    kind="portrait",
                    person_identity=identity,
                    declared_type=_declared_type(url),
                    metadata={"embedded": True, "source_index": index},
                )
                for index, url in enumerate(urls)
            ]
        if query.kind not in {"poster", "backdrop"} or not query.title:
            return []
        identity = WorkIdentity(
            title=query.title,
            original_titles=tuple(query.original_titles),
            year=query.year,
            media_type=query.media_type,
            countries=tuple(query.countries),
            directors=tuple(query.directors),
            casts=tuple(query.casts),
            episode_count=query.episode_count,
            provider_ids=dict(query.provider_ids),
        )
        return [
            AssetCandidate(
                url=url,
                source=self.name,
                kind=query.kind,
                work_identity=identity,
                declared_type=_declared_type(url),
                metadata={"embedded": True, "source_index": index},
            )
            for index, url in enumerate(urls)
        ]


def _source_urls(values: tuple[str, ...]) -> tuple[str, ...]:
    urls: list[str] = []
    for value in values:
        text = str(value or "").strip()
        try:
            parsed = urlsplit(text)
        except ValueError:
            continue
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname or text in urls:
            continue
        if is_placeholder_image_url(text):
            continue
        urls.append(text)
    return tuple(urls)


def _declared_type(url: str) -> str:
    lower = str(url or "").lower().split("?", 1)[0]
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    return ""
