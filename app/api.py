"""FastAPI 라우터 초안 (docs/function_contracts.md 17장).

실행: 프로젝트 루트에서  uvicorn app.api:app --port 8000

- ChromaDB, 임베딩 모델, Gemini 클라이언트는 서버 시작 시 한 번만 만든다.
  (PolicySearchService는 생성 때 임베딩 모델을 로드하므로 요청마다 만들면 매우 느리다.)
- Gemini 호출이 동기 함수이므로 엔드포인트는 `async def`가 아니라 `def`로 둔다.
  FastAPI가 별도 스레드에서 실행해 서버 전체가 멈추지 않는다.
- 이 파일은 기존 서비스(repository, search_service, question_analyzer, answer_service)를
  호출만 한다. 검색·판정 로직을 여기에 다시 쓰지 않는다(계약서 16장).
- 응답 형식은 프론트엔드 `frontend/src/types/contract.ts`의 `[초안]` 타입과 같다.
"""

from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, replace
from typing import Annotated, Any, Callable, TypeVar

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StringConstraints

from .answer_service import AnswerGenerationError
from .config import VALIDATION_LOCAL_LIMIT, VALIDATION_NATIONAL_LIMIT
from .models import PolicySection, RegionSelection
from .question_analyzer import QuestionAnalysisError
from .relevance_service import RelevanceValidationError

logger = logging.getLogger("welfareone.api")
T = TypeVar("T")

# 질문 최대 길이: 프론트엔드 MAX_QUESTION_LENGTH(500)와 같은 값
Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


# BYOK(Bring Your Own Key): 사용자가 본인 Gemini 키를 요청 헤더로 보낸다.
# 서버는 키를 저장·로깅하지 않고, 요청마다 그 키로 Gemini 클라이언트를 만들어 쓴다.
API_KEY_HEADER = "X-Gemini-Api-Key"
_API_KEY_PATTERN = re.compile(r"^[\x21-\x7e]{20,256}$")  # 공백 없는 출력 가능한 ASCII
# 서버 .env의 키로 대신 처리할지 여부. 기본은 끔(공개 배포에서 운영자 키가 소진되지 않도록).
ALLOW_SERVER_KEY_ENV = "WELFAREONE_ALLOW_SERVER_KEY"


@dataclass
class Services:
    """요청 처리에 쓰는 서비스 묶음. 테스트에서는 가짜 객체로 바꿔 끼운다."""

    repository: Any  # PolicyRepository
    search: Any  # PolicySearchService
    analyzer: Any | None  # 서버 키로 만든 QuestionAnalyzer. 서버 키 폴백을 끄면 None
    answers: Any | None  # 서버 키로 만든 AnswerService. 서버 키 폴백을 끄면 None
    regions: dict[str, list[str]]  # DB를 다시 적재하기 전까지 바뀌지 않으므로 시작 시 한 번만 조회
    reranker: Any | None = None  # RerankerService. 테스트에서는 None 또는 가짜 객체
    relevance: Any | None = None  # RelevanceService. 사용자 키 폴백이 꺼지면 None
    analyzer_factory: Callable[[str], Any] | None = None  # 사용자 키 -> QuestionAnalyzer
    answers_factory: Callable[[str], Any] | None = None  # 사용자 키 -> AnswerService
    relevance_factory: Callable[[str], Any] | None = None  # 사용자 키 -> RelevanceService


