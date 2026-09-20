# apps/ — Frontend workspace root

This directory is the root of the npm workspaces declared in the repository-root `package.json` (`"workspaces": ["apps/*"]`). The application here consumes the backend HTTP surface (the gateway serves `/api` and `/health` on port 8000, proxied by the Vite dev server — see `apps/web/vite.config.ts`). Neither workspace is published or consumed as an npm dependency by the other roots.

## Apps

- `web/` — React 19 + TypeScript + Vite main application: the entire browser UI. See [web/README.md](web/README.md).
- `config/` — workspace package `config` (private, not published). Its only config file is `tsconfig.base.json`, the strict shared TypeScript base (ES2022 target, bundler module resolution, `strict`, `noUnusedLocals`/`noUnusedParameters`) that `apps/web/tsconfig.json` consumes via `"extends": "../config/tsconfig.base.json"`.

## Notes

- `apps/web/eslint.config.js` is self-contained and does not read from `apps/config`; `config/package.json` describes itself as shared TypeScript/ESLint/Tailwind config, but no ESLint or Tailwind config files are present in the package.
- Repository-root npm scripts proxy into `web` with the `-w web` flag (for example `dev:web`, `build:web`, `test:web`).
