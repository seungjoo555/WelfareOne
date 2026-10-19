import unittest

from fake_llm import FakeLLM

from app.question_analyzer import (
    ANALYZER_SEED,
    SYSTEM_INSTRUCTION,
    QuestionAnalyzer,
    _GeminiAnalysis,
)


def _fake_client():
    return FakeLLM(
        [
            _GeminiAnalysis(
                route="situation_search",
                search_query="무료 급식 식사 지원",
                intent="policy_search",
                intents=["policy_search"],
                confidence=0.9,
            )
        ]
    )


class QuestionAnalyzerRequestTest(unittest.TestCase):
    """Gemini 요청 설정(seed)과 검색어 지침. 실제 API는 호출하지 않는다."""

    def make(self, **kwargs):
        analyzer = QuestionAnalyzer(api_key="x" * 24, **kwargs)
        analyzer.client = _fake_client()
        return analyzer

    def test_seed_is_fixed_by_default_to_keep_results_stable(self):
        analyzer = self.make()
        analyzer.analyze_question("배고파")
        call = analyzer.client.calls[0]
        self.assertEqual(call["seed"], ANALYZER_SEED)
        self.assertEqual(call["system"], SYSTEM_INSTRUCTION)

    def test_seed_can_be_disabled(self):
        analyzer = self.make(seed=None)
        analyzer.analyze_question("배고파")
        self.assertIsNone(analyzer.client.calls[0]["seed"])

    def test_instruction_tells_model_to_translate_colloquial_needs(self):
        # 구어체 질문("배고파")이 그대로 검색어가 되어 결과가 비는 문제를 막는 지침이 빠지지 않았는지 확인한다.
        for phrase in ("구어체", "배고파", "무료 급식 식사 지원", "점심 추천", "청년 복지 정책"):
            self.assertIn(phrase, SYSTEM_INSTRUCTION)


class QuestionAnalyzerMappingTest(unittest.TestCase):
    def test_documents_intent_maps_to_both_relevant_sections(self):
        parsed = _GeminiAnalysis(
            route="specific_policy",
            policy_name="청년 월세 지원",
            search_query="청년 월세 지원 필요 서류",
            intent="required_documents",
            intents=["required_documents"],
            include_keywords=["월세", "월세", "임대차계약서"],
            exclude_keywords=[],
            confidence=0.9,
        )

        result = QuestionAnalyzer._to_result(parsed, current_policy_id=None)

        self.assertEqual(result.requested_sections, ["documents", "application"])
        self.assertEqual(result.include_keywords, ["월세", "임대차계약서"])

    def test_followup_without_selected_policy_is_corrected(self):
        parsed = _GeminiAnalysis(
            route="current_policy_question",
            policy_name=None,
            search_query="청년 면접 비용 지원",
            intent="benefit",
            intents=["benefit"],
            confidence=0.8,
        )

        result = QuestionAnalyzer._to_result(parsed, current_policy_id=None)

        self.assertEqual(result.route, "situation_search")

    def test_followup_with_selected_policy_is_preserved(self):
        parsed = _GeminiAnalysis(
            route="current_policy_question",
            policy_name=None,
            search_query="신청 방법",
            intent="application",
            intents=["application"],
            confidence=0.95,
        )

        result = QuestionAnalyzer._to_result(
            parsed,
            current_policy_id="local:WLF00000001",
        )

        self.assertEqual(result.route, "current_policy_question")
        self.assertEqual(result.requested_sections, ["application", "administrative"])

    def test_multiple_intents_are_combined_without_duplicate_sections(self):
        parsed = _GeminiAnalysis(
            route="specific_policy",
            policy_name="관악구 청년 월세 지원사업",
            search_query="관악구 청년 월세 지원 금액 신청 방법",
            intent="benefit",
            intents=["benefit", "application"],
            confidence=0.97,
        )

        result = QuestionAnalyzer._to_result(parsed, current_policy_id=None)

        self.assertEqual(result.intent, "benefit")
        self.assertEqual(result.intents, ["benefit", "application"])
        self.assertEqual(
            result.requested_sections,
            ["benefit", "application", "administrative"],
        )

    def test_primary_intent_is_always_first(self):
        parsed = _GeminiAnalysis(
            route="specific_policy",
            policy_name="관악구 청년 월세 지원사업",
            search_query="관악구 청년 월세 지원 자격 서류",
            intent="eligibility",
            intents=["required_documents", "eligibility"],
            confidence=0.8,
        )

        result = QuestionAnalyzer._to_result(parsed, current_policy_id=None)

        self.assertEqual(result.intents, ["eligibility", "required_documents"])
        self.assertEqual(
            result.requested_sections,
            ["target_criteria", "documents", "application"],
        )

    def test_application_form_link_always_includes_documents(self):
        parsed = _GeminiAnalysis(
            route="current_policy_question",
            policy_name=None,
            search_query="신청서 링크",
            intent="application",
            intents=["application", "contact"],
            confidence=0.9,
        )

        result = QuestionAnalyzer._to_result(
            parsed,
            current_policy_id="local:WLF00006125",
            question="신청서 링크줘",
        )

        self.assertEqual(
            result.intents,
            ["application", "contact", "required_documents"],
        )
        self.assertIn("documents", result.requested_sections)


if __name__ == "__main__":
    unittest.main()
