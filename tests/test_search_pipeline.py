import unittest
from types import SimpleNamespace
from unittest import mock

from google.genai import errors

from app.env import load_env_file
from app.gemini_retry import call_with_retry
from app.models import PolicyCandidate, PolicySearchResult, QuestionAnalysis, RegionSelection
from app.relevance_judge import POOL_PER_SCOPE
from app.search_pipeline import run_search, search_queries


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
        self.assertEqual(search.calls[0][1]["local_top_k"], POOL_PER_SCOPE)

    def test_judge_returns_whole_pool_relevant_first_then_low_relevance(self):
        # 풀 전체를 내려준다: 관련 판정 후보가 앞, 나머지(관련도 낮음)가 뒤. 화면이 3개씩 이어서 보여 준다.
        search = FakeSearch(local=8, national=2)
        judge = FakeJudge(relevant_ids={"local:5", "local:2", "national:0"})
        outcome = run_search(analysis(), search, REGION, None, "q", judge)
        ids = [p.policy_id for p in outcome.local_policies]
        self.assertEqual(ids[:2], ["local:2", "local:5"])  # 관련 후보가 먼저(풀의 점수 순서 유지)
        self.assertEqual(len(ids), 8)  # 나머지 6개도 뒤에 이어진다
        self.assertEqual(
            set(outcome.low_relevance_ids) & set(ids), {f"local:{i}" for i in (0, 1, 3, 4, 6, 7)}
        )
        self.assertEqual([p.policy_id for p in outcome.national_policies][:1], ["national:0"])

    def test_judge_with_no_relevant_candidates_keeps_whole_pool_as_low_relevance(self):
        search = FakeSearch(local=8)
        outcome = run_search(analysis(), search, REGION, None, "q", FakeJudge(relevant_ids=set()))
        self.assertEqual(len(outcome.local_policies), 8)
        self.assertEqual(len(outcome.low_relevance_ids), 8)

    def test_judge_failure_falls_back_to_whole_pool_in_distance_order(self):
        search = FakeSearch(local=6, national=6)
        with self.assertLogs("welfareone.api", level="WARNING"):
            outcome = run_search(analysis(), search, REGION, None, "q", FakeJudge(error=RuntimeError("boom")))
        self.assertFalse(outcome.relevance_checked)
        self.assertEqual([p.policy_id for p in outcome.local_policies], [f"local:{i}" for i in range(6)])
        self.assertEqual(len(outcome.national_policies), 6)
        self.assertEqual(outcome.low_relevance_ids, [])

    def test_judge_is_skipped_for_other_routes(self):
        search = FakeSearch(local=2)
        outcome = run_search(analysis("specific_policy"), search, REGION, None, "q", FakeJudge(error=RuntimeError()))
        self.assertFalse(outcome.relevance_checked)
        self.assertEqual(len(outcome.local_policies), 2)


def scored(policy_id: str, score: float, scope: str = "시군구") -> PolicyCandidate:
    return PolicyCandidate(
        policy_id=policy_id, title=policy_id, region_text="", score=score, distance=1 - score,
        scope=scope, summary="", metadata={}, reasons=[],
    )


class ScriptedSearch:
    """질문 문장과 하한(max_distance)에 따라 다른 결과를 돌려주는 가짜 검색."""

    def __init__(self, by_query=None, limit_hides_all=False):
        self.by_query = by_query or {}
        self.limit_hides_all = limit_hides_all  # True면 기본 하한(0.55)에서는 빈 결과, 완화하면 결과가 나온다
        self.calls = []

    def search_policies(self, question, region, **kwargs):
        self.calls.append((question, kwargs))
        if self.limit_hides_all and kwargs.get("max_distance", 0.60) < 0.60:
            return PolicySearchResult()
        return self.by_query.get(question, PolicySearchResult())


class SearchQueriesTest(unittest.TestCase):
    def test_situation_question_searches_with_analyzer_query_and_raw_question(self):
        self.assertEqual(search_queries(analysis(), "월세가 부담돼요"), ["월세 지원", "월세가 부담돼요"])

    def test_raw_question_is_whitespace_normalized_and_deduplicated(self):
        self.assertEqual(search_queries(analysis(), "월세   지원"), ["월세 지원"])

    def test_other_routes_use_only_the_analyzer_query(self):
        self.assertEqual(search_queries(analysis("specific_policy"), "청년월세 지원사업 알려줘"), ["월세 지원"])

    def test_overlong_raw_question_is_not_added(self):
        self.assertEqual(search_queries(analysis(), "가" * 201), ["월세 지원"])


