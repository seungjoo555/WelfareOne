"""Import collected welfare detail XML into one persistent Chroma collection.

Each policy is represented by a set of source-backed, semantically grouped
sections. Exact lookup of every section uses the shared policy_id metadata.
"""

from __future__ import annotations

import argparse
import collections
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer


COLLECTION = "welfare_policy_sections"
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MAX_SECTION_BYTES = 8_000
SECTION_LABELS = {
    "identity": "정책 정보",
    "overview": "개요",
    "target": "지원 대상",
    "criteria": "선정 기준",
    "benefit": "지원 내용",
    "application": "신청 방법",
    "documents": "서류와 서식",
    "contact": "문의 및 링크",
    "legal": "법적 근거",
    "other": "기타 공식 정보",
}
FIELD_SECTIONS = {
    "servDgst": "overview", "wlfareInfoOutlCn": "overview",
    "lifeNmArray": "target", "lifeArray": "target",
    "trgterIndvdlNmArray": "target", "trgterIndvdlArray": "target",
    "sprtTrgtCn": "target", "tgtrDtlCn": "target",
    "slctCritCn": "criteria", "alwServCn": "benefit",
    "sprtCycNm": "benefit", "srvPvsnNm": "benefit",
    "aplyMtdNm": "application", "aplyMtdCn": "application",
    "applmetList": "application", "inqplHmpgReldList": "contact",
    "basfrmList": "documents", "inqplCtadrList": "contact",
    "baslawList": "legal", "inqNum": "other", "rprsCtadr": "contact",
    "enfcBgngYmd": "other", "enfcEndYmd": "other",
    "lastModYmd": "other", "crtrYr": "other",
    "ctpvNm": "identity", "sggNm": "identity",
    "bizChrDeptNm": "identity", "jurMnofNm": "identity", "jurOrgNm": "identity",
    "intrsThemaNmArray": "other", "intrsThemaArray": "other",
    "onapPsbltYn": "application",
}
SKIP_FIELDS = {"servId", "servNm", "resultCode", "resultMessage"}


def flatten_field(node: ET.Element) -> str:
    """Keep nested element names and repeated values, without guessing semantics."""
    if not len(node):
        return (node.text or "").strip()
    lines = []

    def walk(element: ET.Element, prefix: str = "") -> None:
        for child in element:
            name = f"{prefix}/{child.tag}" if prefix else child.tag
            if len(child):
                walk(child, name)
            elif (child.text or "").strip():
                lines.append(f"{name}: {child.text.strip()}")

    walk(node)
    return "\n".join(lines)


def split_lines(lines: list[str], prefix: str) -> list[str]:
    """Keep each Chroma document comfortably under the 16 kB chunk guidance."""
    parts, current = [], prefix
    for line in lines:
        remaining = line
        while remaining:
            room = MAX_SECTION_BYTES - len(current.encode("utf-8")) - 2
            if room <= 0:
                parts.append(current)
                current = prefix
                continue
            if len(remaining.encode("utf-8")) <= room:
                current += "\n" + remaining
                break
            # Split an unusually long field safely on character boundaries.
            cut = max(1, room // 3)
            while len(remaining[:cut].encode("utf-8")) > room:
                cut -= 1
            if cut < len(remaining):
                space = remaining.rfind(" ", 0, cut)
                if space > cut // 2:
                    cut = space
            current += "\n" + remaining[:cut].rstrip()
            parts.append(current)
            current = prefix
            remaining = remaining[cut:].lstrip()
    if current != prefix:
        parts.append(current)
    return parts


def policy_records(path: Path, source: str, root_dir: Path) -> list[dict]:
    root = ET.parse(path).getroot()
    source_id = (root.findtext("servId") or "").strip()
    title = (root.findtext("servNm") or "").strip()
    code = (root.findtext("resultCode") or "").strip()
    if source_id != path.stem or not title or code not in {"0", "00", "200"}:
        raise ValueError(f"Invalid detail XML: {path}")
    policy_id = f"{source}:{source_id}"
    region = " ".join(filter(None, [root.findtext("ctpvNm"), root.findtext("sggNm")]))
    if source == "national":
        region = "전국/중앙부처 (개별 조건 확인)"
    update = (root.findtext("lastModYmd") or root.findtext("crtrYr") or "").strip()
    groups: dict[str, list[str]] = collections.defaultdict(list)
    fields: dict[str, set[str]] = collections.defaultdict(set)
    for child in root:
        if child.tag in SKIP_FIELDS:
            continue
        value = flatten_field(child)
        if not value:
            continue
        section = FIELD_SECTIONS.get(child.tag, "other")
        groups[section].append(f"{child.tag}: {value}")
        fields[section].add(child.tag)

    records = []
    for section, lines in groups.items():
        prefix = f"정책명: {title}\n{SECTION_LABELS[section]}"
        for index, document in enumerate(split_lines(lines, prefix)):
            metadata = {
                "policy_id": policy_id,
                "source": source,
                "source_id": source_id,
                "title": title,
                "section": section,
                "source_fields": ",".join(sorted(fields[section])),
                "region": region,
                "updated_at": update,
                "source_file": str(path.relative_to(root_dir)).replace("\\", "/"),
            }
            records.append({"id": f"{policy_id}:{section}:{index}",
                            "document": document, "metadata": metadata})
    if not records:
        raise ValueError(f"No content in detail XML: {path}")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--limit", type=int, help="Preview only this many policies")
    parser.add_argument("--dry-run", action="store_true", help="Validate XML without writing Chroma")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    project = args.project.resolve()
    raw = project / "data" / "raw"
    paths = [(source, p) for source in ("local", "national")
             for p in sorted((raw / source / "detail").glob("*.xml"))]
    if args.limit:
        paths = paths[:args.limit]
    if not paths:
        parser.error(f"No detail XML under {raw}")
    records, counts = [], collections.Counter()
    for source, path in paths:
        items = policy_records(path, source, project)
        records.extend(items)
        counts[source] += 1
    ids = [r["id"] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate Chroma IDs")
    print(f"Verified {dict(counts)} policies; {len(records)} section records; "
          f"largest {max(len(r['document'].encode('utf-8')) for r in records)} bytes")
    if args.dry_run:
        return

    db_path = (args.db_path or project / "data" / "chroma").resolve()
    model = SentenceTransformer(MODEL, local_files_only=True)
    client = chromadb.PersistentClient(path=str(db_path))
    collection = client.get_or_create_collection(
        COLLECTION, metadata={"hnsw:space": "cosine", "embedding_model": MODEL})
    for start in range(0, len(records), args.batch_size):
        batch = records[start:start + args.batch_size]
        embeddings = model.encode([r["document"] for r in batch],
                                  batch_size=32, normalize_embeddings=True)
        collection.upsert(ids=[r["id"] for r in batch],
                          documents=[r["document"] for r in batch],
                          metadatas=[r["metadata"] for r in batch],
                          embeddings=embeddings.tolist())
        if start == 0 or (start // args.batch_size) % 10 == 0 or start + len(batch) == len(records):
            print(f"Stored {start + len(batch)}/{len(records)} sections", flush=True)
    print(f"Done: {collection.count()} records at {db_path}")


if __name__ == "__main__":
    main()
