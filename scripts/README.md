# scripts 안내

프로젝트 루트에서 `python scripts/<파일>`로 실행합니다. 모두 DB(`data/chroma`)를 직접 고치지 않는 것이 원칙이며, 적재 스크립트는 **재적재가 필요한 때만** 팀 합의 후 실행합니다.

## 현행 스크립트

| 순서/용도 | 파일 | 설명 |
|---|---|---|
| 데이터 수집 1 | `download_welfare.py` | 복지로 공개 API에서 목록·상세 XML을 `data/raw`로 내려받음 |
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