def build_services() -> Services:
    # 무거운 모듈(torch, sentence-transformers)은 실제 서버를 띄울 때만 불러온다.
    from .answer_service import AnswerService
    from .config import PROJECT_DIR
    from .question_analyzer import QuestionAnalyzer, _load_env_file
    from .relevance_service import RelevanceService
    from .reranker_service import RerankerService
    from .repository import PolicyRepository
    from .search_service import PolicySearchService

    _load_env_file(PROJECT_DIR / ".env")  # 서버 키 폴백 플래그도 .env에서 읽을 수 있게 한다
    allow_server_key = os.getenv(ALLOW_SERVER_KEY_ENV, "").strip().lower() in {"1", "true", "yes"}

    repository = PolicyRepository()
    return Services(
        repository=repository,
        search=PolicySearchService(repository),
        # 폴백을 켠 경우에만 서버 키로 만든다(이때 GEMINI_API_KEY가 없으면 여기서 바로 실패한다).
        analyzer=QuestionAnalyzer() if allow_server_key else None,
        answers=AnswerService() if allow_server_key else None,
        regions=repository.list_regions(),
        reranker=RerankerService(),
        relevance=RelevanceService() if allow_server_key else None,
        analyzer_factory=lambda key: QuestionAnalyzer(api_key=key),
        answers_factory=lambda key: AnswerService(api_key=key),
        relevance_factory=lambda key: RelevanceService(api_key=key),
    )


# ---------------------------------------------------------------- 오류 (계약서 17장)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def _error_response(status: int, code: str, message: str, details: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details}},
    )


def _llm_error(exc: Exception) -> ApiError:
    """Gemini 호출 실패를 계약서 오류 코드로 바꾼다. 재시도는 서비스 안에서 이미 끝난 상태다."""
    cause = exc.__cause__
    code = getattr(cause, "code", None)
    if code == 429:
        return ApiError(429, "LLM_RATE_LIMITED", "AI 요청 한도에 도달했습니다.")
    # 잘못된 키: Gemini는 401/403, 또는 400 + "API key not valid" 메시지로 알려 준다.
    if code in (401, 403) or (code == 400 and "api key" in str(cause).lower()):
        return ApiError(401, "INVALID_API_KEY", "Gemini API 키가 올바르지 않습니다.")
    return ApiError(502, "LLM_RESPONSE_INVALID", "AI 응답을 처리하지 못했습니다.")


def _request_api_key(request: Request) -> str | None:
    """요청 헤더의 사용자 키. 없으면 None, 형식이 이상하면 401."""
    key = request.headers.get(API_KEY_HEADER, "").strip()
    if not key:
        return None
    if not _API_KEY_PATTERN.match(key):
        raise ApiError(401, "INVALID_API_KEY", "Gemini API 키 형식이 올바르지 않습니다.")
    return key


def _llm_service(request: Request, default: Any | None, factory: Callable[[str], Any] | None) -> Any:
    """사용자 키가 있으면 그 키로 만든 서비스, 없으면 서버 키 서비스, 둘 다 없으면 401."""
    key = _request_api_key(request)
    if key and factory is not None:
        return factory(key)
    if default is not None:
        return default
    raise ApiError(401, "API_KEY_REQUIRED", "Gemini API 키가 필요합니다.")


