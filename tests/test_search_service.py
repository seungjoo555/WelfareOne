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
        # 6번째 값(선택)이 있으면 그 시군구 범위 질의에만 나온다: "강남구" = 시군구 범위, "" = 광역 범위
        text = str(where)
        if "region_level2" in text:
            scope_level2 = "강남구" if "'$eq': '강남구'" in text else ""
            rows = [item for item in rows if len(item) <= 5 or item[5] == scope_level2]
        return {
            "documents": [[item[4] if len(item) > 4 else "요약" for item in rows]],
            "metadatas": [[
                {"policy_id": pid, "title": title, "source": src, "region_text": "서울특별시 강남구"}
                for pid, title, src, *_ in rows
            ]],
            "distances": [[item[3] for item in rows]],
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


def local_ids(result):
    return [p.policy_id for p in result.local_policies]


class KeywordRerankTest(unittest.TestCase):
    def test_title_keyword_promotes_a_slightly_farther_candidate(self):
        service = make_service([
            ("local:A", "교통비 지원사업", "local", 0.40),
            ("local:B", "수도요금 감면", "local", 0.37),
        ])
        self.assertEqual(local_ids(service.search_policies("대중교통", REGION)), ["local:B", "local:A"])
        ranked = service.search_policies("대중교통", REGION, include_keywords=["교통비"])
        self.assertEqual(local_ids(ranked), ["local:A", "local:B"])
        self.assertIn("포함 키워드 교통비", ranked.local_policies[0].reasons)

    def test_body_match_counts_less_than_title_match(self):
        service = make_service([
            ("local:A", "정책 가", "local", 0.40, "월세 지원 내용"),
            ("local:B", "월세 정책", "local", 0.40, "다른 내용"),
        ])
        result = service.search_policies("질문", REGION, include_keywords=["월세"])
        self.assertEqual(local_ids(result), ["local:B", "local:A"])

    def test_generic_and_short_keywords_are_ignored(self):
        service = make_service([
            ("local:A", "지원사업 가", "local", 0.40),
            ("local:B", "다른 정책", "local", 0.38),
        ])
        result = service.search_policies("질문", REGION, include_keywords=["지원", "사업", "청년", "비", "복지 지원 사업"])
        self.assertEqual(local_ids(result), ["local:B", "local:A"])  # 순서가 바뀌지 않는다

    def test_phrases_are_split_into_words(self):
        service = make_service([
            ("local:A", "정책 가", "local", 0.40),
            ("local:B", "산후조리원 운영", "local", 0.42),
        ])
        result = service.search_policies("질문", REGION, include_keywords=["산후조리원 비용"])
        self.assertEqual(local_ids(result), ["local:B", "local:A"])

    def test_exclude_keyword_demotes_but_keeps_the_candidate(self):
        service = make_service([
            ("local:A", "출산 진료비 지원", "local", 0.35),
            ("local:B", "산후조리 지원", "local", 0.38),
        ])
        result = service.search_policies("질문", REGION, exclude_keywords=["진료비"])
        self.assertEqual(local_ids(result), ["local:B", "local:A"])
        self.assertIn("제외 키워드 진료비", result.local_policies[1].reasons)

    def test_keywords_never_remove_candidates(self):
        items = [("local:A", "가", "local", 0.3), ("local:B", "나", "local", 0.4), ("national:C", "다", "national", 0.5)]
        service = make_service(items)
        plain = service.search_policies("질문", REGION)
        with_kw = service.search_policies("질문", REGION, include_keywords=["없는단어"], exclude_keywords=["가", "나"])
        self.assertEqual(len(with_kw.local_policies), len(plain.local_policies))
        self.assertEqual(len(with_kw.national_policies), len(plain.national_policies))

    def test_distance_limit_still_applies_with_keywords(self):
        service = make_service([("local:A", "월세 지원", "local", MAX_DISTANCE + 0.05)])
        result = service.search_policies("질문", REGION, include_keywords=["월세"])
        self.assertEqual(result.local_policies, [])


class RegionBonusScaleTest(unittest.TestCase):
    """시군구 가산점(+0.60)이 거리를 덮는 문제: region_bonus_scale=0이면 거리순으로 정렬한다."""

    ITEMS = [
        ("local:DISTRICT", "강남구 정책", "local", 0.55, "요약", "강남구"),  # 시군구 범위, 거리가 멀다
        ("local:METRO", "서울 정책", "local", 0.40, "요약", ""),  # 광역 범위, 거리가 가깝다
    ]

    def test_default_keeps_district_policies_first(self):
        result = make_service(self.ITEMS).search_policies("질문", REGION)
        self.assertEqual(local_ids(result), ["local:DISTRICT", "local:METRO"])
        self.assertEqual([p.scope for p in result.local_policies], ["시군구", "광역"])

    def test_zero_scale_orders_by_distance(self):
        result = make_service(self.ITEMS).search_policies("질문", REGION, region_bonus_scale=0.0)
        self.assertEqual(local_ids(result), ["local:METRO", "local:DISTRICT"])


if __name__ == "__main__":
    unittest.main()
