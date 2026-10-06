"""실제 ChromaDB와 임베딩 모델로 검색 흐름을 확인하는 smoke 테스트(Gemini는 호출하지 않는다).

모델 로딩에 수십 초 걸리고 로컬 모델 캐시·DB가 있어야 하므로 기본 실행에서는 건너뛴다.
실행: PowerShell에서  $env:WELFAREONE_REAL_TESTS="1"; python -m unittest tests.test_real_smoke -v
"""

import os
import unittest

from app.config import CHROMA_PATH
from app.models import RegionSelection

ENABLED = os.getenv("WELFAREONE_REAL_TESTS") == "1" and CHROMA_PATH.exists()


@unittest.skipUnless(ENABLED, "WELFAREONE_REAL_TESTS=1 이고 data/chroma가 있을 때만 실행")
class RealSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.repository import PolicyRepository
        from app.search_service import PolicySearchService

        cls.repository = PolicyRepository()
        cls.search = PolicySearchService(cls.repository)
        cls.region = RegionSelection(level1="서울특별시", level2="강남구")

    def test_collection_size_matches_contract(self):
        self.assertEqual(self.repository.count(), 11850)

    def test_regions_are_listed(self):
        regions = self.repository.list_regions()
        self.assertIn("서울특별시", regions)
        self.assertIn("강남구", regions["서울특별시"])

    def test_policy_meta_and_sections(self):
        policy_id = "local:WLF00005414"
        meta = self.repository.get_policy_meta(policy_id)
        self.assertEqual(meta["region_text"], "서울특별시 강남구")
        self.assertTrue(meta["title"])
        self.assertTrue(self.repository.get_policy_sections(policy_id))
        self.assertIsNone(self.repository.get_policy_meta("local:NOPE"))
        self.assertEqual(self.repository.get_policy_sections("local:NOPE"), [])

    def test_relevant_question_returns_candidates_within_distance_limit(self):
        result = self.search.search_policies("청년 월세 지원", self.region, age=28)
        candidates = result.local_policies + result.national_policies
        self.assertTrue(candidates)
        self.assertTrue(all(item.distance <= 0.60 for item in candidates))
        self.assertTrue(any("월세" in item.title for item in result.national_policies))

    def test_unrelated_question_returns_empty_lists(self):
        for question in ("zzzzqqq", "오늘 날씨 어때", "피자 맛집 추천해줘"):
            result = self.search.search_policies(question, self.region, age=28)
            self.assertEqual(result.local_policies, [], question)
            self.assertEqual(result.national_policies, [], question)


if __name__ == "__main__":
    unittest.main()
