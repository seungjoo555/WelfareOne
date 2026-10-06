// 개발 서버(npm run dev)에서는 mock이 기본값이다. 실제 FastAPI를 쓰려면 .env.local에
// VITE_USE_MOCK=false 를 넣는다. 배포 빌드(npm run build)에서는 기본적으로 mock을 쓰지 않는다.
export const USE_MOCK: boolean = import.meta.env.DEV
  ? import.meta.env.VITE_USE_MOCK !== "false"
  : import.meta.env.VITE_USE_MOCK === "true";
