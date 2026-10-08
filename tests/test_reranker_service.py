import unittest

from app.models import PolicyCandidate
from app.reranker_service import RerankerService, build_reranker_text


def candidate(policy_id: str, summary: str) -> PolicyCandidate:
    return PolicyCandidate(
        policy_id=policy_id,
        title=policy_id,
        region_text="",
        score=0.5,
        distance=0.5,
        scope="중앙부처",
        summary=summary,
        metadata={"source": "national"},
    )


class FakeCrossEncoder:
    def __init__(self):
        self.calls = []

    def predict(self, pairs, **kwargs):
        self.calls.append((pairs, kwargs))
        return [0.1, 0.9]


class RerankerServiceTest(unittest.TestCase):
    def test_build_reranker_text_removes_region_and_life_cycle(self):
        summary = """정책명: 관악구 청년 월세 지원사업
지역·소관: 서울특별시 관악구
생애주기: 청년
개요: 청년의 주거비 부담 완화
대상·조건: 관악구 거주 청년
추가 설명입니다.
지원 내용: 월세 지원"""

        text = build_reranker_text(summary)

        self.assertIn("정책명: 관악구 청년 월세 지원사업", text)
        self.assertIn("개요: 청년의 주거비 부담 완화", text)
        self.assertIn("대상·조건: 관악구 거주 청년\n추가 설명입니다.", text)
        self.assertIn("지원 내용: 월세 지원", text)
        self.assertNotIn("지역·소관", text)
        self.assertNotIn("생애주기", text)

    def test_build_reranker_text_keeps_unstructured_summary(self):
        self.assertEqual(build_reranker_text("월세 지원"), "월세 지원")

    def test_scores_and_sorts_without_removing_candidates(self):
        model = FakeCrossEncoder()
        service = RerankerService(model=model, device="cpu", batch_size=4)
        result = service.rerank(
            "월세가 부담돼요",
            [candidate("A", "주거 상담"), candidate("B", "월세 지원")],
        )

        self.assertEqual([item.policy_id for item in result], ["B", "A"])
        self.assertEqual([item.reranker_score for item in result], [0.9, 0.1])
        self.assertEqual(len(result), 2)
        self.assertEqual(model.calls[0][0][1], ("월세가 부담돼요", "월세 지원"))
        self.assertEqual(model.calls[0][1]["batch_size"], 4)


if __name__ == "__main__":
    unittest.main()
