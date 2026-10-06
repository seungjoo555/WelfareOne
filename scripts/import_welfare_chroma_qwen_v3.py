"""Build a Qwen3-Embedding Chroma collection from welfare detail XML files.

This importer keeps the existing collections intact. It creates semantic policy
sections, one compact candidate-summary record per policy, and metadata suitable
for safe filtering. Source XML files remain the authoritative records.
"""

from __future__ import annotations

import argparse
import collections
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

import chromadb
from sentence_transformers import SentenceTransformer


MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
COLLECTION_NAME = "welfare_policy_sections_qwen_v3"
MAX_TOKENS = 300
OVERLAP_TOKENS = 40

LIFE_CYCLES = {
    "영유아": "is_infant",
    "아동": "is_child",
    "청소년": "is_adolescent",
    "청년": "is_youth",
    "중장년": "is_middle_aged",
    "노년": "is_senior",
    "임신·출산": "is_pregnancy_birth",
}

# Fields with the same meaning in the two APIs are grouped into one section.
SECTION_FIELDS = {
    "overview": (
        ("servDgst", "정책 개요"),
        ("wlfareInfoOutlCn", "정책 개요"),
        ("intrsThemaNmArray", "관심 주제"),
        ("intrsThemaArray", "관심 주제"),
    ),
    "target_criteria": (
        ("lifeNmArray", "생애주기"),
        ("lifeArray", "생애주기"),
        ("trgterIndvdlNmArray", "대상 유형"),
        ("trgterIndvdlArray", "대상 유형"),
        ("sprtTrgtCn", "지원 대상"),
        ("tgtrDtlCn", "지원 대상"),
        ("slctCritCn", "선정 기준"),
    ),
    "benefit": (
        ("alwServCn", "지원 내용"),
        ("srvPvsnNm", "지원 형태"),
        ("sprtCycNm", "지원 주기"),
    ),
    "application": (
        ("aplyMtdNm", "신청 방식"),
        ("aplyMtdCn", "신청 방법"),
        ("applmetList", "신청 방법"),
        ("onapPsbltYn", "온라인 신청 가능 여부"),
    ),
    # basfrmList is an attachment/form list. An attached form is not proof that
    # every user must submit it, so keep it separate from required documents.
    "attachments": (("basfrmList", "서식·첨부 자료"),),
    "contact_source": (
        ("bizChrDeptNm", "담당 부서"),
        ("jurMnofNm", "소관 기관"),
        ("jurOrgNm", "소관 기관"),
        ("inqplCtadrList", "문의처"),
        ("rprsCtadr", "대표 문의처"),
        ("inqplHmpgReldList", "관련 홈페이지"),
    ),
    "administrative": (
        ("enfcBgngYmd", "시작일"),
        ("enfcEndYmd", "종료일"),
        ("lastModYmd", "수정일"),
        ("crtrYr", "기준 연도"),
        ("baslawList", "관련 법령"),
        ("inqNum", "조회 수"),
    ),
}

SEARCHABLE_SECTIONS = {
    "candidate_summary",
    "overview",
    "target_criteria",
    "benefit",
    "application",
}

DOCUMENT_EVIDENCE_TERMS = (
    "구비서류", "제출서류", "준비서류", "첨부서류", "필요서류",
    "신청서", "동의서", "증명서", "확인서", "영수증",
    "통장사본", "통장 사본", "서류 제출", "제출해야",
)

COMPLEX_AGE_WORDS = (
    "출생", "출생연도", "연 나이", "군복무", "병역", "복무기간", "연장",
    "나이 계산", "예외", "별도 연령",
)


def normalize_space(value: str) -> str:
    return re.sub(r"[ \t]+", " ", value.replace("\r\n", "\n").replace("\r", "\n")).strip()


def field_text(node: ET.Element) -> str:
    """Flatten nested XML while retaining the child labels and all occurrences."""
    if not len(node):
        return normalize_space(node.text or "")
    lines: list[str] = []

    def walk(parent: ET.Element, parents: tuple[str, ...] = ()) -> None:
        for child in parent:
            path = (*parents, child.tag)
            if len(child):
                walk(child, path)
            elif normalize_space(child.text or ""):
                lines.append(f"{'/'.join(path)}: {normalize_space(child.text or '')}")

    walk(node)
    return "\n".join(lines)


def collect_fields(root: ET.Element) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = collections.defaultdict(list)
    for node in root:
        value = field_text(node)
        if value:
            fields[node.tag].append(value)
    return dict(fields)


def first(fields: dict[str, list[str]], *names: str) -> str:
    for name in names:
        if fields.get(name):
            return fields[name][0]
    return ""


def join_values(fields: dict[str, list[str]], names: Iterable[str]) -> str:
    values = [value for name in names for value in fields.get(name, []) if value]
    return "\n".join(dict.fromkeys(values))


def normalize_life_cycles(raw: str) -> list[str]:
    normalized = raw.replace("임신 · 출산", "임신·출산").replace("임신· 출산", "임신·출산")
    found = []
    for label in LIFE_CYCLES:
        if label in normalized:
            found.append(label)
    return found


