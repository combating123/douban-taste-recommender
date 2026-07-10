from __future__ import annotations

import json
import urllib.request
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .intent_parser import RecommendationIntent, parse_recommendation_intent

DEFAULT_TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 64 * 1024
LOCAL_ENDPOINT_CANDIDATE = "http://127.0.0.1:11434/v1/chat/completions"
ALLOWED_EVIDENCE_FIELDS = (
    "title",
    "media_type",
    "year",
    "genres",
    "countries",
    "languages",
    "douban_rating",
)
TUPLE_FIELDS = {
    "media_types",
    "genres",
    "moods",
    "countries",
    "languages",
    "avoid",
    "session_only_adjustments",
    "permanent_avoid",
}
TEXT_FIELDS = {"pace", "complexity", "intensity_max", "free_text"}
INTEGER_FIELDS = {"runtime_max", "episode_runtime_max", "year_min", "year_max"}
NUMBER_FIELDS = {"quality_floor", "exploration_level", "surprise_level"}
KNOWN_INTENT_FIELDS = TUPLE_FIELDS | TEXT_FIELDS | INTEGER_FIELDS | NUMBER_FIELDS


class UngroundedResponseError(ValueError):
    pass


class LanguageAdapter:
    def parse(self, text: str, evidence_catalog) -> RecommendationIntent:
        raise NotImplementedError

    def explain(self, request, evidence_items) -> str:
        raise NotImplementedError


class LocalRuleLanguageAdapter(LanguageAdapter):
    def parse(self, text: str, evidence_catalog=None) -> RecommendationIntent:
        return parse_recommendation_intent(str(text or ""))

    def explain(self, request, evidence_items) -> str:
        catalog = _normalize_evidence(evidence_items)
        citation_ids = _requested_citations(request, catalog)
        if not citation_ids:
            citation_ids = list(catalog)[:2]
        if not citation_ids:
            return "暂无可引用证据。"
        fragments = [_local_fragment(citation_id, catalog[citation_id]) for citation_id in citation_ids[:2]]
        return "；".join(fragment for fragment in fragments if fragment) + "。"


