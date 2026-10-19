import type {
  AskRequest,
  AskResponse,
  PolicyDetail,
  SearchRequest,
  SearchResponse,
} from "../types/contract";
import { request } from "./client";

// policy_id에 ":"가 들어 있으므로(local:WLF...) 경로에 넣을 때 인코딩한다.
const idPath = (policyId: string) => encodeURIComponent(policyId);

export const searchPolicies = (body: SearchRequest) =>
  request<SearchResponse>(
    "/policies/search",
    { method: "POST", body: JSON.stringify(body) },
    { apiKey: true },
  );

export const getPolicy = (policyId: string) =>
  request<PolicyDetail>(`/policies/${idPath(policyId)}`);

export const askPolicy = (policyId: string, body: AskRequest) =>
  request<AskResponse>(
    `/policies/${idPath(policyId)}/ask`,
    { method: "POST", body: JSON.stringify(body) },
    { apiKey: true },
  );

// 로그인 상태에서는 기록 서버(Spring)를 거쳐 FastAPI를 부른다: 질문·답변이 상담 기록(Oracle)에 저장되고,
// 이 요청에 키가 없으면 서버에 저장된 Gemini 키가 쓰인다. 오류 코드는 Spring이 FastAPI 것을 그대로 전달한다.
const bearer = (token: string) => ({ Authorization: `Bearer ${token}` });

export const searchPoliciesInSession = (sessionId: string, body: SearchRequest, token: string) =>
  request<SearchResponse>(
    `/ai/sessions/${encodeURIComponent(sessionId)}/search`,
    { method: "POST", body: JSON.stringify(body), headers: bearer(token) },
    { apiKey: true },
  );

export const askPolicyInSession = (sessionId: string, policyId: string, body: AskRequest, token: string) =>
  request<AskResponse>(
    `/ai/sessions/${encodeURIComponent(sessionId)}/policies/${idPath(policyId)}/ask`,
    { method: "POST", body: JSON.stringify(body), headers: bearer(token) },
    { apiKey: true },
  );
