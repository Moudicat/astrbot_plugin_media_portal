import { fileURLToPath, URL } from "node:url";
import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";
import VueI18nPlugin from "@intlify/unplugin-vue-i18n/vite";

export default defineConfig(({ mode, command }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // 开发期把 /api、/files、/thumb 代理到实际运行的 Media Portal WebUI FastAPI。
  // 默认端口与 scripts/debug_webui.py 保持一致；如需改端口，设置环境变量
  //   VITE_DEV_API_TARGET=http://127.0.0.1:xxxx  或在 .env.local 里声明。
  const devApiTarget = env.VITE_DEV_API_TARGET || "http://127.0.0.1:7003";

  return {
    plugins: [
      vue(),
      VueI18nPlugin({
        include: [fileURLToPath(new URL("./src/i18n/locales/**", import.meta.url))],
        strictMessage: false,
      }),
    ],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    // 生产：FastAPI 以 /static/ 前缀托管；开发：直接根路径，访问 http://localhost:5173/
    base: command === "build" ? "/static/" : "/",
    build: {
      outDir: fileURLToPath(new URL("../static", import.meta.url)),
      emptyOutDir: true,
      assetsDir: "assets",
      sourcemap: false,
      chunkSizeWarningLimit: 900,
      rollupOptions: {
        output: {
          manualChunks: {
            vue: ["vue", "vue-router", "pinia"],
            i18n: ["vue-i18n"],
            icons: ["lucide-vue-next"],
          },
        },
      },
    },
    server: {
      port: 5173,
      strictPort: false,
      proxy: {
        "/api": { target: devApiTarget, changeOrigin: false },
        "/files": { target: devApiTarget, changeOrigin: false },
        "/thumb": { target: devApiTarget, changeOrigin: false },
      },
    },
  };
});
