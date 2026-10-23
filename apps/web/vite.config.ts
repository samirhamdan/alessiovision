import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": process.env.ALESSIO_API_URL ?? "http://localhost:8000",
      "/agent": process.env.ALESSIO_API_URL ?? "http://localhost:8000",
    },
  },
});
