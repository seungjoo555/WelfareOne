"""사람 라벨링용 후보 시트를 만든다(읽기 전용: DB는 수정하지 않고, 질문 분석에 Gemini를 호출한다).

    python scripts/make_labeling_sheet.py --order A,B,C

입력  data/evaluation/situational_questions.csv  (양식: situational_questions_template.csv)
출력  data/evaluation/labeling/
        sheet_<라벨러>.csv          라벨러에게 줄 시트(점수·거리·순위 숨김, 후보 순서 섞음)
        labeling_key_PRIVATE.csv    정답 키(거리·점수·범위·순위). 라벨러에게 주거나 커밋하지 않는다.

배정 규칙(--order A,B,C): 작성자의 질문은 순서상 앞 사람이 라벨링한다(B의 질문 → A, C의 질문 → B, A의 질문 → C).
질문 3개 중 1개는 나머지 한 사람도 라벨링해 일치도를 잰다. 작성자는 자기 질문을 라벨링하지 않는다.
작성자 이름이 입력 파일의 author 열과 같아야 한다. author가 "예시"인 행은 건너뛴다.
Gemini 429를 피하려고 질문마다 --sleep초(기본 5초) 쉰다.
"""

import argparse
import csv
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import RegionSelection  # noqa: E402
from app.question_analyzer import QuestionAnalyzer  # noqa: E402
from app.repository import PolicyRepository  # noqa: E402
from app.search_profiles import search_options  # noqa: E402
from app.search_service import PolicySearchService  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "data" / "evaluation"
PER_SCOPE = 6  # 지자체 6 + 중앙부처 6 = 질문당 최대 12개
SUMMARY_CHARS = 300
URL_PATTERN = re.compile(r"https?://[^\s)\]]+")
SHEET_COLUMNS = ["row_id", "question_id", "질문", "지역", "나이", "정책명", "요약", "원문 링크", "점수(0/1/2)", "대상한정(✔)", "메모"]
KEY_COLUMNS = ["row_id", "question_id", "policy_id", "scope", "rank_in_scope", "distance", "score", "route", "search_query"]


def read_questions(path: Path, regions: dict[str, list[str]]) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        source_rows = list(csv.DictReader(handle))
    rows = []
    for line_no, row in enumerate(source_rows, start=2):
        if (row.get("author") or "").strip() in ("", "예시"):
            continue
        level1, level2 = row["region_level1"].strip(), (row.get("region_level2") or "").strip()
        if level1 not in regions or (level2 and level2 not in regions[level1]):
            sys.exit(f"{path.name} {line_no}행: 지역 '{level1} {level2}'이(가) DB 지역 목록에 없습니다.")
        age = (row.get("age") or "").strip()
        if age and not age.isdigit():
            sys.exit(f"{path.name} {line_no}행: 나이는 숫자만 쓰세요: '{age}'")
        if not row["question"].strip():
            sys.exit(f"{path.name} {line_no}행: 질문이 비어 있습니다.")
        rows.append({**row, "region": RegionSelection(level1=level1, level2=level2), "age": int(age) if age else None})
    return rows


def assign_labelers(questions: list[dict], order: list[str]) -> dict[str, list[dict]]:
    """질문별 라벨러 목록을 정해 라벨러별 질문 목록으로 돌려준다."""
    by_author: dict[str, int] = {}
    result: dict[str, list[dict]] = {name: [] for name in order}
    for q in questions:
        author = q["author"].strip()
        if author not in order:
            sys.exit(f"작성자 '{author}'이(가) --order {','.join(order)}에 없습니다.")
        idx = by_author.get(author, 0)
        by_author[author] = idx + 1
        position = order.index(author)
        primary = order[position - 1]
        labelers = [primary]
        if idx % 3 == 0 and len(order) >= 3:  # 3개 중 1개는 한 명 더 라벨링
            labelers.append(order[(position + 1) % len(order)])
        for name in labelers:
            result[name].append(q)
    return result


def first_url(repository: PolicyRepository, policy_id: str) -> str:
    for section in repository.get_policy_sections(policy_id):
        if section.section in ("contact_source", "overview"):
            match = URL_PATTERN.search(section.document)
            if match:
                return match.group(0)
    return ""


