"""검색 거리(distance) 분포를 측정해 search_service.MAX_DISTANCE 후보를 구한다. 읽기 전용(DB 수정 없음).

임베딩 모델이나 DB를 바꾼 뒤 하한(0.60)이 여전히 맞는지 확인할 때 실행한다.
    python scripts/measure_search_distance.py

평가 질문(data/evaluation/welfareone_rag_eval_280.csv)의 정답 정책 거리와, 무의미 질문의 최상위 거리를
비교해 하한 후보별 "정답 보존 수 / 무의미 질문에서 결과가 남는 수"를 출력한다.
질문 원문을 그대로 검색하므로 Gemini는 호출하지 않는다(운영에서는 Gemini가 다시 쓴 검색어가 들어간다).
"""

import csv
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import RegionSelection  # noqa: E402
from app.repository import PolicyRepository  # noqa: E402
from app.search_service import MAX_DISTANCE, PolicySearchService  # noqa: E402

EVAL_CSV = Path(__file__).resolve().parents[1] / "data" / "evaluation" / "welfareone_rag_eval_280.csv"
JUNK = ["zzzzqqq", "오늘 날씨 어때", "피자 맛집 추천해줘", "아이폰 가격이 얼마야", "주식 투자 방법 알려줘", "고양이 사료 추천", "축구 경기 결과"]
THRESHOLDS = [0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75]


def parse_region(text: str, regions: dict[str, list[str]]) -> RegionSelection:
    text = (text or "").strip()
    if text in regions:
        return RegionSelection(level1=text, level2="")
    parts = text.split(None, 1)
    if len(parts) == 2 and parts[0] in regions:
        return RegionSelection(level1=parts[0], level2=parts[1].strip())
    return RegionSelection(level1="서울특별시", level2="")


def main() -> None:
    repository = PolicyRepository()
    regions = repository.list_regions()
    service = PolicySearchService(repository)
    rows = list(csv.DictReader(EVAL_CSV.open(encoding="utf-8-sig")))

    def search_all(question, region, age):
        # 하한을 끄고 후보를 넉넉히 받아 거리만 본다
        return service.search_policies(question, region, age=age, local_top_k=50, national_top_k=50, max_distance=None)

    top3_distances = []
    for row in rows:
        region = parse_region(row["region"], regions)
        age = int(row["age"]) if row["age"].strip().isdigit() else None
        result = search_all(row["question"], region, age)
        policy_id = row["expected_policy_id"]
        scope = result.local_policies if policy_id.startswith("local:") else result.national_policies
        for rank, item in enumerate(scope[:3], start=1):
            if item.policy_id == policy_id:
                top3_distances.append(item.distance)
                break

    junk_top = []
    for question in JUNK:
        result = search_all(question, RegionSelection(level1="서울특별시", level2="강남구"), 28)
        junk_top.append(min((p.distance for p in result.local_policies + result.national_policies), default=1.0))

    ordered = sorted(top3_distances)
    print(f"평가 질문 {len(rows)}개 중 정답이 top3에 든 건 {len(ordered)}개")
    print(
        "정답 거리  중앙값 %.3f  p90 %.3f  p95 %.3f  최대 %.3f"
        % (statistics.median(ordered), ordered[int(len(ordered) * 0.9)], ordered[int(len(ordered) * 0.95)], ordered[-1])
    )
    print("무의미 질문 최상위 거리:", ", ".join(f"{d:.3f}" for d in junk_top))
    print(f"\n현재 MAX_DISTANCE = {MAX_DISTANCE}")
    print("하한   정답 보존          무의미 질문 중 결과가 남는 수")
    for t in THRESHOLDS:
        kept = sum(1 for d in ordered if d <= t)
        left = sum(1 for d in junk_top if d <= t)
        print(f"{t:.2f}   {kept}/{len(ordered)} ({100 * kept / len(ordered):.1f}%)   {left}/{len(JUNK)}")


if __name__ == "__main__":
    main()
