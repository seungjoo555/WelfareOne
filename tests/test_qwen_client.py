import json
import unittest

import httpx
from pydantic import BaseModel

from app.gemini_retry import call_with_retry
from app.llm_client import LLMError, QwenClient


class Answer(BaseModel):
    text: str
    score: int


def completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


class FakeServer:
    """OpenAI 호환 서버 흉내. 요청 본문을 기록하고 준비한 응답을 차례로 돌려준다."""

    def __init__(self, *responses):
        self.responses, self.requests = list(responses), []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request, json.loads(request.content)))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make(*responses, **kwargs):
    server = FakeServer(*responses)
    client = QwenClient("http://localhost:1234/v1/", "qwen-test", transport=httpx.MockTransport(server), **kwargs)
    return client, server


class QwenClientTest(unittest.TestCase):
    def test_sends_json_schema_system_prompt_and_seed_and_parses_reply(self):
        client, server = make(completion('{"text": "안녕", "score": 3}'))
        result = client.generate_json(system="지침", prompt="질문", schema=Answer, seed=7, timeout_ms=5000)
        self.assertEqual(result, Answer(text="안녕", score=3))
        request, body = server.requests[0]
        self.assertEqual(str(request.url), "http://localhost:1234/v1/chat/completions")
        self.assertEqual(body["model"], "qwen-test")
        self.assertEqual(body["messages"], [{"role": "system", "content": "지침"}, {"role": "user", "content": "질문"}])
        self.assertEqual((body["temperature"], body["seed"], body["stream"]), (0, 7, False))
        fmt = body["response_format"]
        self.assertEqual(fmt["type"], "json_schema")
        self.assertEqual(fmt["json_schema"]["name"], "Answer")
        self.assertEqual(set(fmt["json_schema"]["schema"]["properties"]), {"text", "score"})

    def test_model_override_and_optional_seed_and_extra_body_and_api_key(self):
        client, server = make(completion('{"text": "a", "score": 1}'), api_key="secret", extra_body={"top_p": 0.9})
        client.generate_json(system="s", prompt="p", schema=Answer, model="other")
        request, body = server.requests[0]
        self.assertEqual(body["model"], "other")
        self.assertNotIn("seed", body)
        self.assertEqual(body["top_p"], 0.9)
        self.assertEqual(request.headers["authorization"], "Bearer secret")

    def test_thinking_is_turned_off_by_default_and_can_be_left_to_the_server(self):
        client, server = make(completion('{"text": "a", "score": 1}'))
        client.generate_json(system="s", prompt="p", schema=Answer)
        self.assertEqual(server.requests[0][1]["reasoning_effort"], "none")
        client, server = make(completion('{"text": "a", "score": 1}'), extra_body={})
        client.generate_json(system="s", prompt="p", schema=Answer)
        self.assertNotIn("reasoning_effort", server.requests[0][1])

    def test_invalid_reply_is_retried_once_with_error_feedback(self):
        client, server = make(completion('{"text": "a"}'), completion('{"text": "a", "score": 2}'))
        result = client.generate_json(system="s", prompt="p", schema=Answer)
        self.assertEqual(result.score, 2)
        retry_messages = server.requests[1][1]["messages"]
        self.assertEqual([m["role"] for m in retry_messages], ["system", "user", "assistant", "user"])
        self.assertIn("스키마", retry_messages[-1]["content"])

    def test_gives_up_after_one_validation_retry(self):
        client, server = make(completion("not json"), completion("still not json"))
        with self.assertRaises(LLMError) as ctx:
            client.generate_json(system="s", prompt="p", schema=Answer)
        self.assertIsNone(ctx.exception.code)  # 재시도 대상이 아니므로 api에서 LLM_RESPONSE_INVALID가 된다
        self.assertEqual(len(server.requests), 2)

    def test_http_status_becomes_llm_error_code(self):
        client, _ = make(httpx.Response(503, json={"error": "busy"}))
        with self.assertRaises(LLMError) as ctx:
            client.generate_json(system="s", prompt="p", schema=Answer)
        self.assertEqual(ctx.exception.code, 503)

    def test_connection_failure_is_retryable_503(self):
        client, _ = make(httpx.ConnectError("refused"))
        with self.assertRaises(LLMError) as ctx:
            client.generate_json(system="s", prompt="p", schema=Answer)
        self.assertEqual(ctx.exception.code, 503)

    def test_malformed_response_body_becomes_llm_error(self):
        client, _ = make(httpx.Response(200, json={"unexpected": 1}))
        with self.assertRaises(LLMError):
            client.generate_json(system="s", prompt="p", schema=Answer)

    def test_server_overload_is_retried_by_shared_retry_rule(self):
        client, server = make(httpx.Response(503, json={}), completion('{"text": "a", "score": 1}'))
        from unittest import mock

        with mock.patch("app.gemini_retry.time.sleep"):
            result = call_with_retry(lambda: client.generate_json(system="s", prompt="p", schema=Answer), 3)
        self.assertEqual(result.text, "a")
        self.assertEqual(len(server.requests), 2)


if __name__ == "__main__":
    unittest.main()
