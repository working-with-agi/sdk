import { defineConfig } from "vite";
import angular from "@analogjs/vite-plugin-angular";

export default defineConfig({
  plugins: [angular()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8601",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8601",
        ws: true,
      },
    },
  },
});
