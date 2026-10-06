import unittest

from app.question_analyzer import QuestionAnalyzer, _GeminiAnalysis


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
