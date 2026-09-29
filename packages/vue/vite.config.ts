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
        // xterm and its addons (and the xterm.css subpath) come from the app's node_modules
        /^@xterm\//,
        "reconnecting-websocket",
      ],
    },
  },
});
