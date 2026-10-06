"""Index all welfare detail XML fields as short, source-backed Chroma records.

The original XML remains the authoritative copy. Searchable policy facts and
administrative fields share one collection; `searchable` filters vector search.
"""

from __future__ import annotations

import argparse
import collections
import xml.etree.ElementTree as ET
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer


MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
COLLECTION_NAME = "welfare_policy_sections_v2"
MAX_TOKENS = 100  # The model's actual limit is 128, including special tokens.

FIELD_INFO = {
    "servDgst": ("개요", "overview", True),
    "wlfareInfoOutlCn": ("개요", "overview", True),
    "sprtTrgtCn": ("지원 대상", "target", True),
    "tgtrDtlCn": ("지원 대상", "target", True),
    "slctCritCn": ("선정 기준", "criteria", True),
    "alwServCn": ("지원 내용", "benefit", True),
    "aplyMtdCn": ("신청 방법", "application", True),
    "applmetList": ("신청 방법", "application", True),
    "basfrmList": ("서식·준비 자료", "documents", True),
    "inqplHmpgReldList": ("관련 홈페이지", "links", True),
    "lifeNmArray": ("생애주기", "target", True),
    "lifeArray": ("생애주기", "target", True),
    "trgterIndvdlNmArray": ("대상 유형", "target", True),
    "trgterIndvdlArray": ("대상 유형", "target", True),
    "intrsThemaNmArray": ("관심 주제", "overview", True),
    "intrsThemaArray": ("관심 주제", "overview", True),
    "sprtCycNm": ("지원 주기", "benefit", True),
    "srvPvsnNm": ("지원 형태", "benefit", True),
    "aplyMtdNm": ("신청 방식", "application", True),
    "onapPsbltYn": ("온라인 신청 가능 여부", "application", True),
    "ctpvNm": ("시도", "identity", False),
    "sggNm": ("시군구", "identity", False),
    "bizChrDeptNm": ("담당 부서", "identity", False),
    "jurMnofNm": ("소관 기관", "identity", False),
    "jurOrgNm": ("소관 기관", "identity", False),
    "inqplCtadrList": ("문의처", "contact", False),
    "rprsCtadr": ("대표 문의처", "contact", False),
    "baslawList": ("관련 법령", "legal", False),
    "enfcBgngYmd": ("시작일", "administrative", False),
    "enfcEndYmd": ("종료일", "administrative", False),
    "lastModYmd": ("수정일", "administrative", False),
    "crtrYr": ("기준 연도", "administrative", False),
    "inqNum": ("조회 수", "administrative", False),
}
SKIP_FIELDS = {"servId", "servNm", "resultCode", "resultMessage"}


def field_text(node: ET.Element) -> str:
    """Flatten nested source fields while retaining their child field names."""
    if not len(node):
        return (node.text or "").strip()
    lines = []

    def walk(parent: ET.Element, parents: tuple[str, ...] = ()) -> None:
        for child in parent:
            path = (*parents, child.tag)
            if len(child):
                walk(child, path)
            elif (child.text or "").strip():
                lines.append(f"{'/'.join(path)}: {child.text.strip()}")

    walk(node)
    return "\n".join(lines)


def token_count(tokenizer, text: str) -> int:
    return len(tokenizer.encode(text, add_special_tokens=True, truncation=False))


