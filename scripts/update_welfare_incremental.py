"""복지로 공개 API에서 "새로 생기거나 바뀐 정책"만 다시 수집한다. (DB 재적재는 하지 않는다.)

    python scripts/update_welfare_incremental.py local            # 점검만(기본): 목록만 받아 바뀐 정책을 알려 준다
    python scripts/update_welfare_incremental.py local --apply    # 바뀐 정책의 상세 XML만 받아 data/raw에 반영한다
    python scripts/update_welfare_incremental.py national --apply

기존 download_welfare.py는 이미 받은 목록·상세 파일이 있으면 다시 받지 않아 갱신을 알 수 없다. 이 스크립트는 다음처럼 바뀐 것을 찾는다.
- local(지자체): 목록의 lastModYmd(최종 수정일)가 내려받아 둔 상세 XML의 lastModYmd와 다르면 갱신 대상. 목록에 없던 ID는 신규.
- national(중앙부처): 목록·상세 어디에도 수정일이 없어서 모든 상세를 다시 받아 내용이 달라졌는지 비교한다.
  (호출 수가 많아 하루 한도를 넘으면 update_state.json에 진행 상황을 남기고 다음 실행에서 이어받는다.)

원칙
- 쓰는 곳은 data/raw/<source>/ 뿐이다. data/chroma는 읽지도 쓰지도 않는다.
- 바뀐 상세 XML은 덮어쓰기 전에 data/raw/<source>/detail_prev/<날짜>/에 옛 파일을 옮겨 둔다.
- 목록에서 사라진 정책은 보고만 하고 파일을 지우지 않는다.
- 인증키는 환경변수 또는 프로젝트 .env(WELFARE_API_KEY_LOCAL / WELFARE_API_KEY_NATIONAL), 없으면 입력 프롬프트로만 받고, 출력·파일에 남기지 않는다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from getpass import getpass
from pathlib import Path
from typing import Callable

SOURCES = {
    "local": {
        "base": "https://apis.data.go.kr/B554287/LocalGovernmentWelfareInformations",
        "list": "LcgvWelfarelist",
        "detail": "LcgvWelfaredetailed",
        "default_max_calls": 900,
        "key_env": "WELFARE_API_KEY_LOCAL",
    },
    "national": {
        "base": "https://apis.data.go.kr/B554287/NationalWelfareInformationsV001",
        "list": "NationalWelfarelistV001",
        "detail": "NationalWelfaredetailedV001",
        "default_max_calls": 90,
        "key_env": "WELFARE_API_KEY_NATIONAL",
    },
}
ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+")


class QuotaReached(Exception):
    """이번 실행의 호출 제한이나 API 일일 한도에 도달했다. 이어받기 가능."""


# ------------------------------------------------------------------ 순수 로직 (네트워크 없음, 테스트 대상)


@dataclass
class ListEntry:
    policy_id: str
    title: str
    last_mod: str = ""  # YYYYMMDD. 중앙부처 목록에는 없다.


def parse_list(xml_bytes: bytes) -> list[ListEntry]:
    """목록 페이지 XML에서 정책 ID·이름·최종 수정일을 읽는다."""
    root = ET.fromstring(xml_bytes)
    entries = []
    for node in root.findall(".//servList"):
        policy_id = (node.findtext("servId") or "").strip()
        title = (node.findtext("servNm") or "").strip()
        if policy_id and title:
            entries.append(ListEntry(policy_id, title, (node.findtext("lastModYmd") or "").strip()))
    return entries


def detail_last_mod(path: Path) -> str | None:
    """내려받아 둔 상세 XML의 최종 수정일. 파일이 없으면 None, 필드가 없으면 빈 문자열."""
    if not path.exists():
        return None
    try:
        return (ET.fromstring(path.read_bytes()).findtext(".//lastModYmd") or "").strip()
    except ET.ParseError:
        return None


def content_digest(xml_bytes: bytes) -> str:
    """상세 XML이 실제로 바뀌었는지 비교하는 해시. 공백 차이와 쉼표 목록의 나열 순서는 무시한다.

    중앙부처 API는 같은 내용이어도 "청년, 중장년, 노년" ↔ "중장년, 청년, 노년"처럼 목록 항목 순서를 바꿔 보내는 일이 있어
    (2026-10-19 실측: 갱신으로 잡힌 49건 중 대부분), 순서만 다른 것을 "수정"으로 세지 않도록 쉼표 목록은 정렬해서 비교한다.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return hashlib.sha256(re.sub(rb">\s+<", b"><", xml_bytes.strip())).hexdigest()
    parts = []
    for element in root.iter():
        if len(element):
            continue
        text = (element.text or "").strip()
        if element.tag.endswith("Array") or element.tag == "srvPvsnNm":
            text = ",".join(sorted(token.strip() for token in text.split(",") if token.strip()))
        parts.append(f"{element.tag}={text}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


@dataclass
class Plan:
    new: list[ListEntry] = field(default_factory=list)
    changed: list[ListEntry] = field(default_factory=list)
    unchanged: list[ListEntry] = field(default_factory=list)
    unknown: list[ListEntry] = field(default_factory=list)  # 수정일로 판단할 수 없어 상세를 받아 비교해야 하는 정책
    removed: list[str] = field(default_factory=list)  # 목록에서 사라진 ID(파일은 지우지 않는다)

    @property
    def to_fetch(self) -> list[ListEntry]:
        return [*self.new, *self.changed, *self.unknown]


def make_plan(fresh: list[ListEntry], detail_dir: Path) -> Plan:
    """새 목록과 내려받아 둔 상세 파일을 비교해 상세를 다시 받을 정책을 고른다."""
    plan = Plan()
    seen = set()
    for entry in fresh:
        if entry.policy_id in seen:
            continue
        seen.add(entry.policy_id)
        stored = detail_last_mod(detail_dir / f"{entry.policy_id}.xml")
        if stored is None:
            plan.new.append(entry)
        elif not entry.last_mod or not stored:
            plan.unknown.append(entry)  # 어느 한쪽에 수정일이 없으면 내용을 직접 비교한다
        elif entry.last_mod != stored:
            plan.changed.append(entry)
        else:
            plan.unchanged.append(entry)
    if detail_dir.exists():
        plan.removed = sorted(p.stem for p in detail_dir.glob("*.xml") if p.stem not in seen)
    return plan


@dataclass
class ApplyResult:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    same: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    remaining: list[str] = field(default_factory=list)  # 한도에 걸려 아직 처리하지 못한 ID


def apply_plan(
    entries: list[ListEntry],
    fetch_detail: Callable[[str], bytes],
    detail_dir: Path,
    prev_dir: Path,
    on_progress: Callable[[str], None] = lambda _msg: None,
) -> ApplyResult:
    """상세를 받아 저장한다. 바뀐 파일은 덮어쓰기 전에 prev_dir로 옮기고, 같으면 건드리지 않는다."""
    result = ApplyResult()
    detail_dir.mkdir(parents=True, exist_ok=True)
    for index, entry in enumerate(entries):
        pid = entry.policy_id
        if not ID_PATTERN.fullmatch(pid):
            result.failed[pid] = "잘못된 정책 ID"
            continue
        try:
            xml_bytes = fetch_detail(pid)
        except QuotaReached:
            result.remaining = [e.policy_id for e in entries[index:]]
            break
        except RuntimeError as error:
            result.failed[pid] = str(error)
            continue
        target = detail_dir / f"{pid}.xml"
        if target.exists():
            if content_digest(target.read_bytes()) == content_digest(xml_bytes):
                result.same.append(pid)
                continue
            prev_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(prev_dir / target.name))
            result.updated.append(pid)
        else:
            result.added.append(pid)
        target.write_bytes(xml_bytes)
        on_progress(f"저장: {pid} {entry.title}")
    return result


