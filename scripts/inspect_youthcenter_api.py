"""온통청년 정책 API를 소량 호출해 응답 형식과 지역 정책을 조사한다.

현재 공식 API(`current`)와 이전 getPlcy API(`legacy`)를 모두 지원한다.
기존 ChromaDB와 원본 복지서비스 데이터는 수정하지 않는다.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import requests


APIS = {
    "current": {
        "url": "https://www.youthcenter.go.kr/opi/youthPlcyList.do",
        "key": "openApiVlak",
    },
    "legacy": {
        "url": "https://www.youthcenter.go.kr/go/ythip/getPlcy",
        "key": "apiKeyNm",
    },
}

NAME_FIELDS = ("plcyNm", "polyBizSjnm", "정책명", "title")
ID_FIELDS = ("plcyNo", "bizId", "policyId", "id")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="온통청년 API 소량 조사")
    parser.add_argument(
        "--api", choices=APIS, default="current", help="호출할 API 형식"
    )
    parser.add_argument("--query", default="광진구", help="검색어")
    parser.add_argument("--page", type=int, default=1, help="페이지 번호")
    parser.add_argument("--display", type=int, default=20, help="페이지당 건수")
    parser.add_argument(
        "--all-pages", action="store_true", help="마지막 페이지까지 모두 조회"
    )
    parser.add_argument(
        "--region-code",
        default="",
        help="시군구 코드(광진구는 11215). 단일 지역 정책 판별에 사용",
    )
    parser.add_argument(
        "--delay", type=float, default=2.0, help="페이지 호출 사이 대기 시간(초)"
    )
    return parser.parse_args()


def get_key() -> str:
    key = os.getenv("YOUTHCENTER_API_KEY", "").strip()
    while not key:
        key = input("온통청년 API 키를 붙여 넣고 Enter를 누르세요: ").strip()
        if not key:
            print("API 키가 비어 있습니다. 다시 입력해 주세요.")
    return key


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def request_policy_page(
    api: str, key: str, query: str, page: int, display: int
) -> requests.Response:
    config = APIS[api]
    if api == "current":
        params = {
            config["key"]: key,
            "pageIndex": page,
            "display": display,
            "query": query,
        }
    else:
        params = {
            config["key"]: key,
            "pageType": 1,
            "pageNum": page,
            "pageSize": display,
            "rtnType": "json",
            # 이전 API는 별도 검색 파라미터가 명확하지 않아 받은 뒤 문자열로 거른다.
        }

    # 온통청년 서버가 간혹 API 요청을 HTTP 8080 포트로 잘못 보내므로
    # 자동 리다이렉트를 막고 원래 응답을 진단한다.
    response: requests.Response | None = None
    retry_waits = (5, 10, 20, 30, 45)
    for attempt in range(1, 7):
        response = requests.get(
            config["url"],
            params=params,
            timeout=40,
            allow_redirects=False,
            headers={
                "Accept": "application/json, application/xml, text/xml;q=0.9, */*;q=0.8",
                "User-Agent": "Mozilla/5.0 WelfareOne-API-Inspector/1.0",
            },
        )
        error_code = ""
        if response.status_code == 400:
            try:
                error_code = str(response.json().get("errorCode", ""))
            except (ValueError, AttributeError):
                pass
        retryable = response.status_code in (429, 500, 502, 503, 504) or (
            response.status_code == 400 and error_code == "E002"
        )
        if not retryable or attempt == 6:
            break
        wait = retry_waits[attempt - 1]
        label = f"HTTP {response.status_code}"
        if error_code:
            label += f" {error_code}"
        print(f"API {label} 응답: {wait}초 후 재시도 ({attempt}/6)")
        time.sleep(wait)

    assert response is not None
    if 300 <= response.status_code < 400:
        location = response.headers.get("Location", "(Location 없음)")
        raise RuntimeError(
            f"온통청년 서버 리다이렉트 오류: HTTP {response.status_code}, "
            f"Location={location!r}. API 서버가 정상 HTTPS 응답 대신 다른 주소로 "
            "보내고 있습니다."
        )
    if response.status_code != 200:
        safe_body = response.text.replace(key, "[API 키 가림]")[:1000]
        raise RuntimeError(f"HTTP {response.status_code}: {safe_body}")
    return response


def xml_to_value(element: ET.Element) -> Any:
    children = list(element)
    if not children:
        return (element.text or "").strip()
    grouped: dict[str, list[Any]] = {}
    for child in children:
        grouped.setdefault(child.tag, []).append(xml_to_value(child))
    return {
        key: values[0] if len(values) == 1 else values
        for key, values in grouped.items()
    }


def parse_response(response: requests.Response) -> tuple[str, Any]:
    text = response.text.lstrip("\ufeff \t\r\n")
    content_type = response.headers.get("Content-Type", "").lower()
    if "json" in content_type or text.startswith(("{", "[")):
        return "json", response.json()
    if "xml" in content_type or text.startswith("<"):
        return "xml", xml_to_value(ET.fromstring(response.content))
    raise RuntimeError(
        f"JSON/XML이 아닌 응답입니다. Content-Type={content_type!r}, "
        f"앞부분={text[:300]!r}"
    )


def parse_saved_response(path: Path) -> tuple[str, Any]:
    if path.suffix.lower() == ".json":
        return "json", json.loads(path.read_text(encoding="utf-8"))
    if path.suffix.lower() == ".xml":
        return "xml", xml_to_value(ET.parse(path).getroot())
    raise RuntimeError(f"지원하지 않는 저장 응답 파일입니다: {path}")


def walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def first_text(record: dict[str, Any], fields: tuple[str, ...]) -> str:
    for field in fields:
        value = record.get(field)
        if value is not None and not isinstance(value, (dict, list)):
            text = str(value).strip()
            if text:
                return text
    return ""


def find_policy_records(value: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in walk_dicts(value):
        title = first_text(item, NAME_FIELDS)
        policy_id = first_text(item, ID_FIELDS)
        if not title:
            continue
        signature = (policy_id, title)
        if signature in seen:
            continue
        seen.add(signature)
        records.append(item)
    return records


def searchable_text(record: dict[str, Any]) -> str:
    chunks: list[str] = []
    for value in record.values():
        if value is not None and not isinstance(value, (dict, list)):
            chunks.append(str(value))
    return " ".join(chunks)


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    scalar_fields: list[str] = []
    for record in records:
        for key, value in record.items():
            if key not in scalar_fields and not isinstance(value, (dict, list)):
                scalar_fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=scalar_fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(record)


def legacy_paging(value: Any) -> tuple[int, int, int]:
    if not isinstance(value, dict):
        return 0, 0, 0
    paging = value.get("result", {}).get("pagging", {})
    try:
        return (
            int(paging.get("totCount", 0)),
            int(paging.get("pageNum", 0)),
            int(paging.get("pageSize", 0)),
        )
    except (TypeError, ValueError):
        return 0, 0, 0


def region_match(record: dict[str, Any], query: str, region_code: str) -> str:
    """정책이 특정 자치구 전용인지 또는 텍스트에서 지역이 확인되는지 판별."""
    zip_codes = [code.strip() for code in str(record.get("zipCd", "")).split(",")]
    zip_codes = [code for code in zip_codes if code]
    if region_code and zip_codes == [region_code]:
        return "district_code_only"
    # 신청 장소·협력업체 주소에 지역명이 나온 경우는 관할 정책이 아니다.
    identity_fields = (
        "plcyNm",
        "sprvsnInstCdNm",
        "operInstCdNm",
        "rgtrInstCdNm",
        "rgtrUpInstCdNm",
        "rgtrHghrkInstCdNm",
    )
    identity_text = " ".join(str(record.get(field, "")) for field in identity_fields)
    if query and query in identity_text:
        return "region_name_in_identity"
    return ""


def main() -> None:
    args = parse_args()
    if args.page < 1 or args.display < 1:
        raise SystemExit("--page와 --display는 1 이상이어야 합니다.")

    key = get_key()
    output = project_root() / "data" / "investigation" / "youthcenter"
    output.mkdir(parents=True, exist_ok=True)

    all_records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    page = args.page
    total_count = 0
    response_type = ""
    last_parsed_path: Path | None = None

    while True:
        cached_json = output / f"{args.api}_page_{page:05d}.json"
        cached_xml = output / f"{args.api}_page_{page:05d}.xml"
        cached_path = cached_json if cached_json.exists() else cached_xml
        if args.all_pages and cached_path.exists():
            response_type, parsed = parse_saved_response(cached_path)
            raw_path = cached_path
            from_cache = True
        else:
            response = request_policy_page(args.api, key, args.query, page, args.display)
            response_type, parsed = parse_response(response)
            raw_path = output / f"{args.api}_page_{page:05d}.{response_type}"
            raw_path.write_bytes(response.content)
            from_cache = False
        parsed_path = output / f"{args.api}_page_{page:05d}_parsed.json"
        parsed_path.write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        last_parsed_path = parsed_path

        page_records = find_policy_records(parsed)
        for record in page_records:
            policy_id = first_text(record, ID_FIELDS)
            if policy_id and policy_id in seen_ids:
                continue
            if policy_id:
                seen_ids.add(policy_id)
            all_records.append(record)

        if args.api == "legacy":
            total_count, _, page_size = legacy_paging(parsed)
        else:
            page_size = args.display
        print(
            f"{page}페이지{'(저장본)' if from_cache else ''}: {len(page_records)}건 "
            f"(누적 {len(all_records)}건 / 전체 {total_count or '미확인'}건)"
        )

        if not args.all_pages:
            break
        if not page_records:
            break
        if total_count and len(all_records) >= total_count:
            break
        if len(page_records) < (page_size or args.display):
            break
        page += 1
        if not from_cache:
            time.sleep(max(args.delay, 0.0))

    report_records: list[dict[str, Any]] = []
    for record in all_records:
        match_type = region_match(record, args.query, args.region_code)
        if match_type:
            report_records.append({"region_match_type": match_type, **record})

    suffix = "all" if args.all_pages else f"page_{args.page:05d}"
    csv_path = output / f"{args.api}_{args.query}_{suffix}.csv"
    write_csv(csv_path, report_records)

    all_jsonl = output / f"{args.api}_all_policies.jsonl"
    if args.all_pages:
        with all_jsonl.open("w", encoding="utf-8") as file:
            for record in all_records:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"HTTP 상태: 200")
    print(f"응답 형식: {response_type.upper()}")
    print(f"찾은 정책 레코드: {len(all_records)}건")
    print(f"'{args.query}' 관련 저장 레코드: {len(report_records)}건")
    for index, record in enumerate(report_records[:10], start=1):
        print(
            f"{index}. {first_text(record, NAME_FIELDS)} "
            f"[{first_text(record, ID_FIELDS) or 'ID 미확인'}]"
        )
    print(f"마지막 구조 확인 JSON: {last_parsed_path}")
    if args.all_pages:
        print(f"전체 정책 JSONL: {all_jsonl}")
    print(f"검토용 CSV: {csv_path}")


if __name__ == "__main__":
    try:
        main()
    except (requests.RequestException, ET.ParseError, ValueError, RuntimeError) as exc:
        print(f"실행 실패: {exc}", file=sys.stderr)
        raise SystemExit(1)
