"""서버 기본 LLM 공급자 선택 규칙과 GET /config (계약서 제안 8-1, 8-3)."""

import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.api import Services, create_app
from app.llm_client import QwenClient, server_qwen_from_env
from test_api import REGIONS, VALID_KEY, FakeAnalyzer, FakeAnswers, FakeRepository, FakeSearch

BODY = {"question": "월세가 부담돼요", "region": {"level1": "경기도", "level2": "성남시"}, "age": 24}


def client_for(**kwargs):
    services = Services(FakeRepository(), FakeSearch(), regions=REGIONS, **{"analyzer": None, "answers": None, **kwargs})
    cm = TestClient(create_app(services), raise_server_exceptions=False)
    return cm


class ProviderSelectionTest(unittest.TestCase):
    def setUp(self):
        self.server_analyzer, self.server_answers = FakeAnalyzer(), FakeAnswers()
        self.user_analyzer = FakeAnalyzer()
        self.made_with = []

        def analyzer_factory(key):
            self.made_with.append(key)
            return self.user_analyzer

        self.cm = client_for(
            analyzer=self.server_analyzer, answers=self.server_answers, server_llm_provider="qwen",
            analyzer_factory=analyzer_factory, answers_factory=lambda key: self.server_answers,
        )
        self.client = self.cm.__enter__()
        self.addCleanup(self.cm.__exit__, None, None, None)

    def test_request_without_key_uses_the_server_provider(self):
        response = self.client.post("/policies/search", json=BODY)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.server_analyzer.calls), 1)
        self.assertEqual(self.made_with, [])

    def test_request_with_key_always_uses_the_user_key_even_if_server_provider_exists(self):
        response = self.client.post("/policies/search", json=BODY, headers={"X-Gemini-Api-Key": VALID_KEY})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.made_with, [VALID_KEY])
        self.assertEqual(len(self.user_analyzer.calls), 1)
        self.assertEqual(self.server_analyzer.calls, [])  # 사용자 키 요청이 서버 모델로 새지 않는다

    def test_malformed_key_is_rejected_instead_of_falling_back_to_the_server_provider(self):
        response = self.client.post("/policies/search", json=BODY, headers={"X-Gemini-Api-Key": "short"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "INVALID_API_KEY")
        self.assertEqual(self.server_analyzer.calls, [])


class ConfigEndpointTest(unittest.TestCase):
    def config(self, **kwargs):
        with client_for(**kwargs) as client:
            response = client.get("/config")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_server_provider_is_reported(self):
        data = self.config(analyzer=FakeAnalyzer(), answers=FakeAnswers(), server_llm_provider="qwen")
        self.assertEqual(data, {"server_llm": True, "server_llm_provider": "qwen", "user_key_provider": "gemini"})

    def test_server_key_fallback_is_reported_as_gemini(self):
        data = self.config(analyzer=FakeAnalyzer(), answers=FakeAnswers())
        self.assertEqual((data["server_llm"], data["server_llm_provider"]), (True, "gemini"))

    def test_no_server_llm_means_user_key_is_required(self):
        data = self.config()
        self.assertEqual(data, {"server_llm": False, "server_llm_provider": None, "user_key_provider": "gemini"})


class ServerQwenFromEnvTest(unittest.TestCase):
    def env(self, **values):
        base = {k: "" for k in ("LLM_PROVIDER", "QWEN_BASE_URL", "QWEN_MODEL", "QWEN_API_KEY", "QWEN_TIMEOUT_S", "QWEN_EXTRA_BODY")}
        return mock.patch.dict(os.environ, {**base, **values})

    def test_unset_provider_means_no_server_qwen(self):
        with self.env():
            self.assertIsNone(server_qwen_from_env())

    def test_builds_client_from_env_with_lm_studio_default_address(self):
        with self.env(LLM_PROVIDER="qwen", QWEN_MODEL="qwen/qwen3-4b-2507"):
            client = server_qwen_from_env()
        self.assertIsInstance(client, QwenClient)
        self.assertEqual(client.model, "qwen/qwen3-4b-2507")
        self.assertEqual(str(client._http.base_url), "http://localhost:1234/v1/")

    def test_extra_body_json_overrides_default_thinking_switch(self):
        with self.env(LLM_PROVIDER="qwen", QWEN_MODEL="m", QWEN_EXTRA_BODY='{"top_p": 0.8}'):
            self.assertEqual(server_qwen_from_env()._extra_body, {"top_p": 0.8})

    def test_misconfiguration_fails_fast(self):
        for values in (
            {"LLM_PROVIDER": "qwen"},  # 모델 이름 없음
            {"LLM_PROVIDER": "other", "QWEN_MODEL": "m"},
            {"LLM_PROVIDER": "qwen", "QWEN_MODEL": "m", "QWEN_EXTRA_BODY": "not json"},
            {"LLM_PROVIDER": "qwen", "QWEN_MODEL": "m", "QWEN_EXTRA_BODY": "[1]"},
        ):
            with self.subTest(values=values), self.env(**values):
                with self.assertRaises(ValueError):
                    server_qwen_from_env()


if __name__ == "__main__":
    unittest.main()
