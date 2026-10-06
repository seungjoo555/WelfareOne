"""FastAPI 라우터 테스트. 실제 DB·임베딩 모델·Gemini 없이 가짜 서비스로 응답 형식을 검증한다."""

import unittest

from fastapi.testclient import TestClient

from app.answer_service import AnswerGenerationError
from app.api import Services, create_app
from app.models import (
    AnswerResult,
    PolicyCandidate,
    PolicyResource,
    PolicySearchResult,
    PolicySection,
    QuestionAnalysis,
)
from app.question_analyzer import QuestionAnalysisError

REGIONS = {"경기도": ["성남시"], "세종특별자치시": []}


def candidate(policy_id: str, title: str, scope: str) -> PolicyCandidate:
    return PolicyCandidate(
        policy_id=policy_id,
        title=title,
        region_text="경기도 성남시" if policy_id.startswith("local") else "",
        score=1.2,
        distance=0.3,
        scope=scope,
        summary="정책명: " + title + "\n개요: 예시 개요",
        metadata={"source": policy_id.split(":")[0]},
        reasons=["벡터 유사도 0.700", f"검색 범위 {scope}"],
    )


class FakeRepository:
    def __init__(self):
        self.fail = False

    def get_policy_meta(self, policy_id):
        if policy_id != "local:EXAMPLE1":
            return None
        return {"title": "예시 지역 정책", "region_text": "경기도 성남시"}

    def get_policy_sections(self, policy_id):
        if self.fail:
            raise RuntimeError("chroma down")
        if policy_id != "local:EXAMPLE1":
            return []
        return [
            PolicySection("target_criteria", 0, "19~39세 청년"),
            PolicySection("target_criteria", 1, "성남시 거주"),
            PolicySection("application", 0, "온라인 신청"),
        ]


class FakeSearch:
    def __init__(self):
        self.calls = []
        self.empty = False

    def search_policies(self, question, region, age=None, **kwargs):
        self.calls.append((question, region, age))
        if self.empty:
            return PolicySearchResult()
        return PolicySearchResult(
            local_policies=[candidate("local:EXAMPLE1", "예시 지역 정책", "시군구")],
            national_policies=[candidate("national:EXAMPLE2", "예시 중앙 정책", "중앙부처")],
        )


class FakeAnalyzer:
    def __init__(self):
        self.route = "situation_search"
        self.error = None
        self.calls = []

    def analyze_question(self, question, current_policy_id=None, current_policy_title=None):
        self.calls.append((question, current_policy_id, current_policy_title))
        if self.error:
            raise self.error
        return QuestionAnalysis(
            route=self.route,
            policy_name=None,
            search_query="청년 " + question,
            intent="eligibility",
            intents=["eligibility", "application"],
            requested_sections=["target_criteria", "application", "administrative"],
        )


class FakeAnswers:
    def __init__(self):
        self.error = None
        self.calls = []

    def generate_answer(self, question, policy_id, contexts, requested_sections=None, policy_title=None):
        self.calls.append((question, policy_id, len(contexts), requested_sections, policy_title))
        if self.error:
            raise self.error
        return AnswerResult(
            answer="대상은 19~39세 청년입니다.",
            policy_id=policy_id,
            used_sections=["target_criteria"],
            evidence=["19~39세 청년"],
            resources=[PolicyResource(label="신청서", resource_type="attachment", url="https://example.com/a.hwp")],
            grounded=True,
        )


