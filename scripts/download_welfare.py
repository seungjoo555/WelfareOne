import argparse
import csv
import re
import time
import xml.etree.ElementTree as ET
from getpass import getpass
from pathlib import Path

import requests


SOURCES = {
    "local": {
        "base": "https://apis.data.go.kr/B554287/LocalGovernmentWelfareInformations",
        "list": "LcgvWelfarelist",
        "detail": "LcgvWelfaredetailed",
        "default_max_calls": 900,
    },
    "national": {
        "base": "https://apis.data.go.kr/B554287/NationalWelfareInformationsV001",
        "list": "NationalWelfarelistV001",
        "detail": "NationalWelfaredetailedV001",
        "default_max_calls": 90,
    },
}


class StopCollection(Exception):
    pass


def child_text(node, name):
    value = node.findtext(name)
    return value.strip() if value else ""


def save_csv(path, fieldnames, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", choices=SOURCES)
    parser.add_argument("--max-calls", type=int)
    args = parser.parse_args()

    config = SOURCES[args.source]
    max_calls = args.max_calls or config["default_max_calls"]
    api_key = getpass(f"{args.source} API 인증키: ").strip()
    if not api_key:
        raise SystemExit("인증키가 비어 있습니다.")

    output = Path("data") / "raw" / args.source
    list_dir = output / "list"
    detail_dir = output / "detail"
    list_dir.mkdir(parents=True, exist_ok=True)
    detail_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    calls = 0

    def request_xml(url, params):
        nonlocal calls

        for attempt in range(3):
            if calls >= max_calls:
                raise StopCollection("이번 실행의 호출 제한에 도달했습니다.")

            calls += 1

            try:
                response = session.get(
                    url,
                    params={"serviceKey": api_key, **params},
                    timeout=30,
                )
            except requests.RequestException:
                if attempt < 2:
                    time.sleep(2)
                    continue
                raise RuntimeError("네트워크 요청 실패") from None

            if response.status_code in (429, 500, 502, 503, 504):
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise RuntimeError(f"HTTP {response.status_code}")

            if response.status_code != 200:
                safe_body = response.text.replace(api_key, "[인증키 가림]")[:500]
                raise RuntimeError(f"HTTP {response.status_code}: {safe_body}")

            try:
                root = ET.fromstring(response.content)
            except ET.ParseError:
                raise RuntimeError("XML이 아닌 응답을 받았습니다.") from None

            result_code = root.findtext(".//resultCode")
            if result_code and result_code.strip() not in ("0", "00", "200"):
                if result_code.strip() == "22":
                    raise StopCollection("API 호출 한도에 도달했습니다.")
                if result_code.strip() == "23" and attempt < 2:
                    time.sleep(3)
                    continue
                raise RuntimeError(f"API 오류 코드 {result_code.strip()}")

            time.sleep(1)  # 너무 빠른 연속 호출 방지
            return response.content, root

        raise RuntimeError("요청 재시도 실패")

    list_url = f"{config['base']}/{config['list']}"
    detail_url = f"{config['base']}/{config['detail']}"

    policies = {}
    page = 1
    received_rows = 0

    try:
        # 1. 목록을 마지막 페이지까지 저장
        while True:
            page_file = list_dir / f"page_{page:05d}.xml"

            if page_file.exists():
                xml_bytes = page_file.read_bytes()
                root = ET.fromstring(xml_bytes)
            else:
                xml_bytes, root = request_xml(
                    list_url,
                    {
                        "callTp": "L",
                        "pageNo": page,
                        "numOfRows": 100,
                        "lifeArray": "004",  # 청년 생애주기 코드
                        **({"srchKeyCode": "003"} if args.source == "national" else {}),
                    },
                )
                page_file.write_bytes(xml_bytes)

            page_items = []
            # wantedDtl 또는 servList 노드 기준으로 탐색
            for node in root.findall(".//wantedDtl") or root.findall(".//servList") or root.iter():
                policy_id = child_text(node, "servId")
                title = child_text(node, "servNm")
                if policy_id and title:
                    page_items.append((policy_id, title))

            if not page_items:
                break

            for policy_id, title in page_items:
                policies[policy_id] = title

            received_rows += len(page_items)
            total_text = root.findtext(".//totalCount")
            total = int(total_text) if total_text and total_text.isdigit() else 0

            print(
                f"목록 {page}페이지: {len(page_items)}건 "
                f"(누적 {received_rows}건 / 전체 {total or '미확인'}건)"
            )

            if total and received_rows >= total:
                break

            page += 1

        if not policies:
            raise RuntimeError("목록에서 정책 ID를 찾지 못했습니다.")

        save_csv(
            output / "policy_ids.csv",
            ["servId", "servNm"],
            [
                {"servId": policy_id, "servNm": title}
                for policy_id, title in policies.items()
            ],
        )

        # 2. 목록에서 얻은 ID별 상세 XML 저장
        for index, (policy_id, title) in enumerate(policies.items(), start=1):
            if not re.fullmatch(r"[A-Za-z0-9_-]+", policy_id):
                print(f"[건너뜀] 잘못된 정책 ID: {policy_id!r}")
                continue

            detail_file = detail_dir / f"{policy_id}.xml"
            if detail_file.exists():
                continue

            try:
                xml_bytes, root = request_xml(
                    detail_url,
                    {"callTp": "D", "servId": policy_id},
                )
                
                # 중앙부처 XML 감싸기 구조를 고려해 모든 servId 텍스트 추출 후 포함 여부 검증
                returned_ids = [node.text.strip() for node in root.findall(".//servId") if node.text]

                if policy_id not in returned_ids:
                    raise RuntimeError(
                        f"상세 응답 ID 불일치: 요청={policy_id!r}, 응답={returned_ids!r}"
                    )

                detail_file.write_bytes(xml_bytes)
                print(f"상세 {index}/{len(policies)} 저장: {policy_id} {title}")

            except StopCollection:
                raise
            except RuntimeError as error:
                print(f"[실패] {policy_id}: {error}")

    except StopCollection as reason:
        print(f"\n수집 일시 중단: {reason}")
        print("나중에 같은 명령을 다시 실행하면 이어받습니다.")

    finally:
        if policies:
            status_rows = []
            for policy_id, title in policies.items():
                detail_file = detail_dir / f"{policy_id}.xml"
                status_rows.append({
                    "servId": policy_id,
                    "servNm": title,
                    "status": "완료" if detail_file.exists() else "미수집",
                })

            save_csv(
                output / "status.csv",
                ["servId", "servNm", "status"],
                status_rows,
            )

            done = sum(row["status"] == "완료" for row in status_rows)
            print(
                f"\n상세조회 완료: {done}/{len(status_rows)}건, "
                f"이번 실행 API 호출: {calls}회"
            )


if __name__ == "__main__":
    main()