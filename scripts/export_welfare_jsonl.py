"""Export readable JSONL views of WelfareOne source XML and Chroma records."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import chromadb


DEFAULT_COLLECTION = "welfare_policy_sections_qwen_v3"


def clean(value: str | None) -> str:
    return (value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def element_value(node: ET.Element):
    """Convert an XML element to JSON while preserving nested and repeated tags."""
    if not len(node):
        return clean(node.text)
    grouped: dict[str, list[object]] = defaultdict(list)
    for child in node:
        grouped[child.tag].append(element_value(child))
    return {
        tag: values[0] if len(values) == 1 else values
        for tag, values in grouped.items()
    }


def first(detail: dict, *names: str) -> str:
    for name in names:
        value = detail.get(name)
        if isinstance(value, str) and value:
            return value
    return ""


def export_policies(project: Path, output: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        for source in ("local", "national"):
            paths = sorted((project / "data" / "raw" / source / "detail").glob("*.xml"))
            counts[source] = len(paths)
            for path in paths:
                root = ET.parse(path).getroot()
                detail = element_value(root)
                if not isinstance(detail, dict):
                    raise ValueError(f"Unexpected XML root: {path}")
                service_id = first(detail, "servId") or path.stem
                record = {
                    "policy_id": f"{source}:{service_id}",
                    "source": source,
                    "service_id": service_id,
                    "title": first(detail, "servNm"),
                    "region": {
                        "level1": first(detail, "ctpvNm"),
                        "level2": first(detail, "sggNm"),
                    },
                    "source_file": str(path.relative_to(project)).replace("\\", "/"),
                    # Complete detail response, including API-specific fields.
                    "detail": detail,
                }
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return counts


def export_chroma(db_path: Path, collection_name: str, output: Path,
                  batch_size: int) -> tuple[int, dict]:
    client = chromadb.PersistentClient(path=str(db_path))
    collection = client.get_collection(collection_name)
    total = collection.count()
    written = 0
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        for offset in range(0, total, batch_size):
            result = collection.get(
                limit=min(batch_size, total - offset),
                offset=offset,
                include=["documents", "metadatas"],
            )
            documents = result.get("documents") or []
            metadatas = result.get("metadatas") or []
            for record_id, document, metadata in zip(result["ids"], documents, metadatas):
                record = {
                    "id": record_id,
                    "document": document,
                    "metadata": metadata,
                }
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                written += 1
    return written, collection.metadata or {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()

    project = args.project.resolve()
    db_path = (args.db_path or project / "data" / "chroma").resolve()
    output_dir = project / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)
    policies_path = output_dir / "policies.jsonl"
    chroma_path = output_dir / "chroma_records.jsonl"

    policy_counts = export_policies(project, policies_path)
    chroma_count, collection_metadata = export_chroma(
        db_path, args.collection, chroma_path, args.batch_size
    )
    manifest = {
        "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "collection": args.collection,
        "collection_metadata": collection_metadata,
        "policy_counts": policy_counts,
        "policy_total": sum(policy_counts.values()),
        "chroma_record_count": chroma_count,
        "embeddings_included_in_jsonl": False,
        "files": {
            "policies": str(policies_path.relative_to(project)).replace("\\", "/"),
            "chroma_records": str(chroma_path.relative_to(project)).replace("\\", "/"),
        },
    }
    manifest_path = output_dir / "export_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
