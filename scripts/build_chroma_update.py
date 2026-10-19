"""갱신된 정책만 기존 ChromaDB의 **복사본**에 반영해 새 DB 폴더를 만든다. 원본 data/chroma는 읽기만 한다.

    python scripts/build_chroma_update.py --out-db D:/chroma_update_20261019 --report-date 20261019 --verify-only   # 호환성 검증만
    python scripts/build_chroma_update.py --out-db D:/chroma_update_20261019 --report-date 20261019                 # 복사본 생성 + 반영

왜 import_welfare_chroma_qwen_v3.py를 그대로 쓰지 않나
- 현재 DB(11,850건)는 서식·첨부 자료를 `documents` 섹션(검색 대상, 문구 "필요 서류 및 첨부 자료")으로 저장했는데, 저장소의
  적재 스크립트는 `attachments` 섹션(검색 제외, 문구 "서식 및 첨부 자료")과 추가 메타데이터 3개를 만든다. 전체를 다시 만들면
  documents 섹션이 사라져 앱·계약서(documents)와 어긋난다.
- 이 스크립트는 적재 스크립트의 레코드 생성 로직을 그대로 쓰되, 문서를 조각내기 **전에** 기존 문구로 바꾸고 섹션·ID·메타데이터를
  기존 DB 형식으로 되돌린다(조각 경계까지 같아지도록). 변환이 맞는지는 `--verify-only`로 "바뀌지 않은 정책의 모든 레코드가 기존 DB와
  같은지" 확인한다.

반영 방식: 수집 보고서(data/raw/<source>/update_reports/update_<날짜>.json)의 added·updated 정책에 대해 복사본에서 그 정책의
레코드를 모두 지우고 새로 넣는다. 나머지 정책의 레코드는 손대지 않는다.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import shutil
import sys
import types
from pathlib import Path

import chromadb

PROJECT = Path(__file__).resolve().parents[1]
IMPORTER = PROJECT / "scripts" / "import_welfare_chroma_qwen_v3.py"
COLLECTION = "welfare_policy_sections_qwen_v3"
EXTRA_METADATA = ("has_attachments", "has_document_evidence", "document_evidence_status")  # 기존 DB에 없는 키

# 적재 스크립트의 문구를 기존 DB가 만들어졌을 때의 문구로 되돌린다(조각을 나누기 전에 적용해야 조각 경계가 같아진다).
LABEL_PATCHES = (
    ('"attachments": "서식 및 첨부 자료"', '"attachments": "필요 서류 및 첨부 자료"'),
    ('("basfrmList", "서식·첨부 자료")', '("basfrmList", "서식·준비 자료")'),
)


def load_importer() -> types.ModuleType:
    source = IMPORTER.read_text(encoding="utf-8")
    for old, new in LABEL_PATCHES:
        if old not in source:
            raise RuntimeError(f"적재 스크립트가 바뀌어 패치 지점을 찾지 못했습니다: {old}")
        source = source.replace(old, new)
    module = types.ModuleType("import_welfare_compat")
    module.__file__ = str(IMPORTER)
    exec(compile(source, str(IMPORTER), "exec"), module.__dict__)
    return module


def to_old_format(record: dict) -> dict:
    """적재 스크립트의 레코드를 기존 DB 형식(documents 섹션, 검색 대상, 추가 키 없음)으로 바꾼다."""
    metadata = dict(record["metadata"])
    record_id = record["id"]
    if metadata.get("section") == "attachments":
        metadata.update(section="documents", record_type="search", searchable=True)
        record_id = record_id.replace(":detail:attachments:", ":search:documents:")
    for key in EXTRA_METADATA:
        metadata.pop(key, None)
    return {"id": record_id, "document": record["document"], "metadata": metadata}


def target_policies(report_date: str) -> dict[str, str]:
    """수집 보고서에서 이번에 추가·갱신된 정책 {source_id: source}."""
    targets: dict[str, str] = {}
    for source in ("local", "national"):
        path = PROJECT / "data" / "raw" / source / "update_reports" / f"update_{report_date}.json"
        if not path.exists():
            raise SystemExit(f"수집 보고서가 없습니다: {path}")
        report = json.loads(path.read_text(encoding="utf-8"))
        for pid in [*report["added"], *report["updated"]]:
            targets[pid] = source
    return targets


def all_records(module, tokenizer, only: dict[str, str] | None = None, skip: set[str] | None = None):
    for source in ("local", "national"):
        for path in sorted((PROJECT / "data" / "raw" / source / "detail").glob("*.xml")):
            if only is not None and path.stem not in only:
                continue
            if skip is not None and path.stem in skip:
                continue
            for record in module.make_records(path, source, PROJECT, tokenizer):
                yield path.stem, to_old_format(record)


def snapshot(collection) -> dict[str, tuple[str, dict]]:
    data = collection.get(include=["documents", "metadatas"])
    return {i: (d, m) for i, d, m in zip(data["ids"], data["documents"], data["metadatas"])}


def compare(base: dict, built: dict, scope_ids: set[str]) -> collections.Counter:
    """scope_ids(정책 ID)에 속한 레코드가 base와 built에서 같은지 센다."""
    stat: collections.Counter = collections.Counter()
    for record_id, (doc, meta) in built.items():
        if meta["source_id"] not in scope_ids:
            continue
        old = base.get(record_id)
        if old is None:
            stat["새 DB에만 있음"] += 1
        elif old[0] != doc:
            stat["문서 다름"] += 1
        elif old[1] != meta:
            stat["메타데이터 다름"] += 1
        else:
            stat["동일"] += 1
    for record_id, (_, meta) in base.items():
        if meta["source_id"] in scope_ids and record_id not in built:
            stat["기존 DB에만 있음"] += 1
    return stat


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-db", type=Path, default=PROJECT / "data" / "chroma", help="기존 DB(읽기만 함)")
    parser.add_argument("--out-db", type=Path, required=True, help="새로 만들 DB 폴더(이미 있으면 중단)")
    parser.add_argument("--report-date", required=True, help="수집 보고서 날짜(예: 20261019)")
    parser.add_argument("--verify-only", action="store_true", help="복사·반영 없이 변환 호환성만 검증")
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()

    module = load_importer()
    model = module.load_model(True)
    targets = target_policies(args.report_date)
    print(f"반영 대상 정책 {len(targets)}개", flush=True)

    base_client = chromadb.PersistentClient(path=str(args.base_db.resolve()))
    base_col = base_client.get_collection(COLLECTION)
    base = snapshot(base_col)
    print(f"기존 DB: {len(base)}건", flush=True)

    # 1) 호환성 검증: 바뀌지 않은 정책의 모든 레코드가 기존 DB와 같은가
    unchanged_built = {rid: (rec["document"], rec["metadata"]) for _, rec in all_records(module, model.tokenizer, skip=set(targets)) for rid in [rec["id"]]}
    unchanged_ids = {meta["source_id"] for _, meta in unchanged_built.values()}
    stat = compare(base, unchanged_built, unchanged_ids)
    print(f"[호환성 검증] 바뀌지 않은 정책 {len(unchanged_ids)}개: {dict(stat)}", flush=True)
    mismatch = sum(v for k, v in stat.items() if k != "동일")
    if args.verify_only:
        sys.exit(0 if mismatch == 0 else 1)
    if mismatch:
        raise SystemExit("변환이 기존 DB와 일치하지 않아 중단합니다. (--verify-only로 원인을 확인하세요)")

    # 2) 복사본 생성 후 대상 정책만 교체
    out = args.out_db.resolve()
    if out.exists():
        raise SystemExit(f"{out}가 이미 있습니다. 다른 폴더를 지정하세요.")
    shutil.copytree(args.base_db.resolve(), out)
    client = chromadb.PersistentClient(path=str(out))
    collection = client.get_collection(COLLECTION)

    new_records = [rec for _, rec in all_records(module, model.tokenizer, only=targets)]
    removed = 0
    for pid in targets:
        found = collection.get(where={"source_id": pid})["ids"]
        removed += len(found)
        if found:
            collection.delete(ids=found)
    for start in range(0, len(new_records), args.batch_size):
        batch = new_records[start:start + args.batch_size]
        embeddings = model.encode([r["document"] for r in batch], batch_size=args.batch_size, normalize_embeddings=True, show_progress_bar=False)
        collection.upsert(
            ids=[r["id"] for r in batch],
            documents=[r["document"] for r in batch],
            metadatas=[r["metadata"] for r in batch],
            embeddings=embeddings.tolist(),
        )
    print(f"교체: 삭제 {removed}건 → 추가 {len(new_records)}건 | 기존 {len(base)}건 → 새 DB {collection.count()}건", flush=True)

    # 3) 반영 후 검증: 대상이 아닌 정책은 기존과 완전히 같아야 한다
    built = snapshot(collection)
    untouched = {meta["source_id"] for _, meta in base.values()} - set(targets)
    after = compare(base, built, untouched)
    print(f"[반영 후 검증] 대상 아닌 정책 {len(untouched)}개: {dict(after)}", flush=True)
    if any(v for k, v in after.items() if k != "동일"):
        raise SystemExit("대상이 아닌 정책이 바뀌었습니다. 새 DB를 사용하지 마세요.")
    print("완료:", out)


if __name__ == "__main__":
    main()
