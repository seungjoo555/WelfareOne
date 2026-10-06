import { useEffect, useRef } from "react";
import type { Message } from "../../types/chat";
import { MessageItem, type MessageActions } from "./MessageItem";

interface Props {
  messages: Message[];
  actions: MessageActions;
}

export function MessageList({ messages, actions }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  // 사용자가 위로 올려 읽는 중이면 새 메시지가 와도 강제로 내리지 않는다.
  const onScroll = () => {
    const el = ref.current;
    if (!el) return;
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  };

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (messages[messages.length - 1]?.type === "user_text") stickToBottom.current = true;
    if (stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  return (
    <div
      className="message-list"
      ref={ref}
      onScroll={onScroll}
      role="log"
      aria-live="polite"
      aria-relevant="additions"
    >
      {messages.map((message) => (
        <MessageItem key={message.id} message={message} actions={actions} />
      ))}
    </div>
  );
}
