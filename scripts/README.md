# scripts 안내

프로젝트 루트에서 `python scripts/<파일>`로 실행합니다. 모두 DB(`data/chroma`)를 직접 고치지 않는 것이 원칙이며, 적재 스크립트는 **재적재가 필요한 때만** 팀 합의 후 실행합니다.

## 현행 스크립트

| 순서/용도 | 파일 | 설명 |
|---|---|---|
| 데이터 수집 1 | `download_welfare.py` | 복지로 공개 API에서 목록·상세 XML을 `data/raw`로 내려받음 |
| 데이터 갱신 | `update_welfare_incremental.py` | 새로 생기거나 바뀐 정책만 다시 수집(기본은 점검만, `--apply`로 반영). DB는 건드리지 않음 |
| 데이터 수집 2 | `export_welfare_jsonl.py` | XML을 읽기 쉬운 JSONL(`data/processed`)로 변환 |
| DB 적재 | `import_welfare_chroma_qwen_v3.py` | 현재 쓰는 컬렉션(`welfare_policy_sections_qwen_v3`)을 만드는 적재기 |
| 측정 | `measure_search_distance.py` | 평가 280문항으로 검색 거리 하한 후보별 정답 보존·무의미 질문 잔존을 측정(읽기 전용) |
| 라벨링 | `make_labeling_sheet.py` | 상황형 질문의 후보를 뽑아 사람 라벨링용 시트와 정답 키를 만듦(Gemini 호출) |

## 구버전·조사용 (현재 파이프라인에서 쓰지 않음, 기록용으로 보관)

| 파일 | 설명 |
|---|---|
| `import_welfare_chroma.py` | 초기 적재기(의미 단위 섹션 컬렉션). `_qwen_v3`로 대체됨 |
| `import_welfare_chroma_v2.py` | 두 번째 적재기(모든 XML 필드를 짧은 레코드로). `_qwen_v3`로 대체됨 |
| `inspect_local_welfare_all.py` | 지자체 복지서비스 전체 목록 누락 조사(결과: `data/investigation/`, Git 제외) |
| `inspect_youthcenter_api.py` | 온통청년 API 응답 형식 조사(결과: `data/investigation/`, Git 제외) |

> 파일 이동·삭제는 하지 않았습니다. 정리(`legacy/` 폴더 이동 등)는 팀 합의 후 진행합니다.

## 데이터 증분 갱신 (`update_welfare_incremental.py`)

```powershell
$env:WELFARE_API_KEY_LOCAL = "<지자체 인증키>"        # 키는 코드·파일에 남기지 않는다
python scripts/update_welfare_incremental.py local            # 점검만: 목록을 받아 신규/수정 정책 수를 보여 준다
python scripts/update_welfare_incremental.py local --apply    # 신규/수정 정책의 상세 XML만 받아 data/raw에 반영
$env:WELFARE_API_KEY_NATIONAL = "<중앙부처 인증키>"
python scripts/update_welfare_incremental.py national --apply
```

- 지자체(local)는 목록의 `lastModYmd`와 저장된 상세 XML의 `lastModYmd`를 비교한다. 중앙부처(national)는 수정일이 없어 모든 상세를 받아 내용 해시로 비교한다(호출 한도에 걸리면 `update_state.json`으로 이어받는다).
- 바뀐 상세는 덮어쓰기 전에 `data/raw/<source>/detail_prev/<날짜>/`로 옮기고, 목록 파일은 모든 반영이 끝났을 때만 새 목록으로 바꾼다(옛 목록은 `list_prev_<날짜>/`). 결과는 `update_reports/update_<날짜>.json`.
- **ChromaDB 반영은 이 스크립트의 범위가 아니다.** 반영 대상 ID는 보고서의 `added`/`updated`로 확인하고, 재적재 여부는 팀 합의 후 결정한다.
