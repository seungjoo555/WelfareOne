import { useReducer } from "react";
import { ChatPage } from "./features/chat/ChatPage";
import { StartForm } from "./features/start/StartForm";
import { conversationReducer } from "./state/conversation";
import { loadInitialState, useConversationHistory } from "./state/useConversationHistory";

export default function App() {
  // 마지막으로 보던 상담이 저장돼 있으면 시작 화면 없이 그대로 이어서 연다.
  const [state, dispatch] = useReducer(conversationReducer, undefined, loadInitialState);
  const history = useConversationHistory(state, dispatch);

  if (state.phase === "start") {
    return (
      <StartForm
        initialRegion={state.region}
        initialAge={state.age}
        onSubmit={(region, age) => dispatch({ type: "START", region, age })}
        onCancel={state.region ? () => dispatch({ type: "CANCEL_EDIT" }) : undefined}
      />
    );
  }
  return <ChatPage state={state} dispatch={dispatch} history={history} />;
}