# ------------------------------------------------------------------ 네트워크


class Fetcher:
    def __init__(self, config: dict, api_key: str, max_calls: int) -> None:
        import requests

        self._requests = requests
        self.config, self.api_key, self.max_calls, self.calls = config, api_key, max_calls, 0
        self.session = requests.Session()

    def _get(self, endpoint: str, params: dict) -> tuple[bytes, ET.Element]:
        url = f"{self.config['base']}/{endpoint}"
        for attempt in range(3):
            if self.calls >= self.max_calls:
                raise QuotaReached("이번 실행의 호출 제한에 도달했습니다.")
            self.calls += 1
            try:
                response = self.session.get(url, params={"serviceKey": self.api_key, **params}, timeout=30)
            except self._requests.RequestException:
                if attempt < 2:
                    time.sleep(2)
                    continue
                raise RuntimeError("네트워크 요청 실패") from None
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            if response.status_code != 200:
                body = response.text.replace(self.api_key, "[인증키 가림]")[:300]
                raise RuntimeError(f"HTTP {response.status_code}: {body}")
            try:
                root = ET.fromstring(response.content)
            except ET.ParseError:
                raise RuntimeError("XML이 아닌 응답을 받았습니다.") from None
            code = (root.findtext(".//resultCode") or "").strip()
            if code and code not in ("0", "00", "200"):
                if code == "22":
                    raise QuotaReached("API 호출 한도에 도달했습니다.")
                if code == "23" and attempt < 2:
                    time.sleep(3)
                    continue
                raise RuntimeError(f"API 오류 코드 {code}")
            time.sleep(1)  # 연속 호출 간격
            return response.content, root
        raise RuntimeError("요청 재시도 실패")

    def list_pages(self, snapshot_dir: Path, source: str) -> list[ListEntry]:
        """목록 전체를 새로 받아 snapshot_dir에 저장하고 항목을 돌려준다. (기존 list/는 건드리지 않는다.)"""
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        entries: list[ListEntry] = []
        page = 1
        while True:
            params = {"callTp": "L", "pageNo": page, "numOfRows": 100, "lifeArray": "004"}  # 청년 생애주기
            if source == "national":
                params["srchKeyCode"] = "003"
            xml_bytes, root = self._get(self.config["list"], params)
            (snapshot_dir / f"page_{page:05d}.xml").write_bytes(xml_bytes)
            page_entries = parse_list(xml_bytes)
            if not page_entries:
                break
            entries.extend(page_entries)
            total_text = root.findtext(".//totalCount") or ""
            total = int(total_text) if total_text.isdigit() else 0
            print(f"목록 {page}페이지: {len(page_entries)}건 (누적 {len(entries)} / 전체 {total or '미확인'})")
            if total and len(entries) >= total:
                break
            page += 1
        return entries

    def detail(self, policy_id: str) -> bytes:
        xml_bytes, root = self._get(self.config["detail"], {"callTp": "D", "servId": policy_id})
        returned = [n.text.strip() for n in root.findall(".//servId") if n.text]
        if policy_id not in returned:
            raise RuntimeError(f"상세 응답 ID 불일치: 요청={policy_id!r}, 응답={returned!r}")
        return xml_bytes