def age_metadata(text: str) -> dict[str, object]:
    """Extract only unambiguous Korean age ranges; never guess complex rules."""
    compact = re.sub(r"\s+", " ", text)
    if not compact:
        return {"age_status": "unknown", "age_known": False}
    if any(word in compact for word in COMPLEX_AGE_WORDS):
        return {"age_status": "complex", "age_known": False}

    ranges = []
    range_pattern = (
        r"(?:만\s*)?(\d{1,3})\s*세?\s*(이상|초과)?\s*[~～\-–]\s*"
        r"(?:만\s*)?(\d{1,3})\s*세\s*(이하|미만)?"
    )
    prose_pattern = (
        r"(?:만\s*)?(\d{1,3})\s*세\s*(이상|초과).{0,30}?"
        r"(?:만\s*)?(\d{1,3})\s*세\s*(이하|미만)"
    )
    for pattern in (range_pattern, prose_pattern):
        for match in re.finditer(pattern, compact):
            minimum = int(match.group(1)) + (match.group(2) == "초과")
            maximum = int(match.group(3)) - (match.group(4) == "미만")
            if 0 <= minimum <= maximum <= 120:
                ranges.append((minimum, maximum))
    ranges = list(dict.fromkeys(ranges))
    if len(ranges) == 1:
        minimum, maximum = ranges[0]
        return {
            "age_status": "exact",
            "age_known": True,
            "min_age": minimum,
            "max_age": maximum,
        }
    if len(ranges) > 1 or re.search(r"(?:만\s*)?\d{1,3}\s*세", compact):
        return {"age_status": "complex", "age_known": False}
    return {"age_status": "unknown", "age_known": False}


def token_ids(tokenizer, text: str) -> list[int]:
    return tokenizer.encode(text, add_special_tokens=False, truncation=False)


def truncate_tokens(tokenizer, text: str, maximum: int) -> str:
    ids = token_ids(tokenizer, text)
    if len(ids) <= maximum:
        return text
    return tokenizer.decode(ids[:maximum], skip_special_tokens=True).strip() + " …"


def split_section(tokenizer, title: str, heading: str, body: str) -> list[str]:
    """Split a semantic section by tokens and retain overlap and policy context."""
    prefix = f"정책명: {title}\n{heading}:\n"
    prefix_tokens = len(token_ids(tokenizer, prefix))
    body_limit = MAX_TOKENS - prefix_tokens
    if body_limit <= OVERLAP_TOKENS:
        raise ValueError(f"Policy title is too long to chunk: {title}")
    ids = token_ids(tokenizer, body)
    if not ids:
        return []
    step = body_limit - OVERLAP_TOKENS
    documents = []
    for start in range(0, len(ids), step):
        part = ids[start:start + body_limit]
        if not part:
            break
        decoded = tokenizer.decode(part, skip_special_tokens=True).strip()
        documents.append(prefix + decoded)
        if start + body_limit >= len(ids):
            break
    return documents


def labeled_section(fields: dict[str, list[str]], section: str) -> str:
    lines = []
    for field_name, label in SECTION_FIELDS[section]:
        for value in fields.get(field_name, []):
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


def build_summary(tokenizer, title: str, region: str, life_text: str,
                  fields: dict[str, list[str]]) -> str:
    parts = [f"정책명: {title}"]
    if region:
        parts.append(f"지역·소관: {region}")
    if life_text:
        parts.append(f"생애주기: {life_text}")
    for field_names, label, budget in (
        (("servDgst", "wlfareInfoOutlCn"), "개요", 90),
        (("sprtTrgtCn", "tgtrDtlCn", "slctCritCn"), "대상·조건", 100),
        (("alwServCn",), "지원 내용", 90),
    ):
        value = join_values(fields, field_names)
        if value:
            parts.append(f"{label}: {truncate_tokens(tokenizer, value, budget)}")
    summary = "\n".join(parts)
    return truncate_tokens(tokenizer, summary, MAX_TOKENS)


