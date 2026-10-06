import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 개발 서버가 /api 요청을 FastAPI(localhost:8000)로 넘겨준다(프록시).
// 브라우저 입장에서는 같은 주소로 요청하는 셈이라 CORS 설정이 필요 없다.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
