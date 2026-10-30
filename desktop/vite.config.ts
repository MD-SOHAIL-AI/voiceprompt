import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    watch: { ignored: ["**/src-tauri/**"] },
  },
  // Rust output can contain generated HTML; it is not a frontend entry point.
  optimizeDeps: { entries: ["index.html"] },
  envPrefix: ["VITE_", "TAURI_"],
  build: {
    target: ["es2021", "chrome100"],
    minify: !process.env.TAURI_DEBUG,
    sourcemap: !!process.env.TAURI_DEBUG,
  },
});