def make_records(path: Path, source: str, project: Path, tokenizer) -> list[dict]:
    root = ET.parse(path).getroot()
    fields = collect_fields(root)
    source_id = first(fields, "servId")
    title = first(fields, "servNm")
    result_code = first(fields, "resultCode")
    if source_id != path.stem or not title or result_code not in {"0", "00", "200"}:
        raise ValueError(f"Invalid detail response: {path}")

    policy_id = f"{source}:{source_id}"
    region_level1 = first(fields, "ctpvNm") if source == "local" else ""
    region_level2 = first(fields, "sggNm") if source == "local" else ""
    region_text = " ".join(filter(None, (region_level1, region_level2)))
    if source == "national":
        region_text = "중앙부처"
    life_raw = join_values(fields, ("lifeNmArray", "lifeArray"))
    life_cycles = normalize_life_cycles(life_raw)
    life_text = ", ".join(life_cycles)
    target_text = join_values(fields, ("sprtTrgtCn", "tgtrDtlCn", "slctCritCn"))
    ages = age_metadata(target_text)
    updated_at = first(fields, "lastModYmd", "crtrYr")
    source_file = str(path.relative_to(project)).replace("\\", "/")
    application_text = join_values(fields, ("aplyMtdCn", "applmetList"))
    attachment_text = join_values(fields, ("basfrmList",))
    has_document_evidence = any(
        term in application_text for term in DOCUMENT_EVIDENCE_TERMS
    )
    has_attachments = bool(attachment_text)
    if has_document_evidence:
        document_evidence_status = "explicit_in_application"
    elif has_attachments:
        document_evidence_status = "attachments_only"
    else:
        document_evidence_status = "not_found"

    common_metadata: dict[str, object] = {
        "policy_id": policy_id,
        "source_id": source_id,
        "source": source,
        "jurisdiction": "local" if source == "local" else "national",
        "title": title,
        "region_text": region_text,
        "region_level1": region_level1,
        "region_level2": region_level2,
        "region_known": bool(region_level1),
        "life_cycles_text": life_text,
        "updated_at": updated_at,
        "source_file": source_file,
        # These are routing hints, not an eligibility or document judgment.
        "has_document_evidence": has_document_evidence,
        "has_attachments": has_attachments,
        "document_evidence_status": document_evidence_status,
        **{flag: label in life_cycles for label, flag in LIFE_CYCLES.items()},
        **ages,
    }

    records = []

    def add(section: str, document: str, index: int, record_type: str,
            searchable: bool) -> None:
        metadata = {
            **common_metadata,
            "section": section,
            "record_type": record_type,
            "searchable": searchable,
            "chunk_index": index,
        }
        records.append({
            "id": f"{policy_id}:{record_type}:{section}:{index}",
            "document": document,
            "metadata": metadata,
        })

    summary = build_summary(tokenizer, title, region_text, life_text, fields)
    add("candidate_summary", summary, 0, "search", True)

    headings = {
        "overview": "정책 개요",
        "target_criteria": "지원 대상 및 선정 조건",
        "benefit": "지원 혜택",
        "application": "신청 방법",
        "attachments": "서식 및 첨부 자료",
        "contact_source": "문의처 및 출처",
        "administrative": "행정 정보",
    }
    for section in SECTION_FIELDS:
        body = labeled_section(fields, section)
        if not body:
            continue
        searchable = section in SEARCHABLE_SECTIONS
        record_type = "search" if searchable else "detail"
        for index, document in enumerate(split_section(tokenizer, title, headings[section], body)):
            add(section, document, index, record_type, searchable)

    if len(records) < 2:
        raise ValueError(f"No policy sections produced: {path}")
    return records


def load_model(local_files_only: bool) -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME, local_files_only=local_files_only)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and rebuild only the Qwen v3 collection if it already exists",
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")

    project = args.project.resolve()
    paths = [
        (source, path)
        for source in ("local", "national")
        for path in sorted((project / "data" / "raw" / source / "detail").glob("*.xml"))
    ]
    if args.limit:
        paths = paths[:args.limit]
    if not paths:
        parser.error("No collected detail XML found")

    model = load_model(args.local_files_only)
    tokenizer = model.tokenizer
    records = []
    policy_counts = collections.Counter()
    for source, path in paths:
        records.extend(make_records(path, source, project, tokenizer))
        policy_counts[source] += 1

    ids = [record["id"] for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate Chroma record IDs")
    section_counts = collections.Counter(record["metadata"]["section"] for record in records)
    print(f"Policies: {dict(policy_counts)}", flush=True)
    print(f"Records: {len(records)} / sections: {dict(section_counts)}", flush=True)
    print(f"Known exact ages: {sum(r['metadata']['age_status'] == 'exact' for r in records)} records", flush=True)
    if args.dry_run:
        return

    db_path = (args.db_path or project / "data" / "chroma").resolve()
    client = chromadb.PersistentClient(path=str(db_path))
    existing_names = {item.name for item in client.list_collections()}
    if COLLECTION_NAME in existing_names:
        if not args.recreate:
            raise RuntimeError(
                f"{COLLECTION_NAME} already exists. Use --recreate for a clean rebuild."
            )
        client.delete_collection(COLLECTION_NAME)
    collection = client.get_or_create_collection(
        COLLECTION_NAME,
        metadata={
            "hnsw:space": "cosine",
            "embedding_model": MODEL_NAME,
            "max_input_tokens": MAX_TOKENS,
            "overlap_tokens": OVERLAP_TOKENS,
            "schema_version": 3,
        },
    )
    for start in range(0, len(records), args.batch_size):
        batch = records[start:start + args.batch_size]
        embeddings = model.encode(
            [record["document"] for record in batch],
            batch_size=args.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        collection.upsert(
            ids=[record["id"] for record in batch],
            documents=[record["document"] for record in batch],
            metadatas=[record["metadata"] for record in batch],
            embeddings=embeddings.tolist(),
        )
        stored = start + len(batch)
        if start == 0 or stored == len(records) or stored % (args.batch_size * 20) == 0:
            print(f"Stored {stored}/{len(records)} records", flush=True)
    print(f"Done: {collection.count()} records in {COLLECTION_NAME}")


if __name__ == "__main__":
    main()
