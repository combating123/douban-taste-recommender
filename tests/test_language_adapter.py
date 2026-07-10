import json
import unittest
from unittest.mock import patch

from douban_recommender.intent_parser import parse_recommendation_intent
from douban_recommender.language_adapter import (
    LanguageService,
    LocalRuleLanguageAdapter,
    OpenAICompatibleLanguageAdapter,
    UngroundedResponseError,
    detect_local_endpoint,
)


class RecordingTransport:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.calls = []

    def __call__(self, request, timeout):
        body = request.data.decode("utf-8") if request.data else ""
        self.calls.append(
            {
                "url": request.full_url,
                "headers": dict(request.header_items()),
                "body": body,
                "timeout": timeout,
            }
        )
        if self.error is not None:
            raise self.error
        return self.payload.encode("utf-8") if isinstance(self.payload, str) else self.payload


class FakeUrlopenResponse:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.read_sizes = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size=-1):
        self.read_sizes.append(size)
        if size is None or size < 0:
            return self.payload
        return self.payload[:size]


class LanguageAdapterTests(unittest.TestCase):
    def test_openai_adapter_without_endpoint_does_not_call_transport(self):
        transport = RecordingTransport(payload='{"genres": ["\u60ac\u7591"]}')
        service = LanguageService(
            primary=OpenAICompatibleLanguageAdapter(endpoint="", model="demo", transport=transport),
            fallback=LocalRuleLanguageAdapter(),
        )

        intent = service.parse("\u4e0d\u8981\u53e4\u88c5\u5267", {"ev1": {"title": "\u793a\u4f8b", "cookie": "secret"}})

        self.assertEqual(transport.calls, [])
        self.assertEqual(intent, parse_recommendation_intent("\u4e0d\u8981\u53e4\u88c5\u5267"))

    def test_openai_adapter_chat_endpoint_uses_chat_envelope_and_compact_evidence(self):
        transport = RecordingTransport(
            payload=json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": '{"text":"\u63a8\u8350\u300a\u771f\u5b9e\u6807\u9898\u300b\u4e8e2014\u5e74\u4e0a\u6620\uff0c\u8c46\u74e3\u8bc4\u52068.8\uff0c\u7c7b\u578b\uff1a\u79d1\u5e7b\uff0c\u56fd\u5bb6/\u5730\u533a\uff1a\u7f8e\u56fd\uff0c\u8bed\u8a00\uff1a\u82f1\u8bed\u3002","citations":["ev1"]}'
                            }
                        }
                    ]
                },
                ensure_ascii=False,
            )
        )
        adapter = OpenAICompatibleLanguageAdapter(
            endpoint="http://127.0.0.1:11434",
            model="demo",
            api_key="super-secret-key",
            transport=transport,
        )

        result = adapter.explain(
            "\u8bf7\u89e3\u91ca\u4e3a\u4ec0\u4e48\u63a8\u8350\u5b83",
            {
                "ev1": {
                    "title": "\u771f\u5b9e\u6807\u9898",
                    "media_type": "\u7535\u5f71",
                    "year": 2014,
                    "genres": ["\u79d1\u5e7b"],
                    "countries": ["\u7f8e\u56fd"],
                    "languages": ["\u82f1\u8bed"],
                    "douban_rating": 8.8,
                    "cookie": "cookie-value",
                    "subscription": {"tier": "gold"},
                    "raw": {"phone": "123"},
                }
            },
        )

        self.assertEqual(
            result,
            "\u63a8\u8350\u300a\u771f\u5b9e\u6807\u9898\u300b\u4e8e2014\u5e74\u4e0a\u6620\uff0c\u8c46\u74e3\u8bc4\u52068.8\uff0c\u7c7b\u578b\uff1a\u79d1\u5e7b\uff0c\u56fd\u5bb6/\u5730\u533a\uff1a\u7f8e\u56fd\uff0c\u8bed\u8a00\uff1a\u82f1\u8bed\u3002",
        )
        self.assertEqual(len(transport.calls), 1)
        call = transport.calls[0]
        self.assertEqual(call["timeout"], 10)
        self.assertIn("Authorization", call["headers"])
        self.assertEqual(call["headers"]["Authorization"], "Bearer super-secret-key")
        self.assertEqual(call["url"], "http://127.0.0.1:11434/v1/chat/completions")
        payload = json.loads(call["body"])
        self.assertEqual(payload["model"], "demo")
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertIn("messages", payload)
        self.assertNotIn("input", payload)
        self.assertGreaterEqual(len(payload["messages"]), 1)
        message_body = json.loads(payload["messages"][-1]["content"])
        self.assertEqual(message_body["task"], "explain")
        self.assertEqual(message_body["request"], "\u8bf7\u89e3\u91ca\u4e3a\u4ec0\u4e48\u63a8\u8350\u5b83")
        evidence = message_body["evidence"]
        self.assertEqual(
            evidence,
            [
                {
                    "id": "ev1",
                    "title": "\u771f\u5b9e\u6807\u9898",
                    "media_type": "\u7535\u5f71",
                    "year": 2014,
                    "genres": ["\u79d1\u5e7b"],
                    "countries": ["\u7f8e\u56fd"],
                    "languages": ["\u82f1\u8bed"],
                    "douban_rating": 8.8,
                }
            ],
        )
        self.assertNotIn("cookie", call["body"])
        self.assertNotIn("subscription", call["body"])
        self.assertNotIn("phone", call["body"])
        self.assertNotIn("super-secret-key", call["body"])

    def test_openai_adapter_responses_endpoint_uses_responses_envelope(self):
        transport = RecordingTransport(
            payload=json.dumps(
                {
                    "output": [
                        {
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": '{"text":"\u63a8\u8350\u300a\u771f\u5b9e\u6807\u9898\u300b","citations":["ev1"]}',
                                }
                            ]
                        }
                    ]
                },
                ensure_ascii=False,
            )
        )
        adapter = OpenAICompatibleLanguageAdapter(
            endpoint="http://127.0.0.1:11434/v1/responses",
            model="demo",
            transport=transport,
        )

        result = adapter.explain("\u8bf7\u89e3\u91ca\u4e3a\u4ec0\u4e48\u63a8\u8350\u5b83", {"ev1": {"title": "\u771f\u5b9e\u6807\u9898"}})

        self.assertEqual(result, "\u63a8\u8350\u300a\u771f\u5b9e\u6807\u9898\u300b")
        self.assertEqual(len(transport.calls), 1)
        call = transport.calls[0]
        self.assertEqual(call["url"], "http://127.0.0.1:11434/v1/responses")
        payload = json.loads(call["body"])
        self.assertEqual(payload["model"], "demo")
        self.assertNotIn("response_format", payload)
        self.assertEqual(payload["instructions"], "Return one strict JSON object only. Do not include markdown or extra text.")
        self.assertEqual(payload["text"], {"format": {"type": "json_object"}})
        self.assertIn("input", payload)
        self.assertNotIn("messages", payload)
        self.assertIsInstance(payload["input"], str)
        input_payload = json.loads(payload["input"])
        self.assertEqual(input_payload["task"], "explain")
        self.assertEqual(input_payload["request"], "\u8bf7\u89e3\u91ca\u4e3a\u4ec0\u4e48\u63a8\u8350\u5b83")
        self.assertEqual(input_payload["evidence"], [{"id": "ev1", "title": "\u771f\u5b9e\u6807\u9898"}])

    def test_openai_adapter_accepts_direct_json_object_from_transport(self):
        adapter = OpenAICompatibleLanguageAdapter(
            endpoint="http://127.0.0.1:11434/v1/chat/completions",
            model="demo",
            transport=RecordingTransport(payload={"text": "\u63a8\u8350\u300a\u771f\u5b9e\u6807\u9898\u300b", "citations": ["ev1"]}),
        )

        result = adapter.explain("\u89e3\u91ca", {"ev1": {"title": "\u771f\u5b9e\u6807\u9898"}})

        self.assertEqual(result, "\u63a8\u8350\u300a\u771f\u5b9e\u6807\u9898\u300b")

    def test_explain_rejects_unknown_or_empty_citation(self):
        payloads = [
            '{"text":"\u63a8\u8350\u300a\u771f\u5b9e\u6807\u9898\u300b","citations":[]}',
            '{"text":"\u63a8\u8350\u300a\u771f\u5b9e\u6807\u9898\u300b","citations":["missing"]}',
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                adapter = OpenAICompatibleLanguageAdapter(
                    endpoint="http://127.0.0.1:11434/v1/chat/completions",
                    model="demo",
                    transport=RecordingTransport(payload=payload),
                )
                with self.assertRaisesRegex(UngroundedResponseError, "citation"):
                    adapter.explain("\u89e3\u91ca", {"ev1": {"title": "\u771f\u5b9e\u6807\u9898"}})

    def test_api_key_is_not_leaked_in_errors(self):
        secret = "top-secret-token"
        adapter = OpenAICompatibleLanguageAdapter(
            endpoint="http://127.0.0.1:11434",
            model="demo",
            api_key=secret,
            transport=RecordingTransport(error=OSError(f"boom {secret}")),
        )

        with self.assertRaises(RuntimeError) as cm:
            adapter.parse("\u60ac\u7591\u7535\u5f71", {})

        self.assertNotIn(secret, str(cm.exception))

    def test_parse_invalid_schema_falls_back_to_local_rules(self):
        service = LanguageService(
            primary=OpenAICompatibleLanguageAdapter(
                endpoint="http://127.0.0.1:11434",
                model="demo",
                transport=RecordingTransport(payload='{"runtime_max":"90"}'),
            ),
            fallback=LocalRuleLanguageAdapter(),
        )

        text = "\u60ac\u7591\u52a8\u753b\u5267\u96c6\uff0c\u4e00\u96c630\u5206\u949f\u4ee5\u5185"
        intent = service.parse(text, {"ev1": {"title": "\u793a\u4f8b"}})

        self.assertEqual(intent, parse_recommendation_intent(text))

    def test_local_explain_mentions_real_title(self):
        adapter = LocalRuleLanguageAdapter()

        text = adapter.explain(
            {"citations": ["ev1"]},
            {"ev1": {"title": "\u771f\u5b9e\u6807\u9898", "genres": ["\u79d1\u5e7b"], "year": 2014}},
        )

        self.assertIn("\u771f\u5b9e\u6807\u9898", text)
        self.assertIn("\u79d1\u5e7b", text)

    def test_local_explain_rejects_explicit_empty_citations(self):
        adapter = LocalRuleLanguageAdapter()

        for request in ({"citations": []}, {"evidence_ids": []}):
            with self.subTest(request=request):
                with self.assertRaisesRegex(UngroundedResponseError, "citation"):
                    adapter.explain(request, {"ev1": {"title": "\u771f\u5b9e\u6807\u9898"}})

    def test_service_explain_falls_back_when_model_is_ungrounded(self):
        service = LanguageService(
            primary=OpenAICompatibleLanguageAdapter(
                endpoint="http://127.0.0.1:11434",
                model="demo",
                transport=RecordingTransport(payload='{"text":"\u63a8\u8350\u300a\u4e0d\u5b58\u5728\u7684\u7535\u5f71\u300b","citations":["missing"]}'),
            ),
            fallback=LocalRuleLanguageAdapter(),
        )

        text = service.explain("\u89e3\u91ca", {"ev1": {"title": "\u771f\u5b9e\u6807\u9898", "genres": ["\u79d1\u5e7b"]}})

        self.assertIn("\u771f\u5b9e\u6807\u9898", text)
        self.assertNotIn("\u4e0d\u5b58\u5728\u7684\u7535\u5f71", text)

    def test_detect_local_endpoint_returns_candidate_without_network_call(self):
        self.assertEqual(detect_local_endpoint(), "http://127.0.0.1:11434/v1/chat/completions")

    def test_invalid_endpoint_is_rejected_before_transport(self):
        transport = RecordingTransport(payload='{"genres": ["\u60ac\u7591"]}')
        adapter = OpenAICompatibleLanguageAdapter(endpoint="javascript:alert(1)", model="demo", transport=transport)

        with self.assertRaisesRegex(ValueError, "endpoint"):
            adapter.parse("\u60ac\u7591\u7535\u5f71", {})

        self.assertEqual(transport.calls, [])

    def test_explain_accepts_supported_grounded_fact_claims(self):
        adapter = OpenAICompatibleLanguageAdapter(
            endpoint="http://127.0.0.1:11434/v1/chat/completions",
            model="demo",
            transport=RecordingTransport(
                payload=json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": '{"text":"\u63a8\u8350\u300a\u771f\u5b9e\u6807\u9898\u300b\u4e8e2014\u5e74\u4e0a\u6620\uff0c\u8c46\u74e3\u8bc4\u52068.8\uff0c\u7c7b\u578b\uff1a\u79d1\u5e7b\uff0c\u56fd\u5bb6/\u5730\u533a\uff1a\u7f8e\u56fd\uff0c\u8bed\u8a00\uff1a\u82f1\u8bed\u3002","citations":["ev1"]}'
                                }
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            ),
        )

        result = adapter.explain(
            "\u89e3\u91ca",
            {
                "ev1": {
                    "title": "\u771f\u5b9e\u6807\u9898",
                    "year": 2014,
                    "douban_rating": 8.8,
                    "genres": ["\u79d1\u5e7b"],
                    "countries": ["\u7f8e\u56fd"],
                    "languages": ["\u82f1\u8bed"],
                }
            },
        )

        self.assertEqual(
            result,
            "\u63a8\u8350\u300a\u771f\u5b9e\u6807\u9898\u300b\u4e8e2014\u5e74\u4e0a\u6620\uff0c\u8c46\u74e3\u8bc4\u52068.8\uff0c\u7c7b\u578b\uff1a\u79d1\u5e7b\uff0c\u56fd\u5bb6/\u5730\u533a\uff1a\u7f8e\u56fd\uff0c\u8bed\u8a00\uff1a\u82f1\u8bed\u3002",
        )

    def test_explain_rejects_ungrounded_explicit_facts(self):
        evidence = {
            "ev1": {
                "title": "\u771f\u5b9e\u6807\u9898",
                "year": 2014,
                "douban_rating": 8.8,
                "genres": ["\u79d1\u5e7b"],
                "countries": ["\u7f8e\u56fd"],
                "languages": ["\u82f1\u8bed"],
            }
        }
        payloads = {
            "year": '{"text":"\u63a8\u8350\u300a\u771f\u5b9e\u6807\u9898\u300b\u4e8e2015\u5e74\u4e0a\u6620\u3002","citations":["ev1"]}',
            "rating": '{"text":"\u63a8\u8350\u300a\u771f\u5b9e\u6807\u9898\u300b\uff0c\u8c46\u74e3\u8bc4\u52069.1\u3002","citations":["ev1"]}',
            "genres": '{"text":"\u63a8\u8350\u300a\u771f\u5b9e\u6807\u9898\u300b\uff0c\u7c7b\u578b\uff1a\u559c\u5267\u3002","citations":["ev1"]}',
            "countries": '{"text":"\u63a8\u8350\u300a\u771f\u5b9e\u6807\u9898\u300b\uff0c\u56fd\u5bb6/\u5730\u533a\uff1a\u6cd5\u56fd\u3002","citations":["ev1"]}',
            "languages": '{"text":"\u63a8\u8350\u300a\u771f\u5b9e\u6807\u9898\u300b\uff0c\u8bed\u8a00\uff1a\u6cd5\u8bed\u3002","citations":["ev1"]}',
        }

        for label, payload in payloads.items():
            with self.subTest(label=label):
                adapter = OpenAICompatibleLanguageAdapter(
                    endpoint="http://127.0.0.1:11434/v1/chat/completions",
                    model="demo",
                    transport=RecordingTransport(
                        payload=json.dumps(
                            {"choices": [{"message": {"content": payload}}]},
                            ensure_ascii=False,
                        )
                    ),
                )
                with self.assertRaisesRegex(UngroundedResponseError, "grounded"):
                    adapter.explain("\u89e3\u91ca", evidence)

    def test_default_transport_reads_using_instance_response_limit(self):
        response = FakeUrlopenResponse(b'{"genres":["x"]}')
        adapter = OpenAICompatibleLanguageAdapter(
            endpoint="http://127.0.0.1:11434/v1/chat/completions",
            model="demo",
            timeout=3,
            max_response_bytes=12,
        )

        with patch("douban_recommender.language_adapter.urllib.request.urlopen", return_value=response) as mocked:
            with self.assertRaises(RuntimeError):
                adapter.parse("\u60ac\u7591\u7535\u5f71", {})

        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(response.read_sizes, [13])

    def test_custom_transport_response_respects_instance_response_limit(self):
        adapter = OpenAICompatibleLanguageAdapter(
            endpoint="http://127.0.0.1:11434/v1/chat/completions",
            model="demo",
            transport=RecordingTransport(payload=b'{"genres":["x"]}'),
            max_response_bytes=10,
        )

        with self.assertRaisesRegex(RuntimeError, "too large"):
            adapter.parse("\u60ac\u7591\u7535\u5f71", {})


if __name__ == "__main__":
    unittest.main()
