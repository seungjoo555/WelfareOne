import unittest

from app.answer_service import (
    AnswerService,
    _GeminiAnswer,
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


if __name__ == "__main__":
    unittest.main()
