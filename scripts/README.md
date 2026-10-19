# scripts 안내

프로젝트 루트에서 `python scripts/<파일>`로 실행합니다. 모두 DB(`data/chroma`)를 직접 고치지 않는 것이 원칙이며, 적재 스크립트는 **재적재가 필요한 때만** 팀 합의 후 실행합니다.

## 현행 스크립트

| 순서/용도 | 파일 | 설명 |
|---|---|---|
| 데이터 수집 1 | `download_welfare.py` | 복지로 공개 API에서 목록·상세 XML을 `data/raw`로 내려받음 |
| 데이터 갱신 | `update_welfare_incremental.py` | 새로 생기거나 바뀐 정책만 다시 수집(기본은 점검만, `--apply`로 반영). DB는 건드리지 않음 |
| DB 갱신 | `build_chroma_update.py` | 갱신된 정책만 기존 DB **복사본**에 반영해 새 DB 폴더를 만듦(원본 `data/chroma`는 읽기만). `--verify-only`로 호환성 검증 |
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

## 갱신된 정책을 검색 DB(`data/chroma`)에 반영하기 (`build_chroma_update.py`)

저장소의 `import_welfare_chroma_qwen_v3.py`는 현재 DB와 구조가 다르다(서식·첨부 자료를 `attachments`로 분리, 메타데이터 3개 추가). 전체를 다시 적재하면 앱·계약서가 쓰는 `documents` 섹션이 사라진다. 그래서 이 스크립트는 같은 레코드 생성 로직을 쓰되 기존 형식으로 되돌려, **갱신된 정책만** 복사본에 반영한다.

```powershell
# 1) 변환이 기존 DB와 일치하는지만 확인(아무것도 만들지 않음)
python scripts/build_chroma_update.py --out-db D:/chroma_update_20261019 --report-date 20261019 --verify-only
# 2) 복사본 생성 + 대상 정책 교체 + 반영 후 검증
python scripts/build_chroma_update.py --out-db D:/chroma_update_20261019 --report-date 20261019
```

- 대상 정책은 수집 보고서(`data/raw/<source>/update_reports/update_<날짜>.json`)의 `added`·`updated`다. 대상이 아닌 정책의 레코드는 기존과 **완전히 같아야** 하며, 다르면 중단한다.
- 2026-10-19 실행 결과: 대상 16개 정책(삭제 108건 → 추가 140건), 11,850건 → 11,882건, 나머지 1,406개 정책 11,742건 동일. 공유용 설명 파일은 `data/updates/MANIFEST_chroma_20261019.json`.
- 팀에는 새 DB 폴더를 압축한 파일(`chroma_update_<날짜>.zip`)과 위 설명 파일을 함께 공유한다. 팀원은 `data/chroma`를 백업한 뒤 압축을 푼 `chroma` 폴더로 교체한다.
