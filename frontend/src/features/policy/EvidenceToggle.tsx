interface Props {
  evidence: string[];
}

export function EvidenceToggle({ evidence }: Props) {
  if (evidence.length === 0) return null;
  return (
    <details className="evidence">
      <summary>근거 원문 보기 ({evidence.length})</summary>
      <ul>
        {evidence.map((text, index) => (
          <li key={index}>{text}</li>
        ))}
      </ul>
    </details>
  );
}
