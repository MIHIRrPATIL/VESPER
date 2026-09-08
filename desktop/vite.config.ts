import { defineConfig, Plugin } from "vite";
import react from "@vitejs/plugin-react";
import process from "node:process";
import fs from "node:fs";
import path from "node:path";

const host = process.env.TAURI_DEV_HOST;

function wasmStaticPlugin(): Plugin {
  return {
    name: "wasm-static-serve",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url && req.url.startsWith("/wasm/")) {
          const cleanPath = req.url.split("?")[0];
          const localPath = path.join(process.cwd(), "public", cleanPath);
          if (fs.existsSync(localPath) && fs.statSync(localPath).isFile()) {
            if (localPath.endsWith(".wasm")) {
              res.setHeader("Content-Type", "application/wasm");
            } else if (localPath.endsWith(".js")) {
              res.setHeader("Content-Type", "application/javascript");
            }
            res.end(fs.readFileSync(localPath));
            return;
          }
        }
        next();
      });
    },
  };
}

// https://vite.dev/config/
export default defineConfig(() => ({
  plugins: [react(), wasmStaticPlugin()],

  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },

  // Vite options tailored for Tauri development and only applied in `tauri dev` or `tauri build`
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      ignored: ["**/src-tauri/**"],
    },
  },
}));
