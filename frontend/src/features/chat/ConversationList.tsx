import { useEffect, useRef, useState } from "react";
import {
  HISTORY_EMPTY,
  HISTORY_PRIVACY,
  HISTORY_RENAME_HINT,
  HISTORY_RENAME_INPUT_LABEL,
  HISTORY_SAVE_ERRORS,
  historyRenameLabel,
} from "../../constants/text";
import { CUSTOM_TITLE_MAX_LENGTH } from "../../storage/history";
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
  const { items, activeId, saveError, select, rename, remove, clearAll } = history;
  const groups = groupByDate(items, Date.now());
  // 제목 수정 중인 상담과 입력값. Enter/포커스 이탈 = 저장, Esc = 취소.
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const finished = useRef(false); // Enter/Esc 직후 이어지는 blur로 두 번 저장되는 것을 막는다

  useEffect(() => {
    if (editingId) {
      finished.current = false;
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editingId]);

  const startEdit = (id: string, title: string) => {
    setEditingId(id);
    setDraft(title);
  };
  const commit = () => {
    if (finished.current || editingId === null) return;
    finished.current = true;
    const target = items.find((item) => item.id === editingId);
    if (target && draft.trim() !== target.title) rename(editingId, draft);
    setEditingId(null);
  };
  const cancel = () => {
    finished.current = true;
    setEditingId(null);
  };

  return (
    <nav className="history" aria-label="상담 기록">
      {items.length === 0 && <p className="muted history-empty">{HISTORY_EMPTY}</p>}
      {groups.map((group) => (
        <section key={group.label}>
          <h2 className="history-heading">{group.label}</h2>
          <ul className="history-list">
            {group.items.map((item) => {
              const active = item.id === activeId;
              if (item.id === editingId) {
                return (
                  <li key={item.id} className={`history-item editing${active ? " active" : ""}`}>
                    <input
                      ref={inputRef}
                      className="history-rename-input"
                      value={draft}
                      maxLength={CUSTOM_TITLE_MAX_LENGTH}
                      aria-label={HISTORY_RENAME_INPUT_LABEL}
                      placeholder={HISTORY_RENAME_HINT}
                      onChange={(event) => setDraft(event.target.value)}
                      onBlur={commit}
                      onKeyDown={(event) => {
                        if (event.nativeEvent.isComposing) return; // 한글 조합 중 Enter는 글자 확정이므로 저장하지 않는다
                        if (event.key === "Enter") {
                          event.preventDefault();
                          commit();
                        } else if (event.key === "Escape") {
                          event.preventDefault();
                          cancel();
                        }
                      }}
                    />
                  </li>
                );
              }
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
                    className="history-edit"
                    aria-label={historyRenameLabel(item.title)}
                    title="제목 수정"
                    onClick={() => startEdit(item.id, item.title)}
                  >
                    ✎
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
