import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { resolve } from "path";

export default defineConfig({
  plugins: [vue()],
  build: {
    lib: {
      entry: resolve(__dirname, "src/index.ts"),
      formats: ["es"],
      fileName: "index",
    },
    rollupOptions: {
      external: [
        "vue",
        "pinia",
        "@work-with-ai/sdk",
        "@xterm/xterm",
        "@xterm/addon-fit",
        "@xterm/addon-web-links",
        "@xterm/addon-webgl",
        "@xterm/addon-unicode11",
        "reconnecting-websocket",
      ],
    },
  },
});
