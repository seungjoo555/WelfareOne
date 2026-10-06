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
