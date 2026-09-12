/** @file vite-env.d.ts - Vite client types plus ambient declarations for brand injection. */

/// <reference types="vite/client" />

interface BrandStorage {
  uiStore: string;
  sessionDrawer: string;
  contextDrawer: string;
  pdfScale: string;
  githubUsername: string;
  l1Display: string;
  legacy: {
    uiStore: string;
    sessionDrawer: string;
    contextDrawer: string;
    pdfScale: string;
    githubUsername: string;
    l1Display: string;
    token: string;
    session: string;
  };
}

interface BrandConfig {
  productName: string;
  productTagline: string;
  storage: BrandStorage;
}

declare const __BRAND__: BrandConfig;
