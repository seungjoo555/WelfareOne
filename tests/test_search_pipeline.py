import unittest
from types import SimpleNamespace
from unittest import mock

from google.genai import errors

from app.env import load_env_file
from app.gemini_retry import call_with_retry
from app.models import PolicyCandidate, PolicySearchResult, QuestionAnalysis, RegionSelection
from app.search_pipeline import DEFAULT_TOP_K, run_search


def candidate(policy_id: str, scope: str = "시군구") -> PolicyCandidate:
    return PolicyCandidate(
        policy_id=policy_id, title=policy_id, region_text="", score=1.0, distance=0.3,
        scope=scope, summary="", metadata={}, reasons=[],
    )


def analysis(route: str = "situation_search") -> QuestionAnalysis:
    return QuestionAnalysis(
        route=route, policy_name=None, search_query="월세 지원", intent="policy_search",
        intents=["policy_search"], requested_sections=["candidate_summary"],
        include_keywords=["월세"], exclude_keywords=[], confidence=0.9,
    )


class FakeSearch:
    def __init__(self, local=0, national=0):
        self.pool = PolicySearchResult(
            local_policies=[candidate(f"local:{i}") for i in range(local)],
            national_policies=[candidate(f"national:{i}", "중앙부처") for i in range(national)],
        )
        self.calls = []

    def search_policies(self, question, region, **kwargs):
        self.calls.append((question, kwargs))
        return self.pool


class FakeJudge:
    def __init__(self, relevant_ids=None, error=None):
        self.relevant_ids, self.error = relevant_ids or set(), error

    def judge(self, question, search_query, candidates, age=None):
        if self.error:
            raise self.error
        return {c.policy_id: c.policy_id in self.relevant_ids for c in candidates}


REGION = RegionSelection(level1="서울특별시", level2="관악구")


class RunSearchTest(unittest.TestCase):
    def test_without_judge_returns_search_result_as_is(self):
        search = FakeSearch(local=3, national=2)
        outcome = run_search(analysis(), search, REGION, 24, "월세가 부담돼요")
        self.assertEqual(len(outcome.local_policies), 3)
        self.assertEqual(len(outcome.national_policies), 2)
        self.assertFalse(outcome.relevance_checked)
        self.assertEqual(outcome.low_relevance_ids, [])
        self.assertNotIn("local_top_k", search.calls[0][1])  # 후보 풀을 넓히지 않는다

    def test_judge_widens_pool_and_folds_irrelevant(self):
        search = FakeSearch(local=5)
        judge = FakeJudge(relevant_ids={"local:0", "local:3"})
        outcome = run_search(analysis(), search, REGION, 24, "q", judge)
        self.assertTrue(outcome.relevance_checked)
        self.assertEqual([p.policy_id for p in outcome.local_policies][:2], ["local:0", "local:3"])
        self.assertIn("local:1", outcome.low_relevance_ids)
        self.assertGreater(search.calls[0][1]["local_top_k"], DEFAULT_TOP_K)

    def test_judge_returns_all_relevant_candidates_for_paging(self):
        # 관련 판정 후보가 3개를 넘어도 풀 전체를 내려준다(화면이 3개씩 쪽으로 넘겨 본다). 접힘은 최대 3개.
        search = FakeSearch(local=8, national=2)
        judge = FakeJudge(relevant_ids={f"local:{i}" for i in range(6)} | {"national:0"})
        outcome = run_search(analysis(), search, REGION, None, "q", judge)
        relevant_local = [p.policy_id for p in outcome.local_policies if p.policy_id not in outcome.low_relevance_ids]
        self.assertEqual(relevant_local, [f"local:{i}" for i in range(6)])
        self.assertEqual(len(outcome.local_policies), 8)  # 관련 6 + 접힘 2
        self.assertEqual([p.policy_id for p in outcome.national_policies][:1], ["national:0"])

    def test_judge_with_no_relevant_candidates_still_folds_at_most_three(self):
        search = FakeSearch(local=8)
        outcome = run_search(analysis(), search, REGION, None, "q", FakeJudge(relevant_ids=set()))
        self.assertEqual(len(outcome.local_policies), 3)
        self.assertEqual(len(outcome.low_relevance_ids), 3)

    def test_judge_failure_falls_back_to_distance_top_k(self):
        search = FakeSearch(local=6, national=6)
        with self.assertLogs("welfareone.api", level="WARNING"):
            outcome = run_search(analysis(), search, REGION, None, "q", FakeJudge(error=RuntimeError("boom")))
        self.assertFalse(outcome.relevance_checked)
        self.assertEqual(len(outcome.local_policies), DEFAULT_TOP_K)
        self.assertEqual(len(outcome.national_policies), DEFAULT_TOP_K)
        self.assertEqual(outcome.low_relevance_ids, [])

    def test_judge_is_skipped_for_other_routes(self):
        search = FakeSearch(local=2)
        outcome = run_search(analysis("specific_policy"), search, REGION, None, "q", FakeJudge(error=RuntimeError()))
        self.assertFalse(outcome.relevance_checked)
        self.assertEqual(len(outcome.local_policies), 2)


class GeminiRetryTest(unittest.TestCase):
    @staticmethod
    def api_error(code):
        return errors.APIError(code, {"error": {"message": "x", "status": "X"}})

    def test_retries_retryable_status_then_succeeds(self):
        calls = {"n": 0}

        def action():
            calls["n"] += 1
            if calls["n"] < 3:
                raise self.api_error(503)
            return "ok"

        with mock.patch("app.gemini_retry.time.sleep") as sleep:
            self.assertEqual(call_with_retry(action, 3), "ok")
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2])

    def test_non_retryable_error_is_raised_immediately(self):
        calls = {"n": 0}

        def action():
            calls["n"] += 1
            raise self.api_error(400)

        with mock.patch("app.gemini_retry.time.sleep"), self.assertRaises(errors.APIError):
            call_with_retry(action, 3)
        self.assertEqual(calls["n"], 1)

    def test_gives_up_after_max_retries(self):
        calls = {"n": 0}

        def action():
            calls["n"] += 1
            raise self.api_error(429)

        with mock.patch("app.gemini_retry.time.sleep"), self.assertRaises(errors.APIError):
            call_with_retry(action, 3)
        self.assertEqual(calls["n"], 3)

    def test_other_exceptions_are_not_retried(self):
        calls = {"n": 0}

        def action():
            calls["n"] += 1
            raise ValueError("bad json")

        with self.assertRaises(ValueError):
            call_with_retry(action, 3)
        self.assertEqual(calls["n"], 1)


class LoadEnvFileTest(unittest.TestCase):
    def test_reads_values_without_overriding_existing(self):
        import os
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text('# 주석\nWO_TEST_A="x"\nWO_TEST_B=keep\n\n잘못된줄\n', encoding="utf-8-sig")
            with mock.patch.dict(os.environ, {"WO_TEST_B": "existing"}, clear=False):
                os.environ.pop("WO_TEST_A", None)
                load_env_file(path)
                self.assertEqual(os.environ["WO_TEST_A"], "x")
                self.assertEqual(os.environ["WO_TEST_B"], "existing")
                os.environ.pop("WO_TEST_A", None)

    def test_missing_file_is_ignored(self):
        from pathlib import Path

        load_env_file(Path("does-not-exist.env"))


if __name__ == "__main__":
    unittest.main()
