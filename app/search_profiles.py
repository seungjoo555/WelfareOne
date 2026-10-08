"""질문 유형(route)별 검색 설정. 기존 검색 함수는 건드리지 않고 호출할 때 넘길 인자만 정한다.

배경(2026-10-06 측정, 상황형·구어체 질문 15개, 후보 판정은 Gemini):
- 기본 거리 하한 0.60은 "정책명을 아는 질문"(평가 질문 280개)에 맞춘 값이라 상황형 질문에는 느슨하다.
  0.60에서 상위 후보의 정밀도는 지자체 29%, 중앙부처 42%였다. 0.55로 줄이면 각각 46%, 45%(관련 재현율 91%, 98%).
- 시군구 가산점(+0.60)이 거리를 덮어, 거리가 먼 시군구 정책이 가까운 광역 정책보다 위로 올라왔다.
  가산점을 없애고 거리순으로 정렬하면 지자체 정밀도가 30% → 48%(하한 0.60 기준)였다.
정책명을 말한 질문(specific_policy)과 후속 질문은 기존 값(하한 0.60, 지역 가산점 1.0)을 그대로 쓴다.
값은 표본이 작은 측정 결과이므로 `scripts/measure_search_distance.py` 등으로 다시 확인한다.
"""

# 상황형 질문의 거리 하한. 이 안에서도 SITUATION_CONFIDENT_DISTANCE보다 먼 후보는 화면에서 접어 둔다.
SITUATION_MAX_DISTANCE = 0.55
# 상황형 질문의 후보가 하한 때문에 전부 사라졌을 때만 쓰는 완화된 하한(기본 하한과 같은 값).
# 2026-10-08 측정: "자격증관련 정책 알려줘"의 1위가 0.56이라 하한 0.55에서 빈 결과였고, 0.60에서는 정상 결과가 나왔다.
# 무의미 질문(날씨·피자 맛집·zzzzqqq)은 0.60에서도 빈 결과였다.
SITUATION_RESCUE_MAX_DISTANCE = 0.60
# 시군구/광역 가산점을 곱하는 비율. 0이면 지자체 후보를 거리(와 키워드)만으로 정렬한다.
SITUATION_REGION_BONUS_SCALE = 0.0
# 프런트 `src/utils/relevance.ts`의 LOW_RELEVANCE_DISTANCE와 같은 값이어야 한다(기본으로 보여 줄 관련도 기준).
SITUATION_CONFIDENT_DISTANCE = 0.50


def search_options(route: str | None) -> dict[str, float]:
    """search_policies()에 넘길 추가 인자. 상황형 질문이 아니면 비어 있어 기본값이 쓰인다."""
    if route == "situation_search":
        return {
            "max_distance": SITUATION_MAX_DISTANCE,
            "region_bonus_scale": SITUATION_REGION_BONUS_SCALE,
        }
    return {}
