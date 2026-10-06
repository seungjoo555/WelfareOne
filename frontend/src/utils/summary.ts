// 후보의 summary는 DB의 candidate_summary 문서 전체다(정책명·지역·생애주기·개요·대상·지원 내용이
// 여러 줄로 이어진 최대 약 450자). 카드에는 "개요:" 줄만 짧게 보여준다.
// 형식이 달라도 깨지지 않도록 개요 줄이 없으면 메타 줄을 뺀 첫 줄을 쓴다.
const META_PREFIXES = ["정책명:", "지역·소관:", "생애주기:"];

export function pickSummary(raw: string, maxLength = 140): string {
  const lines = raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const overview = lines.find((line) => line.startsWith("개요:"));
  const body =
    overview?.replace(/^개요:\s*/, "") ??
    lines.find((line) => !META_PREFIXES.some((prefix) => line.startsWith(prefix))) ??
    raw.trim();
  return body.length > maxLength ? `${body.slice(0, maxLength).trimEnd()}…` : body;
}
