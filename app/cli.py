from collections import defaultdict

from .answer_service import AnswerGenerationError, AnswerService
from .models import RegionSelection
from .question_analyzer import QuestionAnalysisError, QuestionAnalyzer
from .repository import PolicyRepository
from .search_pipeline import run_search
from .search_service import PolicySearchService


SECTION_LABELS = {
    "overview": "정책 개요",
    "target_criteria": "지원 대상 및 선정 조건",
    "benefit": "지원 내용",
    "application": "신청 방법",
    "documents": "필요 서류",
    "contact_source": "문의처 및 출처",
    "administrative": "행정 정보",
}


def choose(prompt: str, values: list[str], allow_skip: bool = False) -> str:
    while True:
        print()
        for number, value in enumerate(values, start=1):
            print(f"{number}. {value}")
        if allow_skip:
            print("0. 선택하지 않음")
        raw = input(f"{prompt}: ").strip()
        if allow_skip and raw == "0":
            return ""
        if raw.isdigit() and 1 <= int(raw) <= len(values):
            return values[int(raw) - 1]
        print("목록에 있는 번호를 입력해주세요.")


def choose_region(repository: PolicyRepository) -> RegionSelection:
    regions = repository.list_regions()
    level1 = choose("시·도를 선택하세요", list(regions))
    districts = regions[level1]
    level2 = choose("시·군·구를 선택하세요", districts, allow_skip=True) if districts else ""
    return RegionSelection(level1=level1, level2=level2)


def read_age() -> int | None:
    while True:
        raw = input("만 나이를 입력하세요(건너뛰려면 Enter): ").strip()
        if not raw:
            return None
        if raw.isdigit() and 0 <= int(raw) <= 120:
            return int(raw)
        print("0부터 120 사이의 숫자를 입력해주세요.")


def show_policy_detail(repository: PolicyRepository, policy_id: str) -> None:
    grouped = defaultdict(list)
    for item in repository.get_policy_sections(policy_id):
        grouped[item.section].append(item.document)

    print("\n" + "=" * 70)
    for section in (
        "overview", "target_criteria", "benefit", "application",
        "documents", "contact_source",
    ):
        documents = grouped.get(section)
        if not documents:
            continue
        print(f"\n[{SECTION_LABELS.get(section, section)}]")
        for document in documents:
            print(document)
    print("\n※ 자격 조건은 공식 원문이며, 아직 자동 자격 판정은 수행하지 않습니다.")
    print("=" * 70)


def show_candidates(title: str, candidates, start_number: int = 1) -> None:
    print(f"\n[{title}]")
    if not candidates:
        print("관련 정책을 찾지 못했습니다.")
        return
    for number, item in enumerate(candidates, start=start_number):
        print(f"{number}. {item.title}")
        print(f"   {item.region_text or '중앙부처'}")


def ask_selected_policy(
    repository: PolicyRepository,
    question_analyzer: QuestionAnalyzer,
    answer_service: AnswerService,
    selected,
) -> bool:
    """선택 정책의 후속 질문을 반복 처리한다. 종료 요청이면 True를 반환한다."""
    contexts = repository.get_policy_sections(selected.policy_id)
    while True:
        print(f"\n현재 선택 정책: {selected.title}")
        question = input(
            "정책에 대해 질문하세요(원문: raw, 다른 검색: 0, 종료: q): "
        ).strip()
        if question.lower() in {"q", "quit", "종료"}:
            return True
        if question == "0":
            return False
        if question.lower() == "raw":
            show_policy_detail(repository, selected.policy_id)
            continue
        if not question:
            continue

        try:
            analysis = question_analyzer.analyze_question(
                question=question,
                current_policy_id=selected.policy_id,
                current_policy_title=selected.title,
            )
            print(
                f"질문 분석: {analysis.route} / {', '.join(analysis.intents)}"
            )
            if analysis.route != "current_policy_question":
                print(
                    "현재 선택한 정책에 대한 질문으로 확인되지 않았습니다. "
                    "다른 정책을 찾으려면 0을 입력해주세요."
                )
                continue
            answer = answer_service.generate_answer(
                question=question,
                policy_id=selected.policy_id,
                policy_title=selected.title,
                contexts=contexts,
                requested_sections=analysis.requested_sections,
            )
        except (QuestionAnalysisError, AnswerGenerationError, ValueError) as exc:
            print(f"답변을 생성하지 못했습니다: {exc}")
            continue

        print(f"\n답변: {answer.answer}")
        if answer.evidence:
            print("근거:")
            for evidence in answer.evidence:
                print(f"- {evidence}")
        if answer.resources:
            print("참고 자료:")
            for resource in answer.resources:
                action = "다운로드" if resource.resource_type == "attachment" else "바로가기"
                print(f"- [{action}] {resource.label}")
                print(f"  {resource.url}")
        if not answer.grounded:
            print("※ 제공된 공식 원문만으로 충분히 확인되지 않은 답변입니다.")


def run() -> None:
    print("WelfareOne 터미널 프로토타입")
    print("기존 ChromaDB에서 지역별 청년 복지정책을 검색합니다.")
    repository = PolicyRepository()
    print(f"DB 연결 완료: {repository.count():,}개 레코드")
    search_service = PolicySearchService(repository)
    print("임베딩 모델 준비 완료")
    try:
        question_analyzer = QuestionAnalyzer()
        answer_service = AnswerService()
    except (QuestionAnalysisError, AnswerGenerationError) as exc:
        print(f"Gemini 연결 준비 실패: {exc}")
        print(".env 설정 후 다시 실행해주세요.")
        return
    print("Gemini 질문 분석 준비 완료")

    region = choose_region(repository)
    age = read_age()

    while True:
        print(f"\n현재 지역: {region.label} / 나이: {age if age is not None else '미입력'}")
        question = input("궁금한 상황이나 정책을 입력하세요(종료: q): ").strip()
        if question.lower() in {"q", "quit", "종료"}:
            break
        if not question:
            continue

        try:
            analysis = question_analyzer.analyze_question(question)
        except (QuestionAnalysisError, ValueError) as exc:
            print(f"질문을 분석하지 못했습니다: {exc}")
            print("잠시 후 다시 질문해주세요.")
            continue

        print(
            f"질문 분석: {analysis.route} / {', '.join(analysis.intents)}"
            f" / 검색어: {analysis.search_query}"
        )
        result = run_search(analysis, search_service, region, age, question)  # 터미널은 LLM 재판정 없이 거리 기반
        local_candidates = result.local_policies
        national_candidates = result.national_policies
        candidates = local_candidates + national_candidates
        if not candidates:
            print("조건에 맞는 정책 후보를 찾지 못했습니다.")
            continue

        show_candidates("내 지역 정책", local_candidates)
        show_candidates(
            "중앙부처 정책",
            national_candidates,
            start_number=len(local_candidates) + 1,
        )

        raw = input("상세 확인할 정책 번호(다시 질문: 0): ").strip()
        if raw == "0":
            continue
        if not raw.isdigit() or not 1 <= int(raw) <= len(candidates):
            print("올바른 정책 번호가 아니므로 질문 입력으로 돌아갑니다.")
            continue
        selected = candidates[int(raw) - 1]
        print(f"\n선택한 정책: {selected.title}")
        should_end = ask_selected_policy(
            repository,
            question_analyzer,
            answer_service,
            selected,
        )
        if should_end:
            break

    print("WelfareOne을 종료합니다.")