def _db(call: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    try:
        return call(*args, **kwargs)
    except Exception as exc:  # ChromaDB 오류는 종류가 다양해 한곳에서 묶어 처리한다
        logger.exception("database error")
        raise ApiError(500, "DATABASE_ERROR", "정책 데이터를 불러오지 못했습니다.") from exc


def _region_search_terms(region: RegionSelection) -> list[str]:
    """metadata 필터가 담당하는 지역 표현을 검색 문장에서 제거하기 위한 별칭 목록."""
    terms = {region.level1.strip(), region.level2.strip()}
    suffixes = ("특별자치시", "특별자치도", "특별시", "광역시", "자치시", "자치도", "시", "군", "구", "도")
    for value in tuple(terms):
        if not value:
            continue
        for suffix in suffixes:
            if value.endswith(suffix) and len(value) > len(suffix):
                stem = value[: -len(suffix)]
                terms.add(stem)
                if suffix in {"특별시", "광역시", "특별자치시"}:
                    terms.add(stem + "시")
                elif suffix in {"특별자치도", "자치도"}:
                    terms.add(stem + "도")
                break
    return sorted((term for term in terms if term), key=len, reverse=True)


def _search_query_without_region(query: str, region: RegionSelection) -> str:
    """지역 필터와 중복되는 지역명을 제거하되 검색 의미가 비면 원문을 유지한다."""
    cleaned = query
    for term in _region_search_terms(region):
        cleaned = cleaned.replace(term, " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,/·")
    return cleaned or query.strip()


_RELEVANCE_PRIORITY = {"direct": 0, "conditional": 1, "indirect": 2}


def _apply_relevance(candidates: list[Any], judgments: list[Any]) -> list[Any]:
    """검증 결과를 후보에 결합하고 unrelated를 제거한다."""
    by_id = {item.policy_id: item for item in judgments}
    related = []
    for candidate in candidates:
        judgment = by_id[candidate.policy_id]
        if judgment.relevance == "unrelated":
            continue
        related.append(replace(
            candidate,
            relevance=judgment.relevance,
            relevance_reason=judgment.reason,
            reasons=[*candidate.reasons, f"Gemini 적합성 {judgment.relevance}: {judgment.reason}"],
        ))
    return sorted(
        related,
        key=lambda item: (
            _RELEVANCE_PRIORITY[item.relevance],
            -(item.reranker_score if item.reranker_score is not None else float("-inf")),
        ),
    )


# ---------------------------------------------------------------- 요청 모델


class RegionBody(BaseModel):
    level1: str = Field(min_length=1)
    level2: str | None = ""  # 없으면 ""(DB가 광역 정책을 region_level2 == ""로 저장). null도 허용


class SearchBody(BaseModel):
    question: Question
    region: RegionBody
    age: int | None = Field(default=None, ge=0, le=120)


class AskBody(BaseModel):
    question: Question
    policy_title: str | None = None


# ---------------------------------------------------------------- 앱


def create_app(services: Services | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.services = services or build_services()
        yield

    app = FastAPI(title="WelfareOne API", lifespan=lifespan)

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _error_response(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(part) for part in error["loc"][1:]), "message": error["msg"]}
            for error in exc.errors()
        ]
        return _error_response(422, "INVALID_REQUEST", "요청 형식이 올바르지 않습니다.", details)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error")
        return _error_response(500, "INTERNAL_ERROR", "서버에서 문제가 발생했습니다.")

    def svc(request: Request) -> Services:
        return request.app.state.services

    def sections_or_404(services: Services, policy_id: str) -> list[PolicySection]:
        sections = _db(services.repository.get_policy_sections, policy_id)
        if not sections:
            raise ApiError(404, "POLICY_NOT_FOUND", "정책을 찾을 수 없습니다.")
        return sections

    @app.get("/health")
    def health() -> dict[str, str]:
        # 모델·DB 로딩은 lifespan에서 끝나야 요청을 받기 시작하므로, 응답이 오면 준비가 끝난 것이다.
        return {"status": "ok"}

    @app.get("/regions")
    def list_regions(request: Request) -> dict[str, list[str]]:
        return svc(request).regions

    @app.post("/policies/search")
    def search_policies(body: SearchBody, request: Request) -> dict[str, Any]:
        services = svc(request)
        level2 = body.region.level2 or ""
        districts = services.regions.get(body.region.level1)
        if districts is None or (level2 and level2 not in districts):
            raise ApiError(400, "INVALID_REGION", "선택한 지역을 확인할 수 없습니다.")
        region = RegionSelection(level1=body.region.level1, level2=level2)

        analyzer = _llm_service(request, services.analyzer, services.analyzer_factory)
        try:
            analysis = analyzer.analyze_question(body.question)
        except ValueError as exc:
            raise ApiError(400, "INVALID_REQUEST", str(exc)) from exc
        except QuestionAnalysisError as exc:
            raise _llm_error(exc) from exc

        retrieval_query = _search_query_without_region(analysis.search_query, region)
        # 검색 결과가 없어도 오류가 아니라 빈 목록으로 응답한다(계약서 9장 검색 규칙 5).
        result = services.search.search_policies(
            retrieval_query,
            region,
            age=body.age,
        )
        candidates = result.local_policies + result.national_policies
        reranked = (
            services.reranker.rerank(retrieval_query, candidates)
            if services.reranker is not None
            else candidates
        )
        # 리랭커는 임계값 판정이 아니라 Gemini에 넘길 상위 후보 선택에만 사용한다.
        local_for_validation = [
            item for item in reranked if item.metadata.get("source") == "local"
        ][:VALIDATION_LOCAL_LIMIT]
        national_for_validation = [
            item for item in reranked if item.metadata.get("source") == "national"
        ][:VALIDATION_NATIONAL_LIMIT]
        validation_candidates = local_for_validation + national_for_validation

        validation_status = "fallback"
        local_policies = local_for_validation
        national_policies = national_for_validation
        validator = None
        if services.relevance is not None or services.relevance_factory is not None:
            validator = _llm_service(request, services.relevance, services.relevance_factory)
        if validator is not None:
            try:
                validation = validator.validate_candidates(
                    question=body.question,
                    analysis=analysis,
                    region=region,
                    age=body.age,
                    candidates=validation_candidates,
                )
                validated = _apply_relevance(validation_candidates, validation.judgments)
                validation_status = validation.status
                local_policies = [item for item in validated if item.metadata.get("source") == "local"]
                national_policies = [item for item in validated if item.metadata.get("source") == "national"]
            except RelevanceValidationError:
                logger.warning("relevance validation failed; returning reranker fallback", exc_info=True)
        return {
            "analysis": {
                "route": analysis.route,
                "intents": analysis.intents,
                "search_query": analysis.search_query,
            },
            "validation_status": validation_status,
            "local_policies": [asdict(item) for item in local_policies],
            "national_policies": [asdict(item) for item in national_policies],
        }

    @app.get("/policies/{policy_id}")
    def get_policy(policy_id: str, request: Request) -> dict[str, Any]:
        services = svc(request)
        sections = sections_or_404(services, policy_id)
        grouped: dict[str, list[str]] = {}
        for item in sections:
            grouped.setdefault(item.section, []).append(item.document)
        meta = _db(services.repository.get_policy_meta, policy_id) or {}
        return {
            "policy_id": policy_id,
            "title": meta.get("title") or None,
            "region_text": meta.get("region_text") or None,
            "sections": grouped,
        }

    @app.post("/policies/{policy_id}/ask")
    def ask_policy(policy_id: str, body: AskBody, request: Request) -> dict[str, Any]:
        services = svc(request)
        contexts = sections_or_404(services, policy_id)

        analyzer = _llm_service(request, services.analyzer, services.analyzer_factory)
        answers = _llm_service(request, services.answers, services.answers_factory)
        try:
            analysis = analyzer.analyze_question(
                question=body.question,
                current_policy_id=policy_id,
                current_policy_title=body.policy_title,
            )
        except ValueError as exc:
            raise ApiError(400, "INVALID_REQUEST", str(exc)) from exc
        except QuestionAnalysisError as exc:
            raise _llm_error(exc) from exc

        base = {"route": analysis.route, "intents": analysis.intents}
        # 선택한 정책에 대한 질문이 아니면 답변을 만들지 않는다(CLI와 같은 분기).
        if analysis.route != "current_policy_question":
            return {**base, "answer": None}

        try:
            answer = answers.generate_answer(
                question=body.question,
                policy_id=policy_id,
                contexts=contexts,
                requested_sections=analysis.requested_sections,
                policy_title=body.policy_title,
            )
        except ValueError as exc:
            raise ApiError(400, "INVALID_REQUEST", str(exc)) from exc
        except AnswerGenerationError as exc:
            raise _llm_error(exc) from exc
        return {**base, "answer": jsonable_encoder(asdict(answer))}

    return app


app = create_app()
