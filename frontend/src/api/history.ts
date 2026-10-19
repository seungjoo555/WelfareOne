import { request } from "./client";
import { getAuthToken } from "./auth";

export interface ServerSessionSummary {
  session_id: string;
  title: string;
  region_level1: string;
  region_level2: string;
  age: number | null;
  created_at: string;
  updated_at: string;
}

export interface ServerChatMessage {
  message_id: string;
  session_id: string;
  sender_type: "user" | "assistant";
  content: string;
  route?: string;
  intents_json?: string;
  selected_policy_id?: string;
  candidates_json?: string;
  evidence_json?: string;
  resources_json?: string;
  created_at: string;
}

export interface ServerSessionDetail {
  session: ServerSessionSummary;
  messages: ServerChatMessage[];
}

export async function fetchServerSessions(): Promise<ServerSessionSummary[]> {
  const token = getAuthToken();
  if (!token) return [];
  return await request<ServerSessionSummary[]>("/history/sessions", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function createServerSession(data: {
  region_level1: string;
  region_level2: string;
  age: number | null;
  title?: string;
}): Promise<ServerSessionSummary> {
  const token = getAuthToken();
  return await request<ServerSessionSummary>("/history/sessions", {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: JSON.stringify(data),
  });
}

export async function fetchServerSessionDetail(sessionId: string): Promise<ServerSessionDetail> {
  const token = getAuthToken();
  return await request<ServerSessionDetail>(`/history/sessions/${sessionId}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}

export async function deleteServerSession(sessionId: string): Promise<void> {
  const token = getAuthToken();
  await request(`/history/sessions/${sessionId}`, {
    method: "DELETE",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}

