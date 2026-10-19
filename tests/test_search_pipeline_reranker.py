import unittest
from dataclasses import replace

from app.models import PolicyCandidate, PolicySearchResult, QuestionAnalysis, RegionSelection
from app.relevance_judge import POOL_PER_SCOPE
from app.search_pipeline import DEFAULT_TOP_K, run_search
from app.search_profiles import RERANK_POOL_PER_SCOPE

REGION = RegionSelection(level1="서울특별시", level2="관악구")


def candidate(policy_id: str, source: str) -> PolicyCandidate:
    return PolicyCandidate(
        policy_id=policy_id, title=policy_id, region_text="", score=1.0, distance=0.3,
        scope="시군구" if source == "local" else "중앙부처", summary="", metadata={"source": source},
    )


def analysis(route: str = "situation_search") -> QuestionAnalysis:
    return QuestionAnalysis(
        route=route, policy_name=None, search_query="월세 지원", intent="policy_search",
        intents=["policy_search"], requested_sections=["candidate_summary"],
        include_keywords=[], exclude_keywords=[], confidence=0.9,
    )


class FakeSearch:
    def __init__(self, local=0, national=0):
        self.pool = PolicySearchResult(
            local_policies=[candidate(f"local:{i}", "local") for i in range(local)],
            national_policies=[candidate(f"national:{i}", "national") for i in range(national)],
        )
        self.calls = []

    def search_policies(self, question, region, **kwargs):
        self.calls.append(kwargs)
        return self.pool


class ReverseReranker:
    """뒤에 있는 후보일수록 점수가 높다고 보는 가짜 리랭커."""

    def __init__(self, error=None):
        self.error, self.queries = error, []

    def rerank(self, question, candidates):
        self.queries.append(question)
        if self.error:
            raise self.error
        return [replace(c, reranker_score=float(i)) for i, c in enumerate(reversed(candidates))]


class FakeJudge:
    def judge(self, question, search_query, candidates, age=None):
        return {c.policy_id: True for c in candidates}


class RerankerPipelineTest(unittest.TestCase):
    def test_situation_search_widens_pool_and_reorders_by_reranker(self):
        search, reranker = FakeSearch(local=5, national=4), ReverseReranker()
        outcome = run_search(analysis(), search, REGION, 24, "q", reranker=reranker)
        self.assertEqual(search.calls[0]["local_top_k"], RERANK_POOL_PER_SCOPE)
        self.assertEqual(reranker.queries, ["월세 지원"])
        # 판정기가 없으면 범위별 기본 개수만 남고, 리랭커 순서(역순)를 따른다
        self.assertEqual([p.policy_id for p in outcome.local_policies], ["local:4", "local:3", "local:2"][:DEFAULT_TOP_K])
        self.assertTrue(all(p.policy_id.startswith("national:") for p in outcome.national_policies))
        self.assertFalse(outcome.relevance_checked)

    def test_pool_size_follows_reranker_but_not_below_judge_pool(self):
        small = ReverseReranker()
        small.pool_per_scope = 5
        search = FakeSearch(local=3)
        run_search(analysis(), search, REGION, 24, "q", reranker=small)
        self.assertEqual(search.calls[0]["local_top_k"], POOL_PER_SCOPE)
        large = ReverseReranker()
        large.pool_per_scope = 40
        search = FakeSearch(local=3)
        run_search(analysis(), search, REGION, 24, "q", reranker=large)
        self.assertEqual(search.calls[0]["local_top_k"], 40)

    def test_scopes_are_not_mixed(self):
        outcome = run_search(analysis(), FakeSearch(local=2, national=2), REGION, 24, "q", reranker=ReverseReranker())
        self.assertTrue(all(p.metadata["source"] == "local" for p in outcome.local_policies))
        self.assertTrue(all(p.metadata["source"] == "national" for p in outcome.national_policies))

    def test_reranker_output_feeds_judge_with_pool_limit(self):
        outcome = run_search(
            analysis(), FakeSearch(local=20), REGION, 24, "q", judge=FakeJudge(), reranker=ReverseReranker()
        )
        self.assertTrue(outcome.relevance_checked)
        self.assertEqual(len(outcome.local_policies), POOL_PER_SCOPE)
        self.assertEqual(outcome.local_policies[0].policy_id, "local:19")

    def test_reranker_failure_falls_back_to_distance_order(self):
        outcome = run_search(
            analysis(), FakeSearch(local=5), REGION, 24, "q", reranker=ReverseReranker(error=RuntimeError("boom"))
        )
        self.assertEqual([p.policy_id for p in outcome.local_policies], ["local:0", "local:1", "local:2"])

    def test_non_situation_route_skips_reranker(self):
        search, reranker = FakeSearch(local=5), ReverseReranker()
        outcome = run_search(analysis("specific_policy"), search, REGION, 24, "q", reranker=reranker)
        self.assertEqual(reranker.queries, [])
        self.assertNotIn("local_top_k", search.calls[0])
        self.assertEqual(len(outcome.local_policies), 5)

    def test_without_reranker_behavior_is_unchanged(self):
        search = FakeSearch(local=5)
        outcome = run_search(analysis(), search, REGION, 24, "q")
        self.assertNotIn("local_top_k", search.calls[0])
        self.assertEqual(len(outcome.local_policies), DEFAULT_TOP_K)  # 다중 검색어 병합이 기본 개수로 자른다(기존 동작)


if __name__ == "__main__":
    unittest.main()
