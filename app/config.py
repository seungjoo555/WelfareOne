import os
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
CHROMA_PATH = PROJECT_DIR / "data" / "chroma"
COLLECTION_NAME = "welfare_policy_sections_qwen_v3"
EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
RERANKER_MAX_LENGTH = int(os.getenv("RERANKER_MAX_LENGTH", "512"))
RERANKER_BATCH_SIZE = int(os.getenv("RERANKER_BATCH_SIZE", "8"))
# 리랭커가 재정렬할 후보 수(범위별). CPU는 후보 1쌍에 약 0.3초라 작게, GPU는 넉넉히 둔다(2026-10-19 측정).
# RERANKER_POOL로 장치와 상관없이 직접 지정할 수 있다.
RERANKER_POOL_CPU = int(os.getenv("RERANKER_POOL_CPU", "12"))
RERANKER_POOL_GPU = int(os.getenv("RERANKER_POOL_GPU", "30"))

# 현재 적재된 DB의 실제 섹션명이다.
DETAIL_SECTIONS = (
    "overview",
    "target_criteria",
    "benefit",
    "application",
    "documents",
    "contact_source",
)
