import json
import unittest
from types import SimpleNamespace

from app.models import PolicyCandidate, QuestionAnalysis, QuestionExclusion, RegionSelection
from app.relevance_service import (
    RelevanceService,
    RelevanceValidationError,
    candidate_validation_payload,
)


def candidate(policy_id: str, title: str, source: str = "local") -> PolicyCandidate:
    return PolicyCandidate(
        policy_id=policy_id,
        title=title,
        region_text="서울특별시 관악구" if source == "local" else "",
        score=0.5,
        distance=0.5,
        scope="시군구" if source == "local" else "중앙부처",
        summary=(
            f"정책명: {title}\n"
            "지역·소관: 서울특별시 관악구\n"
            "생애주기: 청년\n"
            "개요: 의료비 부담을 줄이는 정책\n"
            "대상·조건: 저소득 가구\n"
            "지원 내용: 본인부담 의료비 지원"
        ),
        metadata={"source": source},
        reranker_score=0.3,
    )


def analysis() -> QuestionAnalysis:
    return QuestionAnalysis(
        route="situation_search",
        policy_name=None,
        search_query="대출이 아닌 청년 월세 직접 지원",
        intent="policy_search",
        intents=["policy_search"],
        include_keywords=["월세"],
        exclusions=[QuestionExclusion(concept="대출", evidence="대출안하고")],
    )


class FakeModels:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        payload = self.payloads.pop(0)
        return SimpleNamespace(parsed=payload, text=json.dumps(payload, ensure_ascii=False))


class RelevanceServiceTest(unittest.TestCase):
    def test_candidate_payload_keeps_only_validation_fields(self):
        payload = candidate_validation_payload(candidate("local:A", "의료비 지원"))
        self.assertEqual(payload["title"], "의료비 지원")
        self.assertEqual(payload["overview"], "의료비 부담을 줄이는 정책")
        self.assertEqual(payload["target_conditions"], "저소득 가구")
        self.assertEqual(payload["benefit"], "본인부담 의료비 지원")
        self.assertNotIn("생애주기", json.dumps(payload, ensure_ascii=False))

    def test_validates_all_candidates_in_one_call(self):
        models = FakeModels([{
            "results": [
                {"policy_id": "local:A", "relevance": "direct", "reason": "월세를 직접 지원합니다."},
                {"policy_id": "national:B", "relevance": "unrelated", "reason": "질문과 관계없습니다."},
            ]
        }])
        service = RelevanceService(client=SimpleNamespace(models=models), max_retries=1)
        result = service.validate_candidates(
            "대출안하고 월세 지원 받고 싶어",
            analysis(),
            RegionSelection("서울특별시", "관악구"),
            27,
            [candidate("local:A", "월세 지원"), candidate("national:B", "재무교육", "national")],
        )

        self.assertEqual(result.status, "verified")
        self.assertEqual([item.relevance for item in result.judgments], ["direct", "unrelated"])
        self.assertEqual(len(models.calls), 1)
        sent = json.loads(models.calls[0]["contents"])
        self.assertEqual(sent["user_need"]["exclusions"][0]["concept"], "대출")
        self.assertEqual(len(sent["candidates"]), 2)

    def test_missing_candidate_makes_whole_validation_fail(self):
        models = FakeModels([{
            "results": [
                {"policy_id": "local:A", "relevance": "direct", "reason": "직접 관련"},
            ]
        }])
        service = RelevanceService(client=SimpleNamespace(models=models), max_retries=1)
        with self.assertRaises(RelevanceValidationError):
            service.validate_candidates(
                "병원비 지원",
                analysis(),
                RegionSelection("서울특별시", "관악구"),
                27,
                [candidate("local:A", "의료비 지원"), candidate("national:B", "입원 지원", "national")],
            )


if __name__ == "__main__":
    unittest.main()
