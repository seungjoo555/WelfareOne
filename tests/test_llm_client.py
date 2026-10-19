import unittest
from types import SimpleNamespace
from unittest import mock

from google.genai import errors
from pydantic import BaseModel

from app.gemini_retry import call_with_retry
from app.llm_client import GeminiClient, LLMError


class Answer(BaseModel):
    text: str


class FakeModels:
    def __init__(self, result):
        self.result, self.calls = result, []

    def generate_content(self, model, contents, config):
        self.calls.append((model, contents, config))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def make_client(result, model="m"):
    with mock.patch("app.llm_client.genai.Client") as factory:
        factory.return_value = SimpleNamespace(models=FakeModels(result))
        client = GeminiClient("k" * 24, model)
    return client, client._client.models


class GeminiClientTest(unittest.TestCase):
    def test_sends_system_prompt_seed_and_timeout_and_returns_parsed_object(self):
        client, models = make_client(SimpleNamespace(parsed=Answer(text="ok"), text=""))
        result = client.generate_json(system="sys", prompt="질문", schema=Answer, seed=3, timeout_ms=5000)
        self.assertEqual(result, Answer(text="ok"))
        model, contents, config = models.calls[0]
        self.assertEqual((model, contents), ("m", "질문"))
        self.assertEqual((config.system_instruction, config.seed, config.temperature), ("sys", 3, 0))
        self.assertEqual(config.http_options.timeout, 5000)

    def test_model_can_be_overridden_per_call_and_timeout_is_optional(self):
        client, models = make_client(SimpleNamespace(parsed=Answer(text="ok"), text=""))
        client.generate_json(system="s", prompt="p", schema=Answer, model="other")
        self.assertEqual(models.calls[0][0], "other")
        self.assertIsNone(models.calls[0][2].http_options)

    def test_falls_back_to_response_text_when_not_parsed(self):
        client, _ = make_client(SimpleNamespace(parsed=None, text='{"text": "raw"}'))
        self.assertEqual(client.generate_json(system="s", prompt="p", schema=Answer), Answer(text="raw"))

    def test_api_errors_become_llm_error_with_status_code(self):
        client, _ = make_client(errors.APIError(429, {"error": {"message": "quota"}}))
        with self.assertRaises(LLMError) as ctx:
            client.generate_json(system="s", prompt="p", schema=Answer)
        self.assertEqual(ctx.exception.code, 429)
        self.assertIsInstance(ctx.exception.__cause__, errors.APIError)


class RetryTest(unittest.TestCase):
    def test_llm_error_with_retryable_status_is_retried(self):
        calls = []

        def action():
            calls.append(1)
            if len(calls) == 1:
                raise LLMError("busy", 503)
            return "done"

        with mock.patch("app.gemini_retry.time.sleep"):
            self.assertEqual(call_with_retry(action, 3), "done")
        self.assertEqual(len(calls), 2)

    def test_llm_error_with_other_status_is_raised_immediately(self):
        def action():
            raise LLMError("bad key", 401)

        with self.assertRaises(LLMError):
            call_with_retry(action, 3)


if __name__ == "__main__":
    unittest.main()
