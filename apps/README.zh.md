# apps/ — 前端工作区根

> 语言：简体中文 | [English](README.md)

本目录是仓库根 `package.json` 所声明的 npm workspaces 的根（`"workspaces": ["apps/*"]`）。这里的应用消费后端 HTTP 面（gateway 在端口 8000 上提供 `/api` 与 `/health`，经 Vite dev server 代理 —— 见 `apps/web/vite.config.ts`）。两个 workspace 均不发布，也不作为 npm 依赖被其他根消费。

## 应用

- `web/` — React 19 + TypeScript + Vite 主应用：完整的浏览器 UI。见 [web/README.zh.md](web/README.zh.md)。
- `config/` — workspace 包 `config`（私有，不发布）。其唯一配置文件为 `tsconfig.base.json`，即严格的共享 TypeScript 基础配置（ES2022 target、bundler 模块解析、`strict`、`noUnusedLocals`/`noUnusedParameters`），由 `apps/web/tsconfig.json` 经 `"extends": "../config/tsconfig.base.json"` 消费。

## 备注

- `apps/web/eslint.config.js` 自包含，不读取 `apps/config`；`config/package.json` 将自身描述为共享 TypeScript/ESLint/Tailwind 配置，但该包内并不存在任何 ESLint 或 Tailwind 配置文件。
- 仓库根 npm 脚本经 `-w web` 标志代理进 `web`（例如 `dev:web`、`build:web`、`test:web`）。