def candidate_summary(summary: str) -> str:
    """요약에서 정책명 줄을 빼고 개요·대상·지원 내용을 한 줄로 만든다."""
    lines = [line.strip() for line in summary.splitlines() if line.strip() and not line.startswith("정책명")]
    text = " / ".join(lines)
    return text if len(text) <= SUMMARY_CHARS else text[:SUMMARY_CHARS] + "…"


def build_candidates(questions, analyzer, service, repository, sleep: float):
    """질문별 후보를 (행 정보, 키 정보)로 만든다. 같은 질문은 한 번만 분석한다."""
    built: dict[str, list[tuple[dict, dict]]] = {}
    for q in questions:
        qid = q["id"].strip()
        analysis = analyzer.analyze_question(q["question"].strip())
        result = service.search_policies(
            analysis.search_query,
            q["region"],
            age=q["age"],
            local_top_k=PER_SCOPE,
            national_top_k=PER_SCOPE,
            include_keywords=analysis.include_keywords,
            exclude_keywords=analysis.exclude_keywords,
            **search_options(analysis.route),
        )
        region_text = " ".join(part for part in (q["region"].level1, q["region"].level2) if part)
        items = []
        for scope_name, policies in (("local", result.local_policies), ("national", result.national_policies)):
            for rank, policy in enumerate(policies, start=1):
                sheet = {
                    "question_id": qid,
                    "질문": q["question"].strip(),
                    "지역": region_text,
                    "나이": q["age"] if q["age"] is not None else "",
                    "정책명": policy.title,
                    "요약": candidate_summary(policy.summary),
                    "원문 링크": first_url(repository, policy.policy_id),
                    "점수(0/1/2)": "",
                    "대상한정(✔)": "",
                    "메모": "",
                }
                key = {
                    "question_id": qid,
                    "policy_id": policy.policy_id,
                    "scope": scope_name,
                    "rank_in_scope": rank,
                    "distance": round(policy.distance, 4),
                    "score": round(policy.score, 4),
                    "route": analysis.route,
                    "search_query": analysis.search_query,
                }
                items.append((sheet, key))
        built[qid] = items
        print(f"{qid}: 후보 {len(items)}개 (route={analysis.route})", flush=True)
        time.sleep(sleep)
    return built


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--questions", type=Path, default=EVAL_DIR / "situational_questions.csv")
    parser.add_argument("--out-dir", type=Path, default=EVAL_DIR / "labeling")
    parser.add_argument("--order", default="A,B,C", help="작성자 이름 순서(쉼표 구분). 입력 파일의 author와 같아야 함")
    parser.add_argument("--sleep", type=float, default=5.0)
    parser.add_argument("--seed", type=int, default=0, help="후보 섞는 순서의 seed")
    args = parser.parse_args()

    order = [name.strip() for name in args.order.split(",") if name.strip()]
    repository = PolicyRepository()
    questions = read_questions(args.questions, repository.list_regions())
    if not questions:
        sys.exit("라벨링할 질문이 없습니다(author가 '예시'인 행은 건너뜁니다).")
    ids = [q["id"].strip() for q in questions]
    if len(set(ids)) != len(ids):
        sys.exit("질문 id가 중복됩니다.")

    built = build_candidates(questions, QuestionAnalyzer(), PolicySearchService(repository), repository, args.sleep)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    key_rows: dict[tuple[str, str], dict] = {}
    for name, assigned in assign_labelers(questions, order).items():
        rows = []
        for q in assigned:
            qid = q["id"].strip()
            items = list(built[qid])
            random.Random(f"{args.seed}:{qid}").shuffle(items)  # 라벨러마다 같은 질문은 같은 순서(대조가 쉬움)
            for number, (sheet, key) in enumerate(items, start=1):
                row_id = f"{qid}-{number:02d}"
                rows.append({"row_id": row_id, **sheet})
                key_rows[(qid, row_id)] = {"row_id": row_id, **key}
        write_csv(args.out_dir / f"sheet_{name}.csv", SHEET_COLUMNS, rows)
        print(f"sheet_{name}.csv: 질문 {len(assigned)}개, 행 {len(rows)}개")

    write_csv(args.out_dir / "labeling_key_PRIVATE.csv", KEY_COLUMNS, sorted(key_rows.values(), key=lambda r: r["row_id"]))
    print(f"labeling_key_PRIVATE.csv: {len(key_rows)}행 (라벨러에게 주지 말 것, 커밋 금지)")


if __name__ == "__main__":
    main()
