import type { PolicyResource } from "../../types/contract";

// 원문에서 추출한 URL이라도 http(s)가 아니면 링크로 만들지 않는다(javascript: 등 차단).
const isSafeUrl = (url: string): boolean => /^https?:\/\//i.test(url);

export function ResourceButtons({ resources }: { resources: PolicyResource[] }) {
  const safe = resources.filter((resource) => isSafeUrl(resource.url));
  if (safe.length === 0) return null;
  return (
    <div className="resources">
      {safe.map((resource) => (
        <a
          key={resource.url}
          className="btn small"
          href={resource.url}
          target="_blank"
          rel="noopener noreferrer"
        >
          {resource.resource_type === "attachment" ? "다운로드" : "바로가기"} · {resource.label}
        </a>
      ))}
    </div>
  );
}