class MultiQueryAndRescueTest(unittest.TestCase):
    def test_results_of_both_queries_are_merged_by_best_score_per_policy(self):
        search = ScriptedSearch({
            "월세 지원": PolicySearchResult([scored("local:A", 0.50), scored("local:B", 0.40)], []),
            "월세가 부담돼요": PolicySearchResult([scored("local:A", 0.60), scored("local:C", 0.55)], [scored("national:N", 0.5, "중앙부처")]),
        })
        outcome = run_search(analysis(), search, REGION, None, "월세가 부담돼요")
        self.assertEqual([p.policy_id for p in outcome.local_policies], ["local:A", "local:C", "local:B"])
        self.assertEqual(outcome.local_policies[0].score, 0.60)  # 같은 정책은 점수가 높은 쪽
        self.assertEqual([p.policy_id for p in outcome.national_policies], ["national:N"])
        self.assertEqual(len(search.calls), 2)

    def test_merge_keeps_scopes_separate_and_respects_top_k(self):
        many = PolicySearchResult([scored(f"local:{i}", 1 - i / 100) for i in range(5)], [])
        search = ScriptedSearch({"월세 지원": many, "월세가 부담돼요": many})
        outcome = run_search(analysis(), search, REGION, None, "월세가 부담돼요")
        self.assertEqual(len(outcome.local_policies), 3)  # 판정을 안 쓰면 범위별 기본 3개
        self.assertEqual(outcome.national_policies, [])

    def test_empty_result_is_rescued_once_with_relaxed_limit(self):
        found = PolicySearchResult([scored("local:A", 0.44)], [])
        search = ScriptedSearch({"월세 지원": found}, limit_hides_all=True)
        # 기본 하한 호출은 빈 결과 → 완화(0.60) 호출에서 결과가 나온다
        search.calls = []
        outcome = run_search(analysis(), search, REGION, None, "월세가 부담돼요")
        self.assertTrue(outcome.rescued)
        self.assertEqual([p.policy_id for p in outcome.local_policies], ["local:A"])
        limits = [kwargs.get("max_distance") for _, kwargs in search.calls]
        self.assertEqual(limits[:2], [0.55, 0.55])  # 첫 시도(두 검색어) — 상황형 하한
        self.assertEqual(limits[2:], [0.60, 0.60])  # 완화한 두 번째 시도
        self.assertEqual(len(limits), 4)  # 더 이상 반복하지 않는다

    def test_rescue_runs_for_judged_searches_and_the_judge_decides(self):
        found = PolicySearchResult([scored("local:A", 0.44), scored("local:B", 0.40)], [])
        search = ScriptedSearch({"월세 지원": found}, limit_hides_all=True)
        outcome = run_search(analysis(), search, REGION, None, "월세가 부담돼요", FakeJudge(relevant_ids={"local:B"}))
        self.assertTrue(outcome.rescued)
        self.assertTrue(outcome.relevance_checked)
        self.assertEqual([p.policy_id for p in outcome.local_policies], ["local:B", "local:A"])
        self.assertEqual(outcome.low_relevance_ids, ["local:A"])

    def test_no_rescue_when_nothing_is_found_even_with_the_relaxed_limit(self):
        search = ScriptedSearch({})
        outcome = run_search(analysis(), search, REGION, None, "오늘 날씨 어때", FakeJudge())
        self.assertFalse(outcome.rescued)
        self.assertEqual((outcome.local_policies, outcome.national_policies), ([], []))
        self.assertEqual(outcome.low_relevance_ids, [])  # 후보가 없으면 판정할 것도 없다(실제 판정기는 빈 목록에 Gemini를 부르지 않는다)

    def test_no_rescue_for_other_routes(self):
        search = ScriptedSearch({}, limit_hides_all=True)
        outcome = run_search(analysis("specific_policy"), search, REGION, None, "청년월세 지원사업")
        self.assertFalse(outcome.rescued)
        self.assertEqual(len(search.calls), 1)

    def test_no_rescue_when_the_first_search_already_has_results(self):
        found = PolicySearchResult([scored("local:A", 0.6)], [])
        search = ScriptedSearch({"월세 지원": found})
        outcome = run_search(analysis(), search, REGION, None, "월세가 부담돼요")
        self.assertFalse(outcome.rescued)
        self.assertEqual(len(search.calls), 2)  # 두 검색어만, 완화 재검색 없음


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