# ------------------------------------------------------------------ 실행


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def finalize_lists(raw_dir: Path, snapshot_dir: Path, entries: list[ListEntry], today: str) -> None:
    """모든 상세 갱신이 끝났을 때만 목록 파일(list/, policy_ids.csv, status.csv)을 새 목록으로 바꾼다."""
    list_dir = raw_dir / "list"
    if list_dir.exists():
        shutil.move(str(list_dir), str(raw_dir / f"list_prev_{today}"))
    shutil.move(str(snapshot_dir), str(list_dir))
    unique = list({e.policy_id: e for e in entries}.values())
    write_csv(raw_dir / "policy_ids.csv", ["servId", "servNm"], [{"servId": e.policy_id, "servNm": e.title} for e in unique])
    write_csv(
        raw_dir / "status.csv",
        ["servId", "servNm", "status"],
        [
            {"servId": e.policy_id, "servNm": e.title, "status": "완료" if (raw_dir / "detail" / f"{e.policy_id}.xml").exists() else "미수집"}
            for e in unique
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", choices=SOURCES)
    parser.add_argument("--apply", action="store_true", help="바뀐 정책의 상세를 실제로 받아 data/raw에 반영한다(기본은 점검만)")
    parser.add_argument("--max-calls", type=int, help="이번 실행의 최대 API 호출 수")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="프로젝트 루트")
    args = parser.parse_args()

    config = SOURCES[args.source]
    sys.path.insert(0, str(args.root))
    from app.env import load_env_file  # 이미 설정된 환경변수는 덮어쓰지 않는다

    load_env_file(args.root / ".env")
    api_key = os.getenv(config["key_env"], "").strip() or getpass(f"{args.source} API 인증키: ").strip()
    if not api_key:
        raise SystemExit(f"인증키가 비어 있습니다. 환경변수 {config['key_env']}를 설정하거나 입력하세요.")

    raw_dir = args.root / "data" / "raw" / args.source
    detail_dir, snapshot_dir = raw_dir / "detail", raw_dir / "list_snapshot"
    if not detail_dir.exists():
        raise SystemExit(f"{detail_dir}가 없습니다. 최초 수집은 download_welfare.py로 먼저 진행하세요.")
    today = date.today().strftime("%Y%m%d")
    fetcher = Fetcher(config, api_key, args.max_calls or config["default_max_calls"])
    state_path = raw_dir / "update_state.json"

    shutil.rmtree(snapshot_dir, ignore_errors=True)  # 지난 실행의 찌꺼기 페이지가 섞이지 않게 한다
    try:
        fresh = fetcher.list_pages(snapshot_dir, args.source)
        plan = make_plan(fresh, detail_dir)
        # 중단됐던 실행이 있으면(중앙부처) 이미 처리한 ID는 건너뛴다
        done = set()
        if state_path.exists():
            done = set(json.loads(state_path.read_text(encoding="utf-8")).get("done", []))
        todo = [e for e in plan.to_fetch if e.policy_id not in done]

        print(
            f"\n[{args.source}] 목록 {len(fresh)}건 | 신규 {len(plan.new)} · 수정 {len(plan.changed)} · "
            f"수정일 없음(내용 비교) {len(plan.unknown)} · 변동 없음 {len(plan.unchanged)} · 목록에서 사라짐 {len(plan.removed)}"
        )
        for label, items in (("신규", plan.new), ("수정", plan.changed)):
            for entry in items[:30]:
                print(f"  [{label}] {entry.policy_id} {entry.title} (수정일 {entry.last_mod or '-'})")
            if len(items) > 30:
                print(f"  ... {label} {len(items) - 30}건 더")
        print(f"상세 조회 예정 {len(todo)}건 (이번 실행 호출 한도 {fetcher.max_calls}, 목록에 이미 {fetcher.calls}회 사용)")

        if not args.apply:
            print("\n점검만 했습니다. 반영하려면 --apply를 붙여 다시 실행하세요. (data/raw의 기존 파일은 바뀌지 않았습니다)")
            shutil.rmtree(snapshot_dir, ignore_errors=True)
            return

        result = apply_plan(todo, fetcher.detail, detail_dir, detail_dir.parent / "detail_prev" / today, print)
        done |= set(result.added) | set(result.updated) | set(result.same)
        print(
            f"\n반영: 추가 {len(result.added)} · 갱신 {len(result.updated)} · 내용 동일 {len(result.same)} · "
            f"실패 {len(result.failed)} · 남음 {len(result.remaining)} (API 호출 {fetcher.calls}회)"
        )
        for pid, reason in list(result.failed.items())[:20]:
            print(f"  [실패] {pid}: {reason}")

        report = {
            "source": args.source,
            "date": today,
            "list_total": len(fresh),
            "new": [e.policy_id for e in plan.new],
            "changed": [e.policy_id for e in plan.changed],
            "added": result.added,
            "updated": result.updated,
            "same_content": result.same,
            "failed": result.failed,
            "remaining": result.remaining,
            "removed_from_list": plan.removed,
        }
        report_dir = raw_dir / "update_reports"
        report_dir.mkdir(exist_ok=True)
        (report_dir / f"update_{today}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        if result.remaining or result.failed:
            state_path.write_text(json.dumps({"done": sorted(done)}, ensure_ascii=False), encoding="utf-8")
            print("\n일부가 남아 목록 파일은 바꾸지 않았습니다. 같은 명령을 다시 실행하면 이어받습니다.")
        else:
            finalize_lists(raw_dir, snapshot_dir, fresh, today)
            state_path.unlink(missing_ok=True)
            print("\n완료: list/, policy_ids.csv, status.csv를 새 목록으로 갱신했습니다. (data/chroma는 건드리지 않았습니다)")
    except QuotaReached as reason:
        print(f"\n수집 일시 중단: {reason}\n나중에 같은 명령을 다시 실행하면 이어받습니다.")
    finally:
        if not args.apply:
            shutil.rmtree(snapshot_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
