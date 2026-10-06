import { HISTORY_EMPTY, HISTORY_PRIVACY, HISTORY_SAVE_ERRORS } from "../../constants/text";
import type { ConversationSummary } from "../../storage/history";
import type { ConversationHistory } from "../../state/useConversationHistory";

const DAY_MS = 24 * 60 * 60 * 1000;

const startOfDay = (time: number): number => {
  const date = new Date(time);
  date.setHours(0, 0, 0, 0);
  return date.getTime();
};

// 날짜 구간 이름(오늘/어제/최근 7일/이전). 하루 단위 차이는 자정 기준으로 센다.
export function groupLabel(updatedAt: number, now: number): string {
  const days = Math.round((startOfDay(now) - startOfDay(updatedAt)) / DAY_MS);
  if (days <= 0) return "오늘";
  if (days === 1) return "어제";
  if (days <= 7) return "최근 7일";
  return "이전";
}

function groupByDate(items: ConversationSummary[], now: number) {
  const groups: { label: string; items: ConversationSummary[] }[] = [];
  for (const item of items) {
    const label = groupLabel(item.updated_at, now);
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.items.push(item);
    else groups.push({ label, items: [item] });
  }
  return groups;
}

interface Props {
  history: ConversationHistory;
  disabled: boolean; // 응답을 기다리는 중에는 전환·삭제를 막는다
  onSelected?: () => void; // 모바일에서 사이드바를 닫는 용도
}

export function ConversationList({ history, disabled, onSelected }: Props) {
  const { items, activeId, saveError, select, remove, clearAll } = history;
  const groups = groupByDate(items, Date.now());

  return (
    <nav className="history" aria-label="상담 기록">
      {items.length === 0 && <p className="muted history-empty">{HISTORY_EMPTY}</p>}
      {groups.map((group) => (
        <section key={group.label}>
          <h2 className="history-heading">{group.label}</h2>
          <ul className="history-list">
            {group.items.map((item) => {
              const active = item.id === activeId;
              return (
                <li key={item.id} className={`history-item${active ? " active" : ""}`}>
                  <button
                    type="button"
                    className="history-open"
                    disabled={disabled}
                    aria-current={active ? "true" : undefined}
                    title={item.title}
                    onClick={() => {
                      select(item.id);
                      onSelected?.();
                    }}
                  >
                    <span className="history-title">{item.title}</span>
                    <span className="history-meta">
                      {item.region_text}
                      {item.age === null ? "" : ` · ${item.age}세`}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="history-delete"
                    disabled={disabled}
                    aria-label={`${item.title} 상담 기록 삭제`}
                    onClick={() => remove(item.id)}
                  >
                    ✕
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
      {saveError && <p className="warning" role="alert">{HISTORY_SAVE_ERRORS[saveError]}</p>}
      <div className="history-footer">
        <p className="muted">{HISTORY_PRIVACY}</p>
        {items.length > 0 && (
          <button type="button" className="link-btn" disabled={disabled} onClick={clearAll}>
            기록 모두 삭제
          </button>
        )}
      </div>
    </nav>
  );
}
