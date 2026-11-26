/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const useMocks = (env.VITE_USE_MOCKS ?? (mode === "development" ? "true" : "false")) === "true";
  return {
    plugins: [react()],
    define: { "import.meta.env.VITE_USE_MOCKS": JSON.stringify(String(useMocks)) },
    server: {
      proxy: useMocks
        ? undefined
        : { "/api": { target: env.VITE_API_URL || "http://localhost:8000", changeOrigin: true } },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
    },
  };
});
