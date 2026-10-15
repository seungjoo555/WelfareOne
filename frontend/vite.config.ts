import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite 개발 프록시 설정
// /api/auth, /api/users, /api/history, /api/ai -> Spring Boot (localhost:8080)
// 그 외 /api/* -> FastAPI (localhost:8000)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api/auth": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
      "/api/users": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
      "/api/history": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
      "/api/ai": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
