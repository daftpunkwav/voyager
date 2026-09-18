import { defineConfig } from 'vite';
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

export default defineConfig({
  define: {
    __BRAND__: JSON.stringify(brand),
  },
  plugins: [
    {
      name: 'inject-brand',
      transformIndexHtml(html) {
        return html
          .replaceAll('%PRODUCT_NAME%', brand.productName)
          .replaceAll('%PRODUCT_TAGLINE%', brand.productTagline)
          .replaceAll('%UI_STORE_KEY%', brand.storage.uiStore)
          .replaceAll('%UI_STORE_LEGACY_KEY%', brand.storage.legacy.uiStore);
      },
    },
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
    // §4.2 dev injects the full CSP (incl. frame-ancestors, which meta does not support);
    // production injects it via gateway / reverse proxy response headers.
    headers: {
      'Content-Security-Policy': [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:",
        "worker-src 'self' blob:",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com data:",
        "img-src 'self' data: https:",
        "connect-src 'self' ws: wss: http://127.0.0.1:8000",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
      ].join('; '),
    },
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
  },
});
