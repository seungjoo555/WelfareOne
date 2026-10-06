"""지자체 복지서비스 전체 목록을 내려받아 특정 지역의 누락 여부를 조사한다.

기존 ``data/raw`` 및 ChromaDB는 수정하지 않는다. 모든 결과는
``data/investigation/local_all`` 아래에 저장한다.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests


LIST_URL = (
    "https://apis.data.go.kr/B554287/LocalGovernmentWelfareInformations/"
    "LcgvWelfarelist"
)
DETAIL_URL = (
    "https://apis.data.go.kr/B554287/LocalGovernmentWelfareInformations/"
    "LcgvWelfaredetailed"
)
SESSION = requests.Session()

YOUTH_HINTS = (
    "청년",
    "대학생",
    "취업준비생",
    "취준생",
    "사회초년생",
    "구직청년",
    "청년층",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="생애주기 필터 없이 지자체 복지서비스를 조사합니다."
    )
    parser.add_argument("--region1", default="서울특별시", help="조사할 시도")
    parser.add_argument("--region2", default="광진구", help="조사할 시군구")
    parser.add_argument("--rows", type=int, default=100, help="목록 페이지당 건수")
    parser.add_argument(
        "--details",
        action="store_true",
        help="선택 지역의 모든 정책을 상세조회합니다. 생략하면 목록만 받습니다.",
    )
    parser.add_argument(
        "--reuse-list",
        action="store_true",
        help="이미 저장한 전체 목록 XML을 재사용하고 API 목록 호출을 생략합니다.",
    )
    parser.add_argument(
        "--delay", type=float, default=0.4, help="상세조회 호출 사이 대기 시간(초)"
    )
    parser.add_argument(
        "--max-details",
        type=int,
        default=None,
        help="이번 실행에서 새로 상세조회할 최대 건수",
    )
    return parser.parse_args()


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_service_key() -> str:
    key = os.getenv("DATA_GO_KR_SERVICE_KEY", "").strip()
    while not key:
        # Windows 터미널에서 getpass에 붙여 넣은 값이 빈 값으로 처리되는 경우가
        # 있어 일반 입력을 사용한다. 입력 후 Enter를 누를 때까지 기다린다.
        key = input("공공데이터포털 서비스키를 붙여 넣고 Enter를 누르세요: ").strip()
        if not key:
            print("서비스키가 비어 있습니다. 다시 입력해 주세요.")
    # Encoding 키를 붙여 넣어도 urlencode가 이중 인코딩하지 않도록 먼저 해제한다.
    return urllib.parse.unquote(key)


def request_xml(url: str, params: dict[str, object], retries: int = 4) -> bytes:
    last_error: Exception | None = None
    service_key = str(params.get("serviceKey", ""))

    for attempt in range(1, retries + 1):
        try:
            response = SESSION.get(
                url,
                params=params,
                headers={"User-Agent": "WelfareOne-data-inspector/1.0"},
                timeout=40,
            )
            if response.status_code in (429, 500, 502, 503, 504):
                raise RuntimeError(f"HTTP {response.status_code}")
            if response.status_code != 200:
                safe_body = response.text.replace(service_key, "[인증키 가림]")[:500]
                raise RuntimeError(f"HTTP {response.status_code}: {safe_body}")

            root = ET.fromstring(response.content)
            result_code = (root.findtext(".//resultCode") or "").strip()
            result_message = (root.findtext(".//resultMessage") or "").strip()
            if result_code and result_code not in ("0", "00", "200"):
                raise RuntimeError(f"API 오류 {result_code}: {result_message}")
            time.sleep(0.5)
            return response.content
        except (requests.RequestException, ET.ParseError, RuntimeError) as exc:
            last_error = exc
            if attempt == retries:
                break
            wait = attempt * 3
            print(f"요청 실패({attempt}/{retries}): {exc} - {wait}초 후 재시도")
            time.sleep(wait)

    raise RuntimeError(f"API 요청에 실패했습니다: {last_error}")


def element_to_dict(element: ET.Element) -> dict[str, str]:
    result: dict[str, str] = {}
    for child in element:
        text = " ".join("".join(child.itertext()).split())
        if text:
            result[child.tag] = text
    return result


def load_saved_list(list_dir: Path) -> list[dict[str, str]]:
    paths = sorted(list_dir.glob("page_*.xml"))
    if not paths:
        raise SystemExit(f"재사용할 목록 XML이 없습니다: {list_dir}")

    records: list[dict[str, str]] = []
    for path in paths:
        root = ET.parse(path).getroot()
        records.extend(element_to_dict(item) for item in root.findall(".//servList"))
    return records


def download_all_list(
    service_key: str, list_dir: Path, rows: int
) -> list[dict[str, str]]:
    list_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, str]] = []
    page = 1
    total_count: int | None = None

    while total_count is None or len(records) < total_count:
        body = request_xml(
            LIST_URL,
            {
                "serviceKey": service_key,
                "callTp": "L",
                "pageNo": page,
                "numOfRows": rows,
                # lifeArray를 보내지 않아 전체 생애주기를 요청한다.
            },
        )
        root = ET.fromstring(body)
        if total_count is None:
            total_count = int((root.findtext("totalCount") or "0").strip())
            print(f"API 전체 목록 건수: {total_count}")

        items = [element_to_dict(item) for item in root.findall(".//servList")]
        (list_dir / f"page_{page:05d}.xml").write_bytes(body)
        records.extend(items)
        print(f"목록 {min(len(records), total_count)}/{total_count}건 저장")

        if not items:
            break
        page += 1

    return records


def youth_flags(record: dict[str, str]) -> tuple[bool, list[str]]:
    life_cycle = record.get("lifeNmArray", "")
    searchable = " ".join(
        record.get(field, "")
        for field in ("servNm", "servDgst", "bizChrDeptNm", "trgterIndvdlNmArray")
    )
    hints = [hint for hint in YOUTH_HINTS if hint in searchable]
    return "청년" in life_cycle, hints


def write_jsonl(path: Path, records: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_region_csv(path: Path, records: list[dict[str, str]]) -> None:
    columns = [
        "servId",
        "servNm",
        "ctpvNm",
        "sggNm",
        "lifeNmArray",
        "has_youth_lifecycle",
        "youth_text_hints",
        "servDgst",
        "trgterIndvdlNmArray",
        "intrsThemaNmArray",
        "aplyMtdNm",
        "lastModYmd",
        "servDtlLink",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            has_youth, hints = youth_flags(record)
            writer.writerow(
                {
                    **record,
                    "has_youth_lifecycle": "Y" if has_youth else "N",
                    "youth_text_hints": "|".join(hints),
                }
            )


def download_region_details(
    service_key: str,
    records: list[dict[str, str]],
    detail_dir: Path,
    delay: float,
    max_details: int | None,
) -> tuple[int, int]:
    detail_dir.mkdir(parents=True, exist_ok=True)
    completed = 0
    failed = 0
    newly_requested = 0

    for index, record in enumerate(records, start=1):
        service_id = record.get("servId", "").strip()
        if not service_id:
            continue
        output = detail_dir / f"{service_id}.xml"
        if output.exists() and output.stat().st_size > 0:
            completed += 1
            continue
        if max_details is not None and newly_requested >= max_details:
            print(f"--max-details {max_details}에 도달하여 중단합니다.")
            break

        try:
            body = request_xml(
                DETAIL_URL,
                {
                    "serviceKey": service_key,
                    "callTp": "D",
                    "servId": service_id,
                },
            )
            output.write_bytes(body)
            completed += 1
            newly_requested += 1
            print(f"상세 {index}/{len(records)} 저장: {service_id}")
        except Exception as exc:  # 실패 ID를 건너뛰고 나머지를 계속 받는다.
            failed += 1
            print(f"상세조회 실패: {service_id} - {exc}", file=sys.stderr)
        time.sleep(max(delay, 0.0))

    return completed, failed


def main() -> None:
    args = parse_args()
    if args.rows <= 0:
        raise SystemExit("--rows는 1 이상이어야 합니다.")

    output_root = project_root() / "data" / "investigation" / "local_all"
    list_dir = output_root / "list"
    region_slug = f"{args.region1}_{args.region2}".replace(" ", "_")
    region_dir = output_root / "regions" / region_slug
    region_dir.mkdir(parents=True, exist_ok=True)

    service_key = get_service_key()
    if args.reuse_list:
        all_records = load_saved_list(list_dir)
        print(f"저장된 전체 목록 {len(all_records)}건을 재사용합니다.")
    else:
        all_records = download_all_list(service_key, list_dir, args.rows)

    write_jsonl(output_root / "all_policies.jsonl", all_records)
    region_records = [
        record
        for record in all_records
        if record.get("ctpvNm", "").strip() == args.region1
        and record.get("sggNm", "").strip() == args.region2
    ]
    report_path = region_dir / "policies.csv"
    write_region_csv(report_path, region_records)

    youth_lifecycle_count = sum(youth_flags(record)[0] for record in region_records)
    youth_hint_count = sum(bool(youth_flags(record)[1]) for record in region_records)
    print()
    print(f"조사 지역: {args.region1} {args.region2}")
    print(f"지역 정책: {len(region_records)}건")
    print(f"생애주기에 청년 포함: {youth_lifecycle_count}건")
    print(f"목록 텍스트에 청년 관련 표현 포함: {youth_hint_count}건")
    print(f"검토용 CSV: {report_path}")

    details_completed = 0
    details_failed = 0
    if args.details and region_records:
        details_completed, details_failed = download_region_details(
            service_key,
            region_records,
            region_dir / "detail",
            args.delay,
            args.max_details,
        )
        print(f"상세 저장 완료: {details_completed}건 / 실패: {details_failed}건")

    manifest = {
        "collected_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": "Korea Social Security Information Service local welfare API",
        "list_url": LIST_URL,
        "detail_url": DETAIL_URL,
        "list_filter": "none",
        "all_record_count": len(all_records),
        "region_level1": args.region1,
        "region_level2": args.region2,
        "region_record_count": len(region_records),
        "region_youth_lifecycle_count": youth_lifecycle_count,
        "region_youth_text_hint_count": youth_hint_count,
        "details_requested": args.details,
        "details_completed": details_completed,
        "details_failed": details_failed,
    }
    (region_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
