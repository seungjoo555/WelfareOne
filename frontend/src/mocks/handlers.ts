import { delay, http, HttpResponse } from "msw";
import type {
  AskRequest,
  AskResponse,
  PolicyCandidate,
  PolicyDetail,
  Regions,
  SearchRequest,
  SearchResponse,
} from "../types/contract";

// 개발용 가짜 응답이다. 정책 이름과 내용은 모두 예시이며 실제 정책이 아니다.
// 질문에 아래 키워드를 넣으면 상황을 바꿔 볼 수 있다.
//   "없음"     → 검색 결과 0건
//   "에러"     → 429 LLM_RATE_LIMITED
//   "날씨"     → (정책 선택 후) 현재 정책 질문이 아님 분기
//   "근거없음" → (정책 선택 후) grounded=false 답변
//   "관련낮음" → 관련도 낮은 후보(거리 0.50 초과)가 "더 보기"로 접히는지 확인
//   "재판정"   → 서버가 LLM으로 판정한 응답(relevance_checked)에서 판정 결과대로 접히는지 확인
//   "더보기"   → 지자체 8개·중앙부처 5개: 3개씩 "다음/이전" 쪽 넘김 확인
//   "키없음"   → 401 API_KEY_REQUIRED (API 키 입력 창이 열리는지 확인)
//   "키오류"   → 401 INVALID_API_KEY

const REGIONS: Regions = {
  서울특별시: ["관악구", "용산구"],
  경기도: ["성남시"],
  세종특별자치시: [], // 시·군·구가 없는 지역 케이스
};

const apiError = (status: number, code: string, message: string) =>
  HttpResponse.json({ error: { code, message, details: null } }, { status });

// 실제 DB의 candidate_summary 문서와 같은 여러 줄 형식(정책명/지역·소관/생애주기/개요/대상·조건/지원 내용)
const summaryText = (title: string, region: string, overview: string) =>
  [
    `정책명: ${title}`,
    `지역·소관: ${region}`,
    "생애주기: 청소년, 청년",
    `개요: ${overview}`,
    "대상·조건: 해당 지역 거주 청년 (mock 데이터)",
    "지원 내용: 지원 내용 예시 문구입니다. (mock 데이터)",
  ].join("\n");

const candidate = (
  partial: Pick<PolicyCandidate, "policy_id" | "title" | "region_text" | "scope" | "summary"> &
    Partial<PolicyCandidate>,
): PolicyCandidate => ({
  score: 1.2,
  distance: 0.3,
  metadata: {},
  reasons: ["벡터 유사도 0.700", "검색 범위 시군구"], // 실제 형식(개발용 문구, 화면에 표시하지 않음)
  ...partial,
});

const DETAIL_TEXT = (title: string): PolicyDetail => ({
  policy_id: "",
  title,
  region_text: "",
  sections: {
    overview: [`${title} 개요입니다. (mock 데이터)`],
    target_criteria: ["거주 지역 청년 (mock 데이터)\n연령 기준: 19세 이상 39세 이하 (mock 데이터)"],
    benefit: ["지원 내용 예시 문구입니다. (mock 데이터)"],
    application: ["온라인 또는 방문 신청 (mock 데이터)"],
    documents: [
      "신청서 1부 (mock 데이터)\nwlfareInfoReldNm: 신청서 양식\nhttps://example.com/download/form.hwp",
    ],
    contact_source: ["문의처: 000-0000-0000 (mock 데이터)\nhttps://example.com/policy"],
  },
});

