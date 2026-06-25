import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:5002",
      "/media": "http://127.0.0.1:5002",
      "/file": "http://127.0.0.1:5002",
      "/category": "http://127.0.0.1:5002",
      "/login": "http://127.0.0.1:5002",
      "/logout": "http://127.0.0.1:5002",
      "/register": "http://127.0.0.1:5002",
    },
  },
});
