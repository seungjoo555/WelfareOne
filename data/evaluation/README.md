# data/evaluation 안내

평가 데이터와 결과 파일입니다. **기존 파일은 논문·측정의 근거이므로 수정하지 않습니다.**

## 평가 질문 (정책 이름을 겨냥한 질문 + 정답 정책)

| 파일 | 내용 |
|---|---|
| `welfareone_rag_eval_280.csv` | 현행 평가셋 280문항. 열: `id, region, age, question, expected_policy_id, answer, evidence, source, question_type, author, input_file`. 거리 하한 측정(`scripts/measure_search_distance.py`)에 사용 |
| `welfareone_rag_eval_200.csv` | 이전 200문항 버전 |

## 검색 결과 기록 (벡터 검색 단독 실험)

| 파일 | 내용 |
|---|---|
| `rag_vector_only_results.csv` / `rag_vector_only_results2.csv` | 지역 필터 없이 벡터 검색만 한 결과(200/280문항) |
| `rag_vector_region_filtered_results.csv` | 지역 필터 적용 결과 |
| `rag_vector_region_comparison.csv` | 지역 필터 적용 전후 순위 비교 |
| `rag_vector_region_summary.csv` | 방식별 Hit@1/3/5, MRR 요약 |

## RAGAS 평가 결과 (답변 품질)

`welfareone_ragas_*.xlsx`, `paper_rag_*.xlsx`, `paper_ragas_checkpoint.csv`: 논문용 RAG·RAGAS 평가 산출물. `*_manual_reviewed`는 수동 검토를 반영한 버전, `*_before_manual_review`는 검토 전 버전입니다. 재현 노트북은 `tests/test_RAG.ipynb`, `tests/test_RAGAS.ipynb`.

## 상황형 질문 평가 (사람 라벨링)

| 파일 | 내용 |
|---|---|
| `situational_questions_template.csv` | 팀원이 쓸 상황형·구어체 질문 양식 |
| `labeling/` | `scripts/make_labeling_sheet.py`가 만드는 라벨러별 시트(`sheet_*.csv`)와 정답 키 |

- `labeling/labeling_key_PRIVATE.csv`는 거리·점수가 들어 있어 **라벨러에게 주거나 커밋하지 않습니다**(`.gitignore`에 등록됨).
- 작업 방법은 `docs/labeling/labeling_guide.pdf`를 보세요.
