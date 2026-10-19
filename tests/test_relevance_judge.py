import unittest
from unittest import mock

from fake_llm import FakeLLM
from app.llm_client import LLMError
from app.models import PolicyCandidate, PolicySearchResult
from app.relevance_judge import (
    JUDGE_SEED,
    RelevanceJudge,
    RelevanceJudgeError,
    SYSTEM_INSTRUCTION,
    _Verdict,
    _Verdicts,
    build_prompt,
    rerank_with_judge,
)


def candidate(policy_id: str, title: str = "", summary: str = "요약") -> PolicyCandidate:
    return PolicyCandidate(
        policy_id=policy_id, title=title or policy_id, region_text="", score=1.0, distance=0.3,
        scope="시군구", summary=summary, metadata={}, reasons=[],
    )


FakeClient = FakeLLM


def verdicts(*flags):
    return _Verdicts(items=[_Verdict(id=i, relevant=flag) for i, flag in enumerate(flags)])


class RelevanceJudgeTest(unittest.TestCase):
    def test_returns_verdicts_by_policy_id_and_sends_question_candidates_and_age(self):
        client = FakeClient([verdicts(True, False)])
        judge = RelevanceJudge(client, model="m")
        result = judge.judge("배고파", "무료 급식 식사 지원", [candidate("a", "급식소"), candidate("b", "교통비")], age=28)
        self.assertEqual(result, {"a": True, "b": False})
        call = client.calls[0]
        prompt = call["prompt"]
        self.assertEqual(call["model"], "m")
        for text in ("배고파", "무료 급식 식사 지원", "0. 급식소", "1. 교통비", "28세"):
            self.assertIn(text, prompt)
        self.assertEqual(call["seed"], JUDGE_SEED)
        self.assertEqual(call["system"], SYSTEM_INSTRUCTION)
        self.assertEqual(call["timeout_ms"], 10_000)

    def test_prompt_omits_age_and_duplicate_query_when_not_given(self):
        prompt = build_prompt("월세", "월세", [candidate("a", "정책", "줄바꿈\n있는   요약")], age=None)
        self.assertNotIn("만 나이", prompt)
        self.assertNotIn("검색어", prompt)
        self.assertIn("줄바꿈 있는 요약", prompt)

    def test_long_summary_is_trimmed(self):
        prompt = build_prompt("q", "q", [candidate("a", "t", "가" * 1000)], None)
        self.assertLess(len(prompt), 600)

    def test_no_candidates_means_no_call(self):
        client = FakeClient([])
        self.assertEqual(RelevanceJudge(client).judge("q", "q", []), {})
        self.assertEqual(client.calls, [])

    def test_missing_verdicts_raise(self):
        judge = RelevanceJudge(FakeClient([_Verdicts(items=[_Verdict(id=0, relevant=True)])]))
        with self.assertRaises(RelevanceJudgeError):
            judge.judge("q", "q", [candidate("a"), candidate("b")])

    def test_duplicate_or_unknown_ids_raise(self):
        dup = _Verdicts(items=[_Verdict(id=0, relevant=True), _Verdict(id=0, relevant=False)])
        with self.assertRaises(RelevanceJudgeError):
            RelevanceJudge(FakeClient([dup])).judge("q", "q", [candidate("a"), candidate("b")])
        unknown = _Verdicts(items=[_Verdict(id=0, relevant=True), _Verdict(id=5, relevant=True)])
        with self.assertRaises(RelevanceJudgeError):
            RelevanceJudge(FakeClient([unknown])).judge("q", "q", [candidate("a"), candidate("b")])

    def test_rate_limit_is_not_retried(self):
        client = FakeClient([LLMError("quota", 429)])
        with self.assertRaises(RelevanceJudgeError):
            RelevanceJudge(client).judge("q", "q", [candidate("a")])
        self.assertEqual(len(client.calls), 1)

    def test_server_error_is_retried_once(self):
        client = FakeClient([LLMError("x", 503), verdicts(True)])
        with mock.patch("app.relevance_judge.time.sleep") as sleep:
            result = RelevanceJudge(client).judge("q", "q", [candidate("a")])
        self.assertEqual(result, {"a": True})
        self.assertEqual(len(client.calls), 2)
        sleep.assert_called_once()

    def test_persistent_server_error_gives_up_after_two_attempts(self):
        client = FakeClient([LLMError("x", 500), LLMError("x", 500)])
        with mock.patch("app.relevance_judge.time.sleep"), self.assertRaises(RelevanceJudgeError):
            RelevanceJudge(client).judge("q", "q", [candidate("a")])
        self.assertEqual(len(client.calls), 2)

    def test_unexpected_error_becomes_judge_error(self):
        with self.assertRaises(RelevanceJudgeError):
            RelevanceJudge(FakeClient([TimeoutError("slow")])).judge("q", "q", [candidate("a")])

    def test_error_message_does_not_leak_question_or_response(self):
        try:
            RelevanceJudge(FakeClient([RuntimeError("SECRET-BODY")])).judge("비밀 질문", "q", [candidate("a")])
        except RelevanceJudgeError as exc:
            self.assertNotIn("비밀 질문", str(exc))
            self.assertNotIn("SECRET-BODY", str(exc))