def split_for_model(tokenizer, prefix: str, value: str) -> list[str]:
    """Split at natural boundaries where possible; never exceed MAX_TOKENS."""
    if token_count(tokenizer, prefix) >= MAX_TOKENS:
        raise ValueError(f"Policy title/prefix is too long: {prefix!r}")
    result = []
    remaining = value.strip()
    while remaining:
        if token_count(tokenizer, prefix + remaining) <= MAX_TOKENS:
            result.append(prefix + remaining)
            break
        low, high = 1, len(remaining)
        while low < high:
            mid = (low + high + 1) // 2
            if token_count(tokenizer, prefix + remaining[:mid]) <= MAX_TOKENS:
                low = mid
            else:
                high = mid - 1
        cut = low
        if cut < len(remaining):
            # Prefer the end of a sentence, line, or word near the token limit.
            start = max(1, cut * 2 // 3)
            for separator in ("\n", ". ", "。", " "):
                pos = remaining.rfind(separator, start, cut)
                if pos > 0:
                    cut = pos + len(separator)
                    break
        part = remaining[:cut].strip()
        if not part:
            raise ValueError("Could not split nonempty policy text")
        result.append(prefix + part)
        remaining = remaining[cut:].strip()
    if any(token_count(tokenizer, item) > MAX_TOKENS for item in result):
        raise ValueError("A policy section exceeds the embedding model limit")
    return result


def make_records(path: Path, source: str, project: Path, tokenizer) -> list[dict]:
    root = ET.parse(path).getroot()
    source_id = (root.findtext("servId") or "").strip()
    title = (root.findtext("servNm") or "").strip()
    result_code = (root.findtext("resultCode") or "").strip()
    if source_id != path.stem or not title or result_code not in {"0", "00", "200"}:
        raise ValueError(f"Invalid detail response: {path}")
    policy_id = f"{source}:{source_id}"
    region = " ".join(filter(None, [root.findtext("ctpvNm"), root.findtext("sggNm")]))
    if source == "national":
        region = "중앙부처 (지역 조건은 원문 확인)"
    updated = (root.findtext("lastModYmd") or root.findtext("crtrYr") or "").strip()
    source_file = str(path.relative_to(project)).replace("\\", "/")
    records = []
    field_occurrences = collections.Counter()
    for field in root:
        if field.tag in SKIP_FIELDS:
            continue
        occurrence = field_occurrences[field.tag]
        field_occurrences[field.tag] += 1
        value = field_text(field)
        if not value:
            continue
        label, section, searchable = FIELD_INFO.get(field.tag, (field.tag, "other", False))
        prefix = f"정책명: {title}\n{label}: "
        for index, document in enumerate(split_for_model(tokenizer, prefix, value)):
            records.append({
                "id": f"{policy_id}:{field.tag}:{occurrence}:{index}",
                "document": document,
                "metadata": {
                    "policy_id": policy_id,
                    "title": title,
                    "source": source,
                    "source_id": source_id,
                    "source_field": field.tag,
                    "field_occurrence": occurrence,
                    "section": section,
                    "searchable": searchable,
                    "region": region,
                    "updated_at": updated,
                    "source_file": source_file,
                },
            })
    if not records:
        raise ValueError(f"No nonempty detail fields: {path}")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    project = args.project.resolve()
    paths = [(source, path) for source in ("local", "national")
             for path in sorted((project / "data" / "raw" / source / "detail").glob("*.xml"))]
    if args.limit:
        paths = paths[:args.limit]
    if not paths:
        parser.error("No collected detail XML found")
    model = SentenceTransformer(MODEL_NAME, local_files_only=True)
    tokenizer = model.tokenizer
    records, source_counts = [], collections.Counter()
    for source, path in paths:
        records.extend(make_records(path, source, project, tokenizer))
        source_counts[source] += 1
    ids = [item["id"] for item in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate Chroma record IDs")
    print(f"Policies: {dict(source_counts)}; sections: {len(records)}; "
          f"max tokens: {max(token_count(tokenizer, x['document']) for x in records)}; "
          f"searchable: {sum(x['metadata']['searchable'] for x in records)}", flush=True)
    if args.dry_run:
        return
    db_path = (args.db_path or project / "data" / "chroma").resolve()
    client = chromadb.PersistentClient(path=str(db_path))
    collection = client.get_or_create_collection(
        COLLECTION_NAME, metadata={"hnsw:space": "cosine", "embedding_model": MODEL_NAME,
                                   "max_input_tokens": MAX_TOKENS})
    for start in range(0, len(records), args.batch_size):
        batch = records[start:start + args.batch_size]
        embeddings = model.encode([x["document"] for x in batch],
                                  batch_size=32, normalize_embeddings=True)
        collection.upsert(ids=[x["id"] for x in batch],
                          documents=[x["document"] for x in batch],
                          metadatas=[x["metadata"] for x in batch],
                          embeddings=embeddings.tolist())
        if start == 0 or start + len(batch) == len(records) or start // args.batch_size % 20 == 0:
            print(f"Stored {start + len(batch)}/{len(records)} sections", flush=True)
    print(f"Done: {collection.count()} records in {COLLECTION_NAME}")


if __name__ == "__main__":
    main()
