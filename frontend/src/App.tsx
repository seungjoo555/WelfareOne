import { useReducer } from "react";
import { ChatPage } from "./features/chat/ChatPage";
import { StartForm } from "./features/start/StartForm";
import { conversationReducer, initialState } from "./state/conversation";

export default function App() {
  const [state, dispatch] = useReducer(conversationReducer, initialState);

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
  return <ChatPage state={state} dispatch={dispatch} />;
}
