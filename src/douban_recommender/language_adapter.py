from __future__ import annotations

import json
import re
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
JSON_ONLY_SYSTEM_PROMPT = "Return one strict JSON object only. Do not include markdown or extra text."
STRICT_EXPLANATION_TEMPLATE = (
    "For task='explain', the JSON field 'text' must follow this strict template only: "
    "one or more segments separated by '；' or ';'. "
    "Each citation must correspond to one segment and every cited title must appear exactly once. "
    "Each segment must be '推荐《已引用标题》' optionally followed, in this order, by "
    "'于YYYY年上映/播出/开播', '，豆瓣评分X', '，类型：...', '，国家/地区：...', '，语言：...'. "
    "Use only cited titles and cited fact values. No extra commentary, no unlabeled facts, "
    "no unknown titles, and no extra segments. "
    "每个 citation 必须对应一个 segment；segment 只能是 `推荐《已引用标题》`，"
    "后面按固定语法追加可选字段：`于YYYY年上映/播出/开播`、`，豆瓣评分X`、`，类型：...`、"
    "`，国家/地区：...`、`，语言：...`；不得输出任何额外自由描述。"
)
TITLE_PATTERN = re.compile(r"《(?P<title>[^》]+)》")
SEGMENT_SPLIT_PATTERN = re.compile(r"\s*[；;]\s*")
SEGMENT_TITLE_PATTERN = re.compile(r"^推荐《(?P<title>[^》]+)》")
SEGMENT_YEAR_PATTERN = re.compile(r"^(?:\s*[，,]\s*)?于(?P<year>\d{4})年(?P<label>上映|播出|开播)")
SEGMENT_RATING_PATTERN = re.compile(r"^\s*[，,]\s*豆瓣评分\s*(?P<rating>\d+(?:\.\d+)?)")
SEGMENT_GENRES_PATTERN = re.compile(r"^\s*[，,]\s*类型\s*[:：]\s*(?P<genres>[^，。；;!！?？]+)")
SEGMENT_COUNTRIES_PATTERN = re.compile(r"^\s*[，,]\s*国家/地区\s*[:：]\s*(?P<countries>[^，。；;!！?？]+)")
SEGMENT_LANGUAGES_PATTERN = re.compile(r"^\s*[，,]\s*语言\s*[:：]\s*(?P<languages>[^，。；;!！?？]+)")
LIST_SPLIT_PATTERN = re.compile(r"(?:\s*[、/,，]\s*)|(?:\s+and\s+)")


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
        if citation_ids is None:
            citation_ids = list(catalog)[:2]
        if not citation_ids:
            return "\u6682\u65e0\u53ef\u5f15\u7528\u8bc1\u636e\u3002"
        fragments = [_local_fragment(citation_id, catalog[citation_id]) for citation_id in citation_ids[:2]]
        return "\uff1b".join(fragment for fragment in fragments if fragment) + "\u3002"


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
        self._uses_default_transport = transport is None
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
        protocol = _endpoint_protocol(endpoint)
        body = _request_body(protocol, self.model, task, content)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        try:
            if self._uses_default_transport:
                response = self.transport(request, self.timeout, self.max_response_bytes)
            else:
                response = self.transport(request, self.timeout)
        except Exception as exc:  # pragma: no cover - exercised through tests
            raise RuntimeError("language model request failed") from exc
        return _decode_model_payload(response, self.max_response_bytes, protocol)


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


def _default_transport(request: urllib.request.Request, timeout: int, limit: int):
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(limit + 1)


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