def llm_error(cls, code=None):
    """서비스가 실제로 하는 것처럼 원인 예외(APIError)를 __cause__에 붙여 만든다."""
    cause = RuntimeError("upstream")
    if code is not None:
        cause.code = code
    try:
        raise cls("실패") from cause
    except cls as exc:
        return exc


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.repo = FakeRepository()
        self.search = FakeSearch()
        self.analyzer = FakeAnalyzer()
        self.answers = FakeAnswers()
        services = Services(self.repo, self.search, self.analyzer, self.answers, REGIONS)
        # raise_server_exceptions=False: 예기치 못한 오류도 실제 서버처럼 500 응답으로 확인한다.
        self.client_cm = TestClient(create_app(services), raise_server_exceptions=False)
        self.client = self.client_cm.__enter__()
        self.addCleanup(self.client_cm.__exit__, None, None, None)

    def search_body(self, **overrides):
        body = {"question": "월세가 부담돼요", "region": {"level1": "경기도", "level2": "성남시"}, "age": 24}
        body.update(overrides)
        return body

    def assert_error(self, response, status, code):
        self.assertEqual(response.status_code, status, response.text)
        error = response.json()["error"]
        self.assertEqual(error["code"], code)
        self.assertIn("message", error)
        self.assertIn("details", error)

    # --- GET /health
    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    # --- GET /regions
    def test_regions(self):
        response = self.client.get("/regions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), REGIONS)

    # --- POST /policies/search
    def test_search_returns_analysis_and_separated_lists(self):
        response = self.client.post("/policies/search", json=self.search_body())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            data["analysis"],
            {"route": "situation_search", "intents": ["eligibility", "application"], "search_query": "청년 월세가 부담돼요"},
        )
        self.assertEqual([p["policy_id"] for p in data["local_policies"]], ["local:EXAMPLE1"])
        self.assertEqual([p["policy_id"] for p in data["national_policies"]], ["national:EXAMPLE2"])
        for key in ("policy_id", "title", "region_text", "score", "distance", "scope", "summary", "metadata", "reasons"):
            self.assertIn(key, data["local_policies"][0])

    def test_search_passes_search_query_region_and_age_to_service(self):
        self.client.post("/policies/search", json=self.search_body())
        question, region, age = self.search.calls[0]
        self.assertEqual(question, "청년 월세가 부담돼요")
        self.assertEqual((region.level1, region.level2, age), ("경기도", "성남시", 24))

    def test_search_without_level2_uses_empty_string(self):
        self.client.post("/policies/search", json=self.search_body(region={"level1": "세종특별자치시", "level2": None}, age=None))
        _, region, age = self.search.calls[0]
        self.assertEqual(region.level2, "")
        self.assertIsNone(age)

    def test_search_empty_result_is_not_an_error(self):
        self.search.empty = True
        response = self.client.post("/policies/search", json=self.search_body())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["local_policies"], [])
        self.assertEqual(response.json()["national_policies"], [])

    def test_search_invalid_region(self):
        for region in ({"level1": "없는도", "level2": ""}, {"level1": "경기도", "level2": "없는시"}):
            self.assert_error(
                self.client.post("/policies/search", json=self.search_body(region=region)), 400, "INVALID_REGION"
            )
        self.assertEqual(self.search.calls, [])

    def test_search_validation_errors(self):
        for body in (
            self.search_body(question="   "),
            self.search_body(question="가" * 501),
            self.search_body(age=121),
            self.search_body(age=-1),
            {"region": {"level1": "경기도"}},
        ):
            self.assert_error(self.client.post("/policies/search", json=body), 422, "INVALID_REQUEST")

    def test_search_llm_rate_limited(self):
        self.analyzer.error = llm_error(QuestionAnalysisError, code=429)
        self.assert_error(self.client.post("/policies/search", json=self.search_body()), 429, "LLM_RATE_LIMITED")

    def test_search_llm_invalid_response(self):
        self.analyzer.error = llm_error(QuestionAnalysisError)
        self.assert_error(self.client.post("/policies/search", json=self.search_body()), 502, "LLM_RESPONSE_INVALID")

    def test_unexpected_error_becomes_internal_error(self):
        def boom(*args, **kwargs):
            raise RuntimeError("boom")

        self.search.search_policies = boom
        with self.assertLogs("welfareone.api", level="ERROR"):
            response = self.client.post("/policies/search", json=self.search_body())
        self.assert_error(response, 500, "INTERNAL_ERROR")

    # --- GET /policies/{policy_id}
    def test_policy_detail_groups_sections(self):
        response = self.client.get("/policies/local%3AEXAMPLE1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["policy_id"], "local:EXAMPLE1")
        self.assertEqual(data["sections"]["target_criteria"], ["19~39세 청년", "성남시 거주"])
        self.assertEqual(data["sections"]["application"], ["온라인 신청"])
        self.assertEqual(data["title"], "예시 지역 정책")
        self.assertEqual(data["region_text"], "경기도 성남시")

    def test_policy_detail_not_found(self):
        self.assert_error(self.client.get("/policies/local%3AMISSING"), 404, "POLICY_NOT_FOUND")

    def test_policy_detail_database_error(self):
        self.repo.fail = True
        with self.assertLogs("welfareone.api", level="ERROR"):
            response = self.client.get("/policies/local%3AEXAMPLE1")
        self.assert_error(response, 500, "DATABASE_ERROR")

    # --- POST /policies/{policy_id}/ask
    def test_ask_returns_answer_for_current_policy(self):
        self.analyzer.route = "current_policy_question"
        response = self.client.post(
            "/policies/local%3AEXAMPLE1/ask", json={"question": "대상이 어떻게 되나요?", "policy_title": "예시 지역 정책"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["route"], "current_policy_question")
        self.assertEqual(data["intents"], ["eligibility", "application"])
        answer = data["answer"]
        for key in ("answer", "policy_id", "used_sections", "evidence", "resources", "grounded"):
            self.assertIn(key, answer)
        self.assertEqual(answer["resources"][0], {"label": "신청서", "resource_type": "attachment", "url": "https://example.com/a.hwp"})
        # 질문 분석에는 현재 정책 정보가, 답변 생성에는 분석이 만든 섹션 목록이 전달된다.
        self.assertEqual(self.analyzer.calls[0], ("대상이 어떻게 되나요?", "local:EXAMPLE1", "예시 지역 정책"))
        self.assertEqual(self.answers.calls[0][3], ["target_criteria", "application", "administrative"])

    def test_ask_other_route_returns_null_answer_without_generating(self):
        self.analyzer.route = "situation_search"
        response = self.client.post("/policies/local%3AEXAMPLE1/ask", json={"question": "오늘 날씨", "policy_title": None})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["route"], "situation_search")
        self.assertIsNone(response.json()["answer"])
        self.assertEqual(self.answers.calls, [])

    def test_ask_policy_not_found(self):
        self.assert_error(self.client.post("/policies/local%3AMISSING/ask", json={"question": "안녕"}), 404, "POLICY_NOT_FOUND")

    def test_ask_answer_generation_errors(self):
        self.analyzer.route = "current_policy_question"
        for code, status, expected in ((429, 429, "LLM_RATE_LIMITED"), (None, 502, "LLM_RESPONSE_INVALID")):
            self.answers.error = llm_error(AnswerGenerationError, code=code)
            self.assert_error(self.client.post("/policies/local%3AEXAMPLE1/ask", json={"question": "신청 방법"}), status, expected)


VALID_KEY = "AIzaSyExampleKey-0123456789_abcdefghij"


class ByokTest(unittest.TestCase):
    """사용자 키(X-Gemini-Api-Key) 처리. 서버 키 폴백이 꺼진 상태(analyzer/answers=None)를 기본으로 본다."""

    def setUp(self):
        self.analyzer = FakeAnalyzer()
        self.answers = FakeAnswers()
        self.made_with = []

        def analyzer_factory(key):
            self.made_with.append(("analyzer", key))
            return self.analyzer

        def answers_factory(key):
            self.made_with.append(("answers", key))
            return self.answers

        self.services = Services(
            FakeRepository(), FakeSearch(), None, None, REGIONS,
            analyzer_factory=analyzer_factory, answers_factory=answers_factory,
        )
        self.client_cm = TestClient(create_app(self.services), raise_server_exceptions=False)
        self.client = self.client_cm.__enter__()
        self.addCleanup(self.client_cm.__exit__, None, None, None)

    BODY = {"question": "월세가 부담돼요", "region": {"level1": "경기도", "level2": "성남시"}, "age": 24}

    def code_of(self, response):
        return response.json()["error"]["code"]

    def test_search_without_key_is_rejected_when_server_key_is_off(self):
        response = self.client.post("/policies/search", json=self.BODY)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.code_of(response), "API_KEY_REQUIRED")
        self.assertEqual(self.analyzer.calls, [])

    def test_ask_without_key_is_rejected_when_server_key_is_off(self):
        response = self.client.post("/policies/local%3AEXAMPLE1/ask", json={"question": "대상이 어떻게 되나요?"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.code_of(response), "API_KEY_REQUIRED")

    def test_search_uses_the_key_from_header_and_never_echoes_it(self):
        response = self.client.post("/policies/search", json=self.BODY, headers={"X-Gemini-Api-Key": VALID_KEY})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.made_with, [("analyzer", VALID_KEY)])
        self.assertNotIn(VALID_KEY, response.text)

    def test_ask_builds_both_services_with_the_header_key(self):
        self.analyzer.route = "current_policy_question"
        response = self.client.post(
            "/policies/local%3AEXAMPLE1/ask", json={"question": "대상이 어떻게 되나요?"},
            headers={"X-Gemini-Api-Key": VALID_KEY},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.made_with, [("analyzer", VALID_KEY), ("answers", VALID_KEY)])
        self.assertNotIn(VALID_KEY, response.text)

    def test_malformed_key_is_rejected_before_any_service_is_built(self):
        for bad in ("short", "a" * 300, "AIza has space inside 0123456789"):
            response = self.client.post("/policies/search", json=self.BODY, headers={"X-Gemini-Api-Key": bad})
            self.assertEqual(response.status_code, 401, bad)
            self.assertEqual(self.code_of(response), "INVALID_API_KEY")
        self.assertEqual(self.made_with, [])

    def test_server_key_is_used_when_no_header_and_fallback_is_on(self):
        services = Services(FakeRepository(), FakeSearch(), self.analyzer, self.answers, REGIONS)
        with TestClient(create_app(services), raise_server_exceptions=False) as client:
            self.assertEqual(client.post("/policies/search", json=self.BODY).status_code, 200)

    def test_gemini_rejecting_the_key_maps_to_invalid_api_key(self):
        for code, message in ((401, "unauthorized"), (403, "permission denied"), (400, "API key not valid. Please pass a valid API key.")):
            cause = RuntimeError(message)
            cause.code = code
            try:
                raise QuestionAnalysisError("실패") from cause
            except QuestionAnalysisError as exc:
                self.analyzer.error = exc
            response = self.client.post("/policies/search", json=self.BODY, headers={"X-Gemini-Api-Key": VALID_KEY})
            self.assertEqual(response.status_code, 401, (code, response.text))
            self.assertEqual(self.code_of(response), "INVALID_API_KEY")

    def test_other_bad_request_from_gemini_is_not_reported_as_key_error(self):
        cause = RuntimeError("Invalid JSON payload")
        cause.code = 400
        try:
            raise QuestionAnalysisError("실패") from cause
        except QuestionAnalysisError as exc:
            self.analyzer.error = exc
        response = self.client.post("/policies/search", json=self.BODY, headers={"X-Gemini-Api-Key": VALID_KEY})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.code_of(response), "LLM_RESPONSE_INVALID")


if __name__ == "__main__":
    unittest.main()
