# Media Portal WebUI (Frontend)

Vite + Vue 3 + TypeScript + Pinia + vue-router + vue-i18n，**由 [Bun](https://bun.sh/) 驱动**。

## 目录

- `src/main.ts` — 入口，注册 Pinia / router / i18n
- `src/api/` — 后端接口封装（与 `webui/server.py` 的 `/api/*`、`/files/*`、`/thumb/*` 对齐）
- `src/stores/` — Pinia 状态
- `src/router/` — 路由及鉴权守卫
- `src/i18n/` — vue-i18n 及 `zh-CN` / `en-US` / `ja-JP` 翻译
- `src/components/` — 业务组件
- `src/views/` — 路由页面
- `src/layouts/` — 布局
- `src/styles/` — 全局样式（沿用旧版 token / 主题）

## 前置

- **Bun ≥ 1.1**（同时承担包管理器 / runtime / 脚本执行器三重角色）

安装 Bun：

```bash
# macOS / Linux / WSL
curl -fsSL https://bun.sh/install | bash

# Windows (PowerShell)
powershell -c "irm bun.sh/install.ps1 | iex"

# 国内若访问受阻，可用官方镜像：
# $env:BUN_INSTALL_BASEURL="https://bun.sh/download"
```

验证：

```bash
bun --version
```

> 本项目**仅**使用 Bun。不要混用 npm / pnpm / yarn，以免产生多余 lock 文件。`.gitignore` 已屏蔽其他包管理器的锁文件。

## 开发

```bash
# 1) 启动插件（FastAPI WebUI，默认监听 7003 端口）
#    详见 scripts/debug_webui.py

# 2) 启动前端 dev server（HMR）
cd webui/frontend
bun install
bun run dev
# 浏览器访问 http://localhost:5173
```

`vite.config.ts` 中的 `server.proxy` 已将 `/api`、`/files`、`/thumb` 代理到 `http://127.0.0.1:7003`。
如后端端口不同，可通过环境变量覆盖：

```bash
# 临时覆盖（当前会话生效）
$env:VITE_DEV_API_TARGET="http://127.0.0.1:11451"
bun run dev
```

## 构建

```bash
bun run build
```

构建产物直接写入 `webui/static/`（仓库内提交，**插件用户无需 Bun / Node 环境**）。
执行前会清空 `webui/static/` 的旧内容，请确保没有本地未提交的手改。

构建会先跑 `vue-tsc --noEmit` 做类型检查，失败直接终止。

## 国际化

- 默认语言 `zh-CN`，回退 `zh-CN`
- `en-US` / `ja-JP` 按路由懒加载
- 运行时调用 `setLocale("en-US")` 切换，语言会写入 `localStorage`（key: `media_portal_locale`）
- 新增翻译：在 `src/i18n/locales/*.json` 按键补齐即可

## 常用脚本

```bash
bun run typecheck   # vue-tsc
bun run lint        # eslint
bun run format      # prettier
bun run preview     # 预览产物
```

Bun 小技巧：

```bash
bun add <pkg>              # 等价 pnpm add
bun add -d <pkg>           # 等价 pnpm add -D
bun remove <pkg>           # 卸载
bun outdated               # 列出可升级包
bun install --frozen-lockfile   # CI 专用
bunx <binary>              # 等价 npx / pnpm dlx
```

## 发布流程

1. 修改前端源码
2. `bun run build` 生成 `webui/static/`
3. `git add webui/frontend webui/static && git commit`
