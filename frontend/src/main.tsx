import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";
import { USE_MOCK } from "./config";

async function bootstrap() {
  // mock 모드면 백엔드 없이 MSW 가짜 응답으로 동작한다(src/config.ts 참고).
  if (USE_MOCK) {
    const { worker } = await import("./mocks/browser");
    await worker.start({ onUnhandledRequest: "bypass" });
  }
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

void bootstrap();