class OpenAICompatibleLanguageAdapter(LanguageAdapter):
    def __init__(
        self,
        endpoint: str,
        model: str,
        api_key: str = "",
        *,
        transport=None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
    ):
        self.endpoint = str(endpoint or "").strip()
        self.model = str(model or "").strip()
        self.api_key = str(api_key or "")
        self.transport = transport or _default_transport
        self.timeout = int(timeout) if int(timeout) > 0 else DEFAULT_TIMEOUT_SECONDS
        self.max_response_bytes = int(max_response_bytes) if int(max_response_bytes) > 0 else MAX_RESPONSE_BYTES

    def parse(self, text: str, evidence_catalog) -> RecommendationIntent:
        payload = self._invoke(
            task="parse",
            content={"text": str(text or ""), "evidence": _compact_evidence(evidence_catalog)},
        )
        return _intent_from_payload(payload)

    def explain(self, request, evidence_items) -> str:
        normalized = _normalize_evidence(evidence_items)
        payload = self._invoke(
            task="explain",
            content={"request": _request_text(request), "evidence": _compact_evidence(normalized)},
        )
        return _grounded_text_from_payload(payload, normalized)

    def _invoke(self, *, task: str, content: dict[str, Any]) -> dict[str, Any]:
        endpoint = _validated_endpoint(self.endpoint)
        if not endpoint:
            raise RuntimeError("language endpoint is not configured")
        if not self.model:
            raise ValueError("model is required")
        body = json.dumps(
            {
                "model": self.model,
                "input": {"task": task, **content},
                "response_format": {"type": "json_object"},
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        try:
            response = self.transport(request, self.timeout)
            text = _read_response_text(response, self.max_response_bytes)
        except Exception as exc:  # pragma: no cover - exercised through tests
            raise RuntimeError("language model request failed") from exc
        return _json_object(text)


class LanguageService(LanguageAdapter):
    def __init__(self, primary: LanguageAdapter, fallback: LanguageAdapter):
        self.primary = primary
        self.fallback = fallback

    def parse(self, text: str, evidence_catalog) -> RecommendationIntent:
        try:
            intent = self.primary.parse(text, evidence_catalog)
            if not isinstance(intent, RecommendationIntent):
                raise ValueError("parse must return RecommendationIntent")
            return intent
        except Exception:
            return self.fallback.parse(text, evidence_catalog)

    def explain(self, request, evidence_items) -> str:
        try:
            text = self.primary.explain(request, evidence_items)
            if not isinstance(text, str) or not text.strip():
                raise ValueError("explain must return text")
            return text.strip()
        except Exception:
            return self.fallback.explain(request, evidence_items)


def detect_local_endpoint() -> str:
    return LOCAL_ENDPOINT_CANDIDATE


def _default_transport(request: urllib.request.Request, timeout: int):
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(MAX_RESPONSE_BYTES + 1)


def _validated_endpoint(endpoint: str) -> str:
    text = str(endpoint or "").strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError as exc:
        raise ValueError("endpoint is invalid") from exc
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("endpoint must use http or https")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("endpoint is invalid")
    host = parsed.hostname or ""
    if not host:
        raise ValueError("endpoint must include host")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("endpoint is invalid") from exc
    netloc = host
    if ":" in host and not host.startswith("["):
        netloc = f"[{host}]"
    if port:
        netloc = f"{netloc}:{port}"
    path = parsed.path or ""
    if not path or path == "/":
        path = "/v1/chat/completions"
    return urlunsplit((parsed.scheme, netloc, path, "", ""))


def _read_response_text(response, limit: int) -> str:
    if isinstance(response, str):
        data = response.encode("utf-8")
    elif isinstance(response, bytes):
        data = response
    elif hasattr(response, "read"):
        data = response.read(limit + 1)
    else:
        raise RuntimeError("unsupported transport response")
    if len(data) > limit:
        raise RuntimeError("language model response too large")
    return data.decode("utf-8")


def _json_object(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("model response must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("model response must be JSON object")
    return payload


def _intent_from_payload(payload: dict[str, Any]) -> RecommendationIntent:
    unknown = set(payload) - KNOWN_INTENT_FIELDS
    if unknown:
        raise ValueError("intent payload contains unknown field")
    clean: dict[str, Any] = {}
    for field, value in payload.items():
        if value is None:
            clean[field] = None
        elif field in TUPLE_FIELDS:
            clean[field] = _string_tuple(value, field)
        elif field in TEXT_FIELDS:
            if not isinstance(value, str):
                raise ValueError(f"{field} must be string")
            clean[field] = value.strip()
        elif field in INTEGER_FIELDS:
            if type(value) is not int:
                raise ValueError(f"{field} must be integer")
            clean[field] = value
        elif field in NUMBER_FIELDS:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{field} must be number")
            clean[field] = float(value) if field in {"quality_floor", "exploration_level", "surprise_level"} else value
    return RecommendationIntent.from_dict(clean)


def _grounded_text_from_payload(payload: dict[str, Any], evidence_items: dict[str, dict[str, Any]]) -> str:
    if set(payload) != {"text", "citations"}:
        raise ValueError("explanation payload must contain only text and citations")
    text = payload.get("text")
    citations = payload.get("citations")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be string")
    if not isinstance(citations, list):
        raise ValueError("citations must be array")
    citation_ids = [str(value).strip() for value in citations if isinstance(value, str)]
    if len(citation_ids) != len(citations) or not citation_ids:
        raise UngroundedResponseError("citation is required")
    for citation_id in citation_ids:
        if citation_id not in evidence_items:
            raise UngroundedResponseError("citation is not grounded")
    all_titles = {item_id: _title(evidence) for item_id, evidence in evidence_items.items() if _title(evidence)}
    cited_titles = {all_titles[item_id] for item_id in citation_ids if item_id in all_titles}
    if cited_titles and not any(title in text for title in cited_titles):
        raise UngroundedResponseError("citation title is not grounded")
    uncited_titles = {title for item_id, title in all_titles.items() if item_id not in citation_ids}
    if any(title in text for title in uncited_titles):
        raise UngroundedResponseError("citation title is not grounded")
    return text.strip()


def _requested_citations(request, evidence_items: dict[str, dict[str, Any]]) -> list[str]:
    if not isinstance(request, dict):
        return []
    raw = request.get("citations")
    if raw is None:
        raw = request.get("evidence_ids")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise UngroundedResponseError("citation is required")
    citation_ids: list[str] = []
    for value in raw:
        citation_id = str(value or "").strip()
        if not citation_id or citation_id not in evidence_items:
            raise UngroundedResponseError("citation is not grounded")
        if citation_id not in citation_ids:
            citation_ids.append(citation_id)
    return citation_ids


def _normalize_evidence(evidence_items) -> dict[str, dict[str, Any]]:
    if not isinstance(evidence_items, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for raw_id, item in evidence_items.items():
        item_id = str(raw_id or "").strip()
        if not item_id:
            continue
        normalized[item_id] = _compact_item_dict(item)
    return normalized


def _compact_evidence(evidence_items) -> list[dict[str, Any]]:
    normalized = _normalize_evidence(evidence_items)
    return [{"id": item_id, **item} for item_id, item in normalized.items()]


def _compact_item_dict(item) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for field in ALLOWED_EVIDENCE_FIELDS:
        value = _item_value(item, field)
        if value in (None, "", [], ()):  # keep payload compact
            continue
        if field in {"genres", "countries", "languages"}:
            compact[field] = _string_list(value)
        elif field == "year":
            if type(value) is int:
                compact[field] = value
        elif field == "douban_rating":
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                compact[field] = float(value)
        else:
            compact[field] = str(value).strip()
    return compact


def _item_value(item, field: str):
    if isinstance(item, dict):
        return item.get(field)
    return getattr(item, field, None)


def _string_list(value) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        return []
    out: list[str] = []
    for raw in values:
        text = str(raw or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _string_tuple(value, field: str) -> tuple[str, ...]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        raise ValueError(f"{field} must be string array")
    out: list[str] = []
    for item in values:
        if not isinstance(item, str):
            raise ValueError(f"{field} must be string array")
        text = item.strip()
        if text:
            out.append(text)
    return tuple(out)


def _request_text(request) -> str:
    if isinstance(request, str):
        return request
    if isinstance(request, dict):
        if isinstance(request.get("text"), str):
            return request["text"]
        if isinstance(request.get("request"), str):
            return request["request"]
    return str(request or "")


def _title(item: dict[str, Any]) -> str:
    return str(item.get("title") or "").strip()


def _local_fragment(citation_id: str, item: dict[str, Any]) -> str:
    title = _title(item) or citation_id
    facts: list[str] = []
    genres = item.get("genres") or []
    if isinstance(genres, list) and genres:
        facts.append("/".join(genres[:2]))
    year = item.get("year")
    if type(year) is int:
        facts.append(str(year))
    rating = item.get("douban_rating")
    if isinstance(rating, (int, float)) and not isinstance(rating, bool):
        facts.append(f"豆瓣{float(rating):g}")
    return f"推荐《{title}》" + (f"：{'、'.join(facts)}" if facts else "")


__all__ = [
    "LanguageAdapter",
    "LanguageService",
    "LocalRuleLanguageAdapter",
    "OpenAICompatibleLanguageAdapter",
    "UngroundedResponseError",
    "detect_local_endpoint",
]
