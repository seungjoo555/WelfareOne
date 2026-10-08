import unittest

from app.answer_service import (
    INTENT_ANSWER_GUIDE,
    AnswerService,
    _GeminiAnswer,
    _build_contents,
    answer_guide,
    extract_resources,
    select_contexts,
)
from app.models import PolicySection


class AnswerServiceTest(unittest.TestCase):
    def setUp(self):
        self.contexts = [
            PolicySection(
                section="benefit",
                chunk_index=0,
                document="월 최대 20만원을 지원합니다.",
            ),
            PolicySection(
                section="application",
                chunk_index=0,
                document="관할 주민센터에서 방문 신청합니다.",
            ),
            PolicySection(
                section="contact_source",
                chunk_index=0,
                document="문의처는 복지정책과입니다.",
            ),
        ]

    def test_selects_only_requested_sections(self):
        selected = select_contexts(
            self.contexts,
            ["benefit", "application"],
        )
        self.assertEqual(
            [item.section for item in selected],
            ["benefit", "application"],
        )

    def test_result_keeps_only_available_sections_and_verbatim_evidence(self):
        parsed = _GeminiAnswer(
            answer="월 최대 20만원을 지원하며 주민센터에서 신청합니다.",
            used_sections=["benefit", "application", "documents"],
            evidence=[
                "월 최대 20만원을 지원합니다.",
                "원문에 없는 근거",
            ],
            grounded=True,
        )

        result = AnswerService._to_result(parsed, "local:TEST", self.contexts)

        self.assertEqual(result.used_sections, ["benefit", "application"])
        self.assertEqual(result.evidence, ["월 최대 20만원을 지원합니다."])
        self.assertTrue(result.grounded)

    def test_unsupported_evidence_cannot_be_grounded(self):
        parsed = _GeminiAnswer(
            answer="확인할 수 없습니다.",
            used_sections=["benefit"],
            evidence=["원문에 없는 근거"],
            grounded=True,
        )

        result = AnswerService._to_result(parsed, "local:TEST", self.contexts)

        self.assertFalse(result.grounded)
        self.assertEqual(result.evidence, [])

    def test_extracts_attachment_without_relying_on_llm(self):
        contexts = [
            PolicySection(
                section="documents",
                chunk_index=0,
                document=(
                    "wlfareInfoReldCn: https://example.go.kr/file?id=123&no=1\n"
                    "wlfareInfoReldNm: 청년지원 신청서.hwp"
                ),
            )
        ]

        resources = extract_resources(contexts)

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].label, "청년지원 신청서.hwp")
        self.assertEqual(resources[0].resource_type, "attachment")
        self.assertEqual(resources[0].url, "https://example.go.kr/file?id=123&no=1")

    def test_answer_can_use_application_but_return_document_resource(self):
        selected_contexts = [self.contexts[1]]
        all_contexts = [
            *self.contexts,
            PolicySection(
                section="documents",
                chunk_index=0,
                document=(
                    "wlfareInfoReldCn: https://example.go.kr/form.hwp\n"
                    "wlfareInfoReldNm: 신청서.hwp"
                ),
            ),
        ]
        parsed = _GeminiAnswer(
            answer="관할 주민센터에서 신청합니다.",
            used_sections=["application"],
            evidence=["관할 주민센터에서 방문 신청합니다."],
            grounded=True,
        )

        result = AnswerService._to_result(
            parsed,
            "local:TEST",
            selected_contexts,
            resource_contexts=all_contexts,
        )

        self.assertEqual(result.used_sections, ["application"])
        self.assertEqual(len(result.resources), 1)
        self.assertEqual(result.resources[0].label, "신청서.hwp")

class AnswerGuideTest(unittest.TestCase):
    contexts = [PolicySection(section="target_criteria", chunk_index=0, document="만 19~39세 청년")]

    def test_every_button_intent_has_a_guide(self):
        for intent in ("eligibility", "benefit", "application", "administrative", "required_documents", "contact"):
            self.assertIn(intent, INTENT_ANSWER_GUIDE)
            self.assertIn("[답변 구성]", answer_guide([intent]))

    def test_guide_lists_items_in_order(self):
        guide = answer_guide(["eligibility"])
        self.assertLess(guide.index("누가 대상인가"), guide.index("제외 대상"))
        self.assertLess(guide.index("제외 대상"), guide.index("신청 전에 확인할 점"))

    def test_multiple_intents_include_each_guide(self):
        guide = answer_guide(["eligibility", "application"])
        self.assertIn("지원 대상", guide)
        self.assertIn("신청 방법", guide)

    def test_unknown_or_missing_intents_add_nothing(self):
        self.assertEqual(answer_guide(None), "")
        self.assertEqual(answer_guide([]), "")
        self.assertEqual(answer_guide(["policy_search"]), "")

    def test_prompt_contains_guide_only_when_intents_are_given(self):
        base = _build_contents("대상이 어떻게 되나요?", "local:X", "예시 정책", self.contexts)
        self.assertNotIn("[답변 구성]", base)
        guided = _build_contents("대상이 어떻게 되나요?", "local:X", "예시 정책", self.contexts, ["eligibility"])
        self.assertIn("[답변 구성]", guided)
        # 원문 블록과 질문은 그대로 유지된다
        self.assertIn("공식 정책 원문:", guided)
        self.assertIn("사용자 질문: 대상이 어떻게 되나요?", guided)
        self.assertEqual(guided.replace(answer_guide(["eligibility"]) + "\n\n", ""), base)


if __name__ == "__main__":
    unittest.main()
