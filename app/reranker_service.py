"""벡터검색 후보를 질문과 candidate_summary의 관련성으로 재정렬한다."""

from __future__ import annotations

import re
import threading
from dataclasses import replace
from typing import Any

import torch
from sentence_transformers import CrossEncoder

from .config import RERANKER_BATCH_SIZE, RERANKER_MAX_LENGTH, RERANKER_MODEL
from .models import PolicyCandidate


_SUMMARY_HEADER = re.compile(
    r"^(정책명|지역·소관|생애주기|개요|대상·조건|지원 내용):\s*(.*)$"
)
_RERANKER_SECTIONS = {"정책명", "개요", "대상·조건", "지원 내용"}


def build_reranker_text(summary: str) -> str:
    """candidate_summary에서 정책 관련성 판단에 필요한 섹션만 남긴다.

    지역은 검색의 metadata 필터가 이미 처리하고, 생애주기는 여러 정책에 반복되어
    관련 없는 후보의 점수를 올릴 수 있으므로 리랭커 입력에서는 제외한다.
    구조화된 헤더가 없는 테스트·이전 데이터는 원문을 그대로 사용한다.
    """
    selected: list[str] = []
    current_section: str | None = None
    found_header = False

    for raw_line in summary.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _SUMMARY_HEADER.match(line)
        if match:
            found_header = True
            current_section = match.group(1)
            if current_section in _RERANKER_SECTIONS:
                value = match.group(2).strip()
                selected.append(f"{current_section}: {value}" if value else f"{current_section}:")
            continue
        if current_section in _RERANKER_SECTIONS:
            selected.append(line)

    return "\n".join(selected) if found_header and selected else summary.strip()


class RerankerService:
    """서버 시작 시 모델을 한 번 로드하고 요청마다 후보 쌍만 추론한다."""

    def __init__(
        self,
        model_name: str = RERANKER_MODEL,
        max_length: int = RERANKER_MAX_LENGTH,
        batch_size: int = RERANKER_BATCH_SIZE,
        device: str | None = None,
        model: Any | None = None,
    ) -> None:
        self.batch_size = batch_size
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = model or CrossEncoder(
            model_name,
            device=self.device,
            max_length=max_length,
            local_files_only=True,
        )
        # 하나의 GPU 모델에 여러 FastAPI 작업 스레드가 동시에 진입하지 않게 한다.
        self._predict_lock = threading.Lock()

    def rerank(
        self,
        question: str,
        candidates: list[PolicyCandidate],
    ) -> list[PolicyCandidate]:
        """후보를 삭제하지 않고 리랭커 점수만 부여해 내림차순으로 반환한다."""
        if not candidates:
            return []

        pairs = [
            (question, build_reranker_text(candidate.summary))
            for candidate in candidates
        ]
        with self._predict_lock:
            scores = self.model.predict(
                pairs,
                batch_size=self.batch_size,
                show_progress_bar=False,
            )

        reranked = [
            replace(
                candidate,
                reranker_score=float(score),
                reasons=[*candidate.reasons, f"리랭커 관련성 {float(score):.6f}"],
            )
            for candidate, score in zip(candidates, scores)
        ]
        return sorted(
            reranked,
            key=lambda candidate: candidate.reranker_score
            if candidate.reranker_score is not None
            else float("-inf"),
            reverse=True,
        )