def _endpoint_protocol(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    return "responses" if parsed.path == "/v1/responses" else "chat"


def _system_prompt(task: str) -> str:
    return f"{JSON_ONLY_SYSTEM_PROMPT} {STRICT_EXPLANATION_TEMPLATE}" if task == "explain" else JSON_ONLY_SYSTEM_PROMPT


def _request_body(protocol: str, model: str, task: str, content: dict[str, Any]) -> bytes:
    prompt = _system_prompt(task)
    if protocol == "responses":
        payload = {
            "model": model,
            "instructions": prompt,
            "input": json.dumps(
                {"task": task, **content},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "text": {"format": {"type": "json_object"}},
        }
    else:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"task": task, **content},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
        }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _decode_model_payload(response, limit: int, protocol: str) -> dict[str, Any]:
    payload = _response_object(response, limit)
    if _looks_like_final_payload(payload):
        return payload
    if protocol == "responses":
        return _responses_payload(payload, limit)
    return _chat_payload(payload, limit)


def _response_object(response, limit: int) -> dict[str, Any]:
    if isinstance(response, dict):
        _ensure_payload_size(response, limit)
        return response
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
    return _json_object(data.decode("utf-8"))


def _ensure_payload_size(payload: dict[str, Any], limit: int) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > limit:
        raise RuntimeError("language model response too large")


def _looks_like_final_payload(payload: dict[str, Any]) -> bool:
    keys = set(payload)
    if "choices" in payload or "output" in payload or "output_text" in payload:
        return False
    if {"text", "citations"}.issubset(keys):
        return True
    return keys <= KNOWN_INTENT_FIELDS