class FakeJudge:
    def __init__(self, relevant_ids):
        self.relevant_ids = set(relevant_ids)
        self.calls = []

    def judge(self, question, search_query, candidates, age=None):
        self.calls.append((question, search_query, [c.policy_id for c in candidates], age))
        return {c.policy_id: c.policy_id in self.relevant_ids for c in candidates}


class RerankTest(unittest.TestCase):
    def pool(self):
        return PolicySearchResult(
            local_policies=[candidate(f"local:{i}") for i in range(1, 7)],
            national_policies=[candidate(f"national:{i}") for i in range(1, 5)],
        )

    def test_relevant_first_then_irrelevant_folded_and_marked(self):
        judge = FakeJudge({"local:2", "local:4", "national:3"})
        outcome = rerank_with_judge(judge, "q", "sq", self.pool(), age=30)
        self.assertEqual([p.policy_id for p in outcome.local_policies], ["local:2", "local:4", "local:1", "local:3", "local:5"])
        self.assertEqual([p.policy_id for p in outcome.national_policies], ["national:3", "national:1", "national:2", "national:4"])
        self.assertEqual(outcome.low_relevance_ids, ["local:1", "local:3", "local:5", "national:1", "national:2", "national:4"])
        self.assertEqual(judge.calls[0][3], 30)

    def test_relevant_ones_are_capped_and_low_ones_limited(self):
        judge = FakeJudge({f"local:{i}" for i in range(1, 7)})  # 지자체 6건 모두 관련
        outcome = rerank_with_judge(judge, "q", "sq", self.pool(), show=3, keep_low=2)
        self.assertEqual([p.policy_id for p in outcome.local_policies if p.policy_id not in outcome.low_relevance_ids], ["local:1", "local:2", "local:3"])
        self.assertEqual(len([p for p in outcome.national_policies]), 2)  # 중앙은 전부 무관 → 접힌 2건만

    def test_nothing_relevant_keeps_only_folded(self):
        outcome = rerank_with_judge(FakeJudge(set()), "q", "sq", self.pool())
        self.assertEqual(len(outcome.local_policies), 3)
        self.assertEqual(set(outcome.low_relevance_ids), {p.policy_id for p in outcome.local_policies + outcome.national_policies})

    def test_judge_failure_propagates_to_the_caller(self):
        class Boom:
            def judge(self, *args, **kwargs):
                raise RelevanceJudgeError("x")

        with self.assertRaises(RelevanceJudgeError):
            rerank_with_judge(Boom(), "q", "sq", self.pool())

    def test_empty_pool(self):
        outcome = rerank_with_judge(FakeJudge(set()), "q", "sq", PolicySearchResult())
        self.assertEqual((outcome.local_policies, outcome.national_policies, outcome.low_relevance_ids), ([], [], []))


if __name__ == "__main__":
    unittest.main()
