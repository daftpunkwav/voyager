import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { viteStaticCopy } from 'vite-plugin-static-copy';
import path from 'path';
import { readFileSync } from 'fs';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
const reactDir = path.dirname(require.resolve('react/package.json'));
const reactDomDir = path.dirname(require.resolve('react-dom/package.json'));
// cmaps and standard fonts required by pdf.js for CJK PDFs (the reader references them under /pdfjs/)
// the glob library does not understand Windows backslashes: normalize to posix separators
const pdfjsDir = path.dirname(require.resolve('pdfjs-dist/package.json')).split(path.sep).join('/');

const BACKEND = process.env.VITE_API_TARGET || 'http://127.0.0.1:8000';
const brand = JSON.parse(readFileSync(path.resolve(__dirname, '../../brand.json'), 'utf8')) as {
  productName: string;
  productTagline: string;
  storage: { uiStore: string; legacy: { uiStore: string } };
};

// The shipped policy (apps/web/index.html) allows no inline script and no
// eval in the page. The dev server relaxes script-src for the React Fast
// Refresh preamble it injects into <head> (an inline <script type="module">).
const CSP_SCRIPT_SRC = "script-src 'self';";
const CSP_SCRIPT_SRC_DEV = "script-src 'self' 'unsafe-inline';";

// The runner worker is served as its own script, so it takes the policy of
// its own response rather than the page policy. That policy closes what the
// guards inside the worker cannot stop: a script load that redirects to
// another origin, and a nested worker.
const RUNNER_WORKER_PATH = '/code-runner-worker.js';

const WORKER_CSP = [
  "default-src 'none'",
  "script-src 'self' blob: 'unsafe-eval'",
  "connect-src 'self'",
  "worker-src 'none'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
].join('; ');

// §4.2 dev injects the full CSP (incl. frame-ancestors, which meta does not
// support); production injects it via gateway / reverse proxy response
// headers.
const DEV_PAGE_CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:",
  "worker-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "font-src 'self' data:",
  "img-src 'self' data: https:",
  "connect-src 'self' ws: wss: http://127.0.0.1:8000",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join('; ');

/**
 * Send the policy of every dev and preview response.
 *
 * The policy is set here rather than in `server.headers` because that option
 * applies the page policy to every file it serves, which would overwrite the
 * worker policy of the runner worker.
 */
function responsePolicies(): Plugin {
  const middleware = (
    req: { url?: string },
    res: { setHeader: (name: string, value: string) => void },
    next: () => void
  ): void => {
    const path = (req.url ?? '').split('?')[0];
    res.setHeader(
      'Content-Security-Policy',
      path === RUNNER_WORKER_PATH ? WORKER_CSP : DEV_PAGE_CSP
    );
    next();
  };
  return {
    name: 'response-policies',
    configureServer(server) {
      server.middlewares.use(middleware);
    },
    configurePreviewServer(server) {
      server.middlewares.use(middleware);
    },
  };
}

export default defineConfig({
  define: {
    __BRAND__: JSON.stringify(brand),
  },
  plugins: [
    {
      name: 'inject-brand',
      transformIndexHtml(html, ctx) {
        const branded = html
          .replaceAll('%PRODUCT_NAME%', brand.productName)
          .replaceAll('%PRODUCT_TAGLINE%', brand.productTagline)
          .replaceAll('%UI_STORE_KEY%', brand.storage.uiStore)
          .replaceAll('%UI_STORE_LEGACY_KEY%', brand.storage.legacy.uiStore);
        // ctx.server is set while serving; the built output keeps the strict policy.
        return ctx.server ? branded.replace(CSP_SCRIPT_SRC, CSP_SCRIPT_SRC_DEV) : branded;
      },
    },
    responsePolicies(),
    react(),
    viteStaticCopy({
      targets: [
        { src: `${pdfjsDir}/cmaps`, dest: 'pdfjs' },
        { src: `${pdfjsDir}/standard_fonts`, dest: 'pdfjs' },
      ],
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      // ensure the whole app uses a single React copy (avoid duplicate instances from monorepo hoisting)
      react: reactDir,
      'react-dom': reactDomDir,
    },
    dedupe: ['react', 'react-dom'],
  },
  server: {
    host: '127.0.0.1',
    port: Number(process.env.VITE_PORT) || 5173,
    strictPort: true,
    // The response policy comes from the response-policies plugin: the runner
    // worker carries the policy of its own response, not the page policy.
    proxy: {
      // /health is not under the /api prefix; proxy it separately (the service badge bar and the status page depend on it)
      '/api': { target: BACKEND, changeOrigin: true },
      '/health': { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // split heavy libs into their own chunks; do not split React, to avoid dual instances.
        manualChunks(id) {
          if (!id.includes('node_modules')) return;
          if (/node_modules[/\\](react|react-dom|scheduler)[/\\]/.test(id)) return;
          if (/node_modules[/\\](three|@react-three)[/\\]/.test(id)) return 'vendor-three';
          if (/node_modules[/\\]mermaid[/\\]/.test(id)) return 'vendor-mermaid';
          if (/node_modules[/\\]pdfjs-dist[/\\]/.test(id)) return 'vendor-pdfjs';
          if (/node_modules[/\\](@codemirror|codemirror|@lezer)[/\\]/.test(id)) {
            return 'vendor-codemirror';
          }
          if (/node_modules[/\\]d3/.test(id)) return 'vendor-d3';
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './tests/setup.ts',
    include: ['tests/unit/**/*.test.{ts,tsx}'],
    // Ratchet floors, not aspirations: pinned at the measured baseline
    // (2026-10-03) so any regression fails while deliberate coverage work
    // raises them. Mirrors the Python side's --cov-fail-under philosophy.
    coverage: {
      thresholds: {
        statements: 67,
        branches: 59,
        functions: 63,
        lines: 68,
      },
    },
    // Pin NODE_ENV before any module loads: react's CJS entry picks its build
    // from this variable at import time, and a shell exporting production
    // would resolve react.production (which has no act()) — setup.ts cannot
    // fix that because its own imports hoist ahead of any assignment.
    env: { NODE_ENV: 'development' },
  },
});
