import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  envDir: "..",
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    allowedHosts: ["081v1l3h-5173.inc1.devtunnels.ms"]
  },
  build: {
    chunkSizeWarningLimit: 1000
  }
});
