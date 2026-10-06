from collections import defaultdict

import chromadb

from .config import CHROMA_PATH, COLLECTION_NAME
from .models import PolicySection


class PolicyRepository:
    """ChromaDB 접근을 한곳에 모아 CLI와 FastAPI가 함께 사용하게 한다."""

    def __init__(self) -> None:
        self.client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        self.collection = self.client.get_collection(COLLECTION_NAME)

    def count(self) -> int:
        return self.collection.count()

    def list_regions(self) -> dict[str, list[str]]:
        result = self.collection.get(
            where={"section": "candidate_summary"},
            include=["metadatas"],
        )
        regions: dict[str, set[str]] = defaultdict(set)
        for metadata in result["metadatas"]:
            level1 = str(metadata.get("region_level1", "")).strip()
            level2 = str(metadata.get("region_level2", "")).strip()
            if level1:
                regions[level1].add(level2)
        return {
            level1: sorted(value for value in level2_values if value)
            for level1, level2_values in sorted(regions.items())
        }

    def vector_query(self, query_vector: list[float], where: dict, limit: int) -> dict:
        return self.collection.query(
            query_embeddings=[query_vector],
            n_results=limit,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

    def get_policy_meta(self, policy_id: str) -> dict[str, str] | None:
        """정책명·지역 표기를 candidate_summary 메타데이터에서 읽는다. 없으면 None."""
        result = self.collection.get(
            where={"$and": [{"policy_id": {"$eq": policy_id}}, {"section": "candidate_summary"}]},
            include=["metadatas"],
            limit=1,
        )
        if not result["metadatas"]:
            return None
        metadata = result["metadatas"][0]
        return {
            "title": str(metadata.get("title", "")),
            "region_text": str(metadata.get("region_text", "")),
        }

    def get_policy_sections(self, policy_id: str) -> list[PolicySection]:
        result = self.collection.get(
            where={"policy_id": {"$eq": policy_id}},
            include=["documents", "metadatas"],
        )
        sections = [
            PolicySection(
                section=str(metadata.get("section", "")),
                chunk_index=int(metadata.get("chunk_index", 0)),
                document=document,
            )
            for document, metadata in zip(result["documents"], result["metadatas"])
            if metadata.get("section") != "candidate_summary"
        ]
        return sorted(sections, key=lambda item: (item.section, item.chunk_index))