def _chat_payload(payload: dict[str, Any], limit: int) -> dict[str, Any]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("chat response must include choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("chat response must include choices")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError("chat response must include message")
    return _coerce_json_output(message.get("content"), limit, "chat response content")


def _responses_payload(payload: dict[str, Any], limit: int) -> dict[str, Any]:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return _coerce_json_output(output_text, limit, "responses output_text")
    output = payload.get("output")
    if not isinstance(output, list) or not output:
        raise ValueError("responses response must include output_text or output")
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "output_text" and isinstance(block.get("text"), str) and block["text"].strip():
                return _coerce_json_output(block["text"], limit, "responses output")
    raise ValueError("responses response must include output_text or output")


def _coerce_json_output(value: Any, limit: int, label: str) -> dict[str, Any]:
    if isinstance(value, dict):
        _ensure_payload_size(value, limit)
        return value
    if isinstance(value, list):
        parts = []
        for block in value:
            if isinstance(block, dict) and block.get("type") in {"text", "output_text"} and isinstance(block.get("text"), str):
                parts.append(block["text"])
        if parts:
            value = "".join(parts)
    if not isinstance(value, str):
        raise ValueError(f"{label} must be JSON string")
    if len(value.encode("utf-8")) > limit:
        raise RuntimeError("language model response too large")
    return _json_object(value)


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
    _validate_grounded_claims(text, citation_ids, evidence_items)
    return text.strip()


def _validate_grounded_claims(text: str, citation_ids: list[str], evidence_items: dict[str, dict[str, Any]]) -> None:
    segments = _split_explanation_segments(text)
    if len(segments) != len(citation_ids):
        raise UngroundedResponseError("citation title is not grounded")
    cited_titles = _cited_title_map(citation_ids, evidence_items)
    seen_citations: set[str] = set()
    for segment in segments:
        citation_id, claims = _parse_explanation_segment(segment, cited_titles)
        if citation_id in seen_citations:
            raise UngroundedResponseError("citation title is not grounded")
        _validate_segment_claims(claims, evidence_items[citation_id])
        seen_citations.add(citation_id)
    if seen_citations != set(citation_ids):
        raise UngroundedResponseError("citation title is not grounded")


def _split_explanation_segments(text: str) -> list[str]:
    stripped = str(text or "").strip()
    stripped = re.sub(r"[\s\u3002.!\uff01?\uff1f]+$", "", stripped)
    if not stripped:
        raise UngroundedResponseError("citation title is not grounded")
    segments = [segment.strip() for segment in SEGMENT_SPLIT_PATTERN.split(stripped)]
    if not segments or any(not segment for segment in segments):
        raise UngroundedResponseError("citation title is not grounded")
    return segments


def _cited_title_map(citation_ids: list[str], evidence_items: dict[str, dict[str, Any]]) -> dict[str, str]:
    title_to_citation: dict[str, str] = {}
    for citation_id in citation_ids:
        title = _title(evidence_items[citation_id])
        if not title:
            raise UngroundedResponseError("citation title is not grounded")
        if title in title_to_citation and title_to_citation[title] != citation_id:
            raise UngroundedResponseError("citation title is not grounded")
        title_to_citation[title] = citation_id
    return title_to_citation


def _parse_explanation_segment(segment: str, cited_titles: dict[str, str]) -> tuple[str, dict[str, Any]]:
    match = SEGMENT_TITLE_PATTERN.match(segment.strip())
    if not match:
        raise UngroundedResponseError("explicit fact is not grounded")
    title = match.group("title").strip()
    citation_id = cited_titles.get(title)
    if not citation_id:
        raise UngroundedResponseError("citation title is not grounded")
    cursor = match.end()
    claims: dict[str, Any] = {}
    for field, pattern, group_name, coerce in (
        ("year", SEGMENT_YEAR_PATTERN, "year", lambda value: int(value)),
        ("douban_rating", SEGMENT_RATING_PATTERN, "rating", lambda value: float(value)),
        ("genres", SEGMENT_GENRES_PATTERN, "genres", _split_claim_values),
        ("countries", SEGMENT_COUNTRIES_PATTERN, "countries", _split_claim_values),
        ("languages", SEGMENT_LANGUAGES_PATTERN, "languages", _split_claim_values),
    ):
        value, cursor = _consume_segment_fact(segment, cursor, pattern, group_name, coerce)
        if value in (None, []):
            continue
        claims[field] = value
    if segment[cursor:].strip():
        raise UngroundedResponseError("explicit fact is not grounded")
    return citation_id, claims


def _consume_segment_fact(segment: str, cursor: int, pattern: re.Pattern[str], group_name: str, coerce) -> tuple[Any, int]:
    match = pattern.match(segment[cursor:])
    if not match:
        return None, cursor
    value = coerce(match.group(group_name).strip())
    return value, cursor + match.end()


def _validate_segment_claims(claims: dict[str, Any], evidence_item: dict[str, Any]) -> None:
    if "year" in claims and claims["year"] != evidence_item.get("year"):
        raise UngroundedResponseError("explicit fact is not grounded")
    if "douban_rating" in claims and _normalize_number(claims["douban_rating"]) != _normalize_number(evidence_item.get("douban_rating")):
        raise UngroundedResponseError("explicit fact is not grounded")
    for field in ("genres", "countries", "languages"):
        if field not in claims:
            continue
        supported = set(_string_list(evidence_item.get(field)))
        if not supported or any(value not in supported for value in claims[field]):
            raise UngroundedResponseError("explicit fact is not grounded")


def _split_claim_values(value: str) -> list[str]:
    items = [item.strip() for item in LIST_SPLIT_PATTERN.split(value) if item and item.strip()]
    out: list[str] = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def _normalize_number(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return ""
    return f"{float(value):g}"


def _requested_citations(request, evidence_items: dict[str, dict[str, Any]]) -> list[str] | None:
    if not isinstance(request, dict):
        return None
    raw = request.get("citations")
    if raw is None:
        raw = request.get("evidence_ids")
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
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
        facts.append(f"\u8c46\u74e3{float(rating):g}")
    return f"\u63a8\u8350\u300a{title}\u300b" + (f"\uff1a{'\u3001'.join(facts)}" if facts else "")


__all__ = [
    "LanguageAdapter",
    "LanguageService",
    "LocalRuleLanguageAdapter",
    "OpenAICompatibleLanguageAdapter",
    "UngroundedResponseError",
    "detect_local_endpoint",
]
