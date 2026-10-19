# docs 안내

어떤 문서를 먼저 읽을지, 어떤 문서가 팀 공유용인지 정리한 목록입니다.

| 문서 | 용도 | 상태 | Git 공유 |
|---|---|---|---|
| `function_contracts.md` | 팀 공통 계약서(필드명, 함수 입출력, API, 오류 코드) | 기준 문서. **팀 합의 없이 수정 금지** | 공유 |
| `contract_update_proposal.md` | 계약서와 실제 구현이 어긋난 부분의 수정 제안 | 제안(팀 검토 전) | 공유 |
| `SEARCH_QUALITY_CHANGES.md` | 검색 관련도 개선 브랜치의 변경 내용·측정 근거 | 리뷰용 | 공유 |
| `DIRECTION_C_PLAN.md` | 자격 판정 이후 단계(서류·초안·LangGraph) 작업 계획 | 계획 초안(팀 합의 전) | 공유 |
| `eligibility_design_draft.md` | 자격 판정 설계 초안 | 초안(팀 합의 전) | 공유 |
| `CLEANUP_COMMITS.md` | 폴더 구조 정리 브랜치의 커밋별 변경 설명 | 리뷰용 | 공유 |
| `labeling/labeling_guide.pdf` | 사람 라벨링 가이드(원본 `labeling_guide.html`) | 라벨링 작업용 | 공유 가능 |
| `CHANGELOG_2026-10-06.md` | 2026-10-06 변경 내역 | 개인 메모 참조 포함 → 정리 후 공유 | 미추적 |
| `HANDOFF_BRANCH.md` | 브랜치 협업 인수인계 | 개인 메모 참조 포함 → 정리 후 공유 | 미추적 |
| `HANDOFF.md`, `HANDOFF_NEXT.md` | 개인 인수인계 메모 | 개인용 | **Git 제외**(`.git/info/exclude`) |

## 읽는 순서 (새로 합류한 경우)

1. 저장소 루트 `README.md` — 실행 방법
2. `function_contracts.md` — 이름과 형식의 기준
3. `SEARCH_QUALITY_CHANGES.md` — 현재 검색 동작과 정한 값(거리 0.60/0.55/0.50 등)과 근거
4. `DIRECTION_C_PLAN.md` — 앞으로 할 작업

## 문서 작성 규칙

- 계약서와 어긋나는 구현을 했다면 계약서를 직접 고치지 말고 `contract_update_proposal.md`에 항목을 추가합니다.
- 개인 메모(`HANDOFF*.md`)의 내용을 공유 문서에서 참조하지 않습니다. 필요한 내용은 공유 문서로 옮겨 적습니다.