export const handlers = [
  http.get("/api/regions", async () => {
    await delay(300);
    return HttpResponse.json(REGIONS);
  }),

  http.post("/api/policies/search", async ({ request }) => {
    const body = (await request.json()) as SearchRequest;
    await delay(700);
    if (body.question.includes("에러")) {
      return apiError(429, "LLM_RATE_LIMITED", "mock rate limit");
    }
    if (body.question.includes("키없음")) return apiError(401, "API_KEY_REQUIRED", "mock api key required");
    if (body.question.includes("키오류")) return apiError(401, "INVALID_API_KEY", "mock invalid api key");
    const analysis = {
      route: "situation_search" as const,
      intents: ["policy_search" as const],
      search_query: `청년 ${body.question}`.slice(0, 60),
    };
    if (body.question.includes("없음")) {
      const empty: SearchResponse = { analysis, local_policies: [], national_policies: [] };
      return HttpResponse.json(empty);
    }
    const regionText = [body.region.level1, body.region.level2].filter(Boolean).join(" ");
    if (body.question.includes("재판정")) {
      // 서버가 LLM으로 관련도를 판정한 응답: 거리가 가까워도 무관 판정이면 접히고, 거리가 멀어도 관련 판정이면 보인다
      const judged: SearchResponse = {
        analysis,
        relevance_checked: true,
        low_relevance_ids: ["local:MOCK0201"],
        local_policies: [
          candidate({ policy_id: "local:MOCK0202", title: "[예시] 거리는 멀지만 관련 있는 정책", region_text: regionText, scope: "광역", distance: 0.54, summary: summaryText("[예시] 거리는 멀지만 관련 있는 정책", regionText, "LLM이 관련 있다고 판정한 후보입니다. (mock 데이터)") }),
          candidate({ policy_id: "local:MOCK0201", title: "[예시] 거리는 가깝지만 무관한 정책", region_text: regionText, scope: "시군구", distance: 0.2, summary: summaryText("[예시] 거리는 가깝지만 무관한 정책", regionText, "LLM이 무관하다고 판정한 후보입니다. (mock 데이터)") }),
        ],
        national_policies: [],
      };
      return HttpResponse.json(judged);
    }
    if (body.question.includes("더보기")) {
      // 관련 판정 후보가 3개를 넘는 응답: 그룹마다 3개씩 쪽으로 넘겨 보는지 확인한다(우선순위 순서 = 배열 순서)
      const many = (prefix: string, count: number, scope: PolicyCandidate["scope"], region: string, agency: string) =>
        Array.from({ length: count }, (_, i) => {
          const title = `[예시] ${prefix} 정책 ${i + 1}순위`;
          return candidate({
            policy_id: `${prefix === "지역" ? "local" : "national"}:MOCKPAGE${i + 1}`,
            title,
            region_text: region,
            scope,
            distance: 0.2 + i * 0.02,
            summary: summaryText(title, agency, `${i + 1}번째로 관련도가 높은 후보입니다. (mock 데이터)`),
          });
        });
      const paged: SearchResponse = {
        analysis,
        relevance_checked: true,
        low_relevance_ids: [],
        local_policies: many("지역", 8, "시군구", regionText, regionText),
        national_policies: many("중앙", 5, "중앙부처", "", "보건복지부"),
      };
      return HttpResponse.json(paged);
    }
    if (body.question.includes("관련낮음")) {
      // 관련도가 낮은(거리 0.50 초과) 후보가 접히는지 확인하는 케이스
      const low: SearchResponse = {
        analysis,
        local_policies: [
          candidate({ policy_id: "local:MOCK0101", title: "[예시] 거리 가까운 지역 정책", region_text: regionText, scope: "시군구", distance: 0.31, summary: summaryText("[예시] 거리 가까운 지역 정책", regionText, "관련도가 높은 후보입니다. (mock 데이터)") }),
          candidate({ policy_id: "local:MOCK0102", title: "[예시] 거리 먼 지역 정책", region_text: regionText, scope: "광역", distance: 0.53, summary: summaryText("[예시] 거리 먼 지역 정책", regionText, "관련도가 낮은 후보입니다. (mock 데이터)") }),
        ],
        national_policies: [
          candidate({ policy_id: "national:MOCK0103", title: "[예시] 거리 먼 중앙부처 정책", region_text: "", scope: "중앙부처", distance: 0.54, summary: summaryText("[예시] 거리 먼 중앙부처 정책", "보건복지부", "관련도가 낮은 후보입니다. (mock 데이터)") }),
        ],
      };
      return HttpResponse.json(low);
    }
    const result: SearchResponse = {
      analysis,
      local_policies: [
        candidate({
          policy_id: "local:MOCK0001",
          title: "[예시] 청년 면접준비 지원사업",
          region_text: regionText,
          scope: body.region.level2 ? "시군구" : "시도",
          summary: summaryText("[예시] 청년 면접준비 지원사업", regionText, "면접 준비 비용을 지원하는 정책입니다. 예시 문구를 길게 이어 붙여 카드에서 줄여 보이는지 확인합니다. 예시 문구를 길게 이어 붙여 카드에서 줄여 보이는지 확인합니다. 예시 문구를 길게 이어 붙여 카드에서 줄여 보이는지 확인합니다. (mock 데이터)"),
        }),
        candidate({
          policy_id: "local:MOCK0002",
          title: "[예시] 청년 월세 한시 특별지원",
          region_text: body.region.level1,
          scope: "광역",
          summary: summaryText("[예시] 청년 월세 한시 특별지원", body.region.level1, "월세 일부를 지원하는 정책입니다. (mock 데이터)"),
        }),
      ],
      national_policies: [
        candidate({
          policy_id: "national:MOCK0003",
          title: "[예시] 청년 주거급여 분리지급",
          region_text: "",
          scope: "중앙부처",
          summary: summaryText("[예시] 청년 주거급여 분리지급", "보건복지부", "부모와 떨어져 사는 청년의 주거급여입니다. (mock 데이터)"),
        }),
      ],
    };
    return HttpResponse.json(result);
  }),

  http.get("/api/policies/:policyId", async ({ params }) => {
    await delay(300);
    const policyId = decodeURIComponent(String(params.policyId));
    if (!policyId.includes("MOCK")) {
      return apiError(404, "POLICY_NOT_FOUND", "mock not found");
    }
    const detail = DETAIL_TEXT("선택한 정책");
    return HttpResponse.json({ ...detail, policy_id: policyId });
  }),

  http.post("/api/policies/:policyId/ask", async ({ request, params }) => {
    const body = (await request.json()) as AskRequest;
    const policyId = decodeURIComponent(String(params.policyId));
    await delay(900);
    if (body.question.includes("에러")) {
      return apiError(429, "LLM_RATE_LIMITED", "mock rate limit");
    }
    if (body.question.includes("날씨")) {
      const notCurrent: AskResponse = {
        route: "situation_search",
        intents: ["policy_search"],
        answer: null,
      };
      return HttpResponse.json(notCurrent);
    }
    const grounded = !body.question.includes("근거없음");
    const result: AskResponse = {
      route: "current_policy_question",
      intents: ["eligibility", "application"],
      answer: {
        answer: grounded
          ? "**지원 대상**은 거주 지역의 19~39세 청년입니다.\n\n**신청 방법**은 온라인 또는 방문 신청입니다. (mock 데이터)"
          : "제공된 공식 자료에서는 확인되지 않습니다. (mock 데이터)",
        policy_id: policyId,
        used_sections: grounded ? ["target_criteria", "application"] : [],
        evidence: grounded ? ["연령 기준: 19세 이상 39세 이하", "온라인 또는 방문 신청"] : [],
        resources: [
          { label: "신청서 양식", resource_type: "attachment", url: "https://example.com/download/form.hwp" },
          { label: "관련 웹사이트", resource_type: "website", url: "https://example.com/policy" },
        ],
        grounded,
      },
    };
    return HttpResponse.json(result);
  }),
];
