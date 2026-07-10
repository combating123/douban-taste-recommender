import json
import unittest

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


class LanguageAdapterTests(unittest.TestCase):
    def test_openai_adapter_without_endpoint_does_not_call_transport(self):
        transport = RecordingTransport(payload='{"genres": ["悬疑"]}')
        service = LanguageService(
            primary=OpenAICompatibleLanguageAdapter(endpoint="", model="demo", transport=transport),
            fallback=LocalRuleLanguageAdapter(),
        )

        intent = service.parse("不要古装剧", {"ev1": {"title": "示例", "cookie": "secret"}})

        self.assertEqual(transport.calls, [])
        self.assertIn("古装", intent.avoid)

    def test_openai_adapter_only_sends_compact_evidence_and_auth_header(self):
        transport = RecordingTransport(payload='{"text":"推荐《真实标题》","citations":["ev1"]}')
        adapter = OpenAICompatibleLanguageAdapter(
            endpoint="http://127.0.0.1:11434",
            model="demo",
            api_key="super-secret-key",
            transport=transport,
        )

        result = adapter.explain(
            "请解释为什么推荐它",
            {
                "ev1": {
                    "title": "真实标题",
                    "media_type": "电影",
                    "year": 2014,
                    "genres": ["科幻"],
                    "cookie": "cookie-value",
                    "subscription": {"tier": "gold"},
                    "raw": {"phone": "123"},
                }
            },
        )

        self.assertEqual(result, "推荐《真实标题》")
        self.assertEqual(len(transport.calls), 1)
        call = transport.calls[0]
        self.assertEqual(call["timeout"], 10)
        self.assertIn("Authorization", call["headers"])
        self.assertEqual(call["headers"]["Authorization"], "Bearer super-secret-key")
        payload = json.loads(call["body"])
        evidence = payload["input"]["evidence"]
        self.assertEqual(
            evidence,
            [
                {
                    "id": "ev1",
                    "title": "真实标题",
                    "media_type": "电影",
                    "year": 2014,
                    "genres": ["科幻"],
                }
            ],
        )
        self.assertNotIn("cookie", call["body"])
        self.assertNotIn("subscription", call["body"])
        self.assertNotIn("phone", call["body"])
        self.assertNotIn("super-secret-key", call["body"])

    def test_explain_rejects_unknown_or_empty_citation(self):
        payloads = [
            '{"text":"推荐《真实标题》","citations":[]}',
            '{"text":"推荐《真实标题》","citations":["missing"]}',
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                adapter = OpenAICompatibleLanguageAdapter(
                    endpoint="http://127.0.0.1:11434",
                    model="demo",
                    transport=RecordingTransport(payload=payload),
                )
                with self.assertRaisesRegex(UngroundedResponseError, "citation"):
                    adapter.explain("解释", {"ev1": {"title": "真实标题"}})

    def test_api_key_is_not_leaked_in_errors(self):
        secret = "top-secret-token"
        adapter = OpenAICompatibleLanguageAdapter(
            endpoint="http://127.0.0.1:11434",
            model="demo",
            api_key=secret,
            transport=RecordingTransport(error=OSError(f"boom {secret}")),
        )

        with self.assertRaises(RuntimeError) as cm:
            adapter.parse("悬疑电影", {})

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

        intent = service.parse("悬疑动画剧集，一集30分钟以内", {"ev1": {"title": "示例"}})

        self.assertEqual(intent, parse_recommendation_intent("悬疑动画剧集，一集30分钟以内"))

    def test_local_explain_mentions_real_title(self):
        adapter = LocalRuleLanguageAdapter()

        text = adapter.explain(
            {"citations": ["ev1"]},
            {"ev1": {"title": "真实标题", "genres": ["科幻"], "year": 2014}},
        )

        self.assertIn("真实标题", text)
        self.assertIn("科幻", text)

    def test_service_explain_falls_back_when_model_is_ungrounded(self):
        service = LanguageService(
            primary=OpenAICompatibleLanguageAdapter(
                endpoint="http://127.0.0.1:11434",
                model="demo",
                transport=RecordingTransport(payload='{"text":"推荐《不存在的电影》","citations":["missing"]}'),
            ),
            fallback=LocalRuleLanguageAdapter(),
        )

        text = service.explain("解释", {"ev1": {"title": "真实标题", "genres": ["科幻"]}})

        self.assertIn("真实标题", text)
        self.assertNotIn("不存在的电影", text)

    def test_detect_local_endpoint_returns_candidate_without_network_call(self):
        self.assertEqual(detect_local_endpoint(), "http://127.0.0.1:11434/v1/chat/completions")

    def test_invalid_endpoint_is_rejected_before_transport(self):
        transport = RecordingTransport(payload='{"genres": ["悬疑"]}')
        adapter = OpenAICompatibleLanguageAdapter(endpoint="javascript:alert(1)", model="demo", transport=transport)

        with self.assertRaisesRegex(ValueError, "endpoint"):
            adapter.parse("悬疑电影", {})

        self.assertEqual(transport.calls, [])


if __name__ == "__main__":
    unittest.main()
