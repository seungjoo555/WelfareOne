import unittest

from app.models import RegionSelection
from app.search_service import MAX_DISTANCE, PolicySearchService


class FakeEmbedder:
    def encode(self, *args, **kwargs):
        class Vector:
            def tolist(self):
                return [0.0]

        return Vector()


class FakeRepository:
    """scope마다 같은 후보 목록을 돌려주는 가짜 저장소. items = [(policy_id, title, source, distance)]"""

    def __init__(self, items):
        self.items = items

    def vector_query(self, query_vector, where, limit):
        source = "national" if "national" in str(where) else "local"
        rows = [item for item in self.items if item[2] == source]
        return {
            "documents": [["요약" for _ in rows]],
            "metadatas": [[
                {"policy_id": pid, "title": title, "source": src, "region_text": "서울특별시 강남구"}
                for pid, title, src, _ in rows
            ]],
            "distances": [[distance for _, _, _, distance in rows]],
        }


def make_service(items):
    service = PolicySearchService.__new__(PolicySearchService)  # 임베딩 모델 로드를 건너뛴다
    service.repository = FakeRepository(items)
    service.embedder = FakeEmbedder()
    return service


REGION = RegionSelection(level1="서울특별시", level2="강남구")


class DistanceLimitTest(unittest.TestCase):
    def test_far_candidates_are_dropped_and_list_is_not_padded(self):
        service = make_service([
            ("local:A", "청년 월세 지원", "local", 0.30),
            ("local:B", "보훈위문금 지급", "local", MAX_DISTANCE + 0.01),
            ("national:C", "주거안정 월세대출", "national", 0.45),
            ("national:D", "어업활동지원", "national", 0.80),
        ])
        result = service.search_policies("월세가 부담돼요", REGION)
        self.assertEqual([p.policy_id for p in result.local_policies], ["local:A"])
        self.assertEqual([p.policy_id for p in result.national_policies], ["national:C"])

    def test_candidate_exactly_at_limit_is_kept(self):
        service = make_service([("local:A", "청년 월세 지원", "local", MAX_DISTANCE)])
        result = service.search_policies("월세", REGION)
        self.assertEqual(len(result.local_policies), 1)

    def test_nothing_relevant_returns_empty_lists(self):
        service = make_service([
            ("local:A", "보훈위문금 지급", "local", 0.85),
            ("national:B", "어업활동지원", "national", 0.77),
        ])
        result = service.search_policies("오늘 날씨 어때", REGION)
        self.assertEqual(result.local_policies, [])
        self.assertEqual(result.national_policies, [])

    def test_full_title_match_is_exempt_from_limit(self):
        service = make_service([("local:A", "청년 월세 지원사업", "local", 0.85)])
        result = service.search_policies("청년 월세 지원사업 알려줘", REGION)
        self.assertEqual([p.policy_id for p in result.local_policies], ["local:A"])

    def test_partial_title_match_is_not_exempt(self):
        service = make_service([("local:A", "청년 월세 한시 특별지원", "local", 0.85)])
        result = service.search_policies("월세 알려줘", REGION)
        self.assertEqual(result.local_policies, [])

    def test_max_distance_none_disables_limit(self):
        service = make_service([("local:A", "보훈위문금 지급", "local", 0.85)])
        result = service.search_policies("오늘 날씨 어때", REGION, max_distance=None)
        self.assertEqual(len(result.local_policies), 1)


if __name__ == "__main__":
    unittest.main()
