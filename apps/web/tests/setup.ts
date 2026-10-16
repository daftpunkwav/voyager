import { expect } from 'vitest';
import { configure } from '@testing-library/react';
import * as jestDomMatchers from '@testing-library/jest-dom/matchers';

// Register the matchers through the `/matchers` entry rather than
// `@testing-library/jest-dom/vitest`. The latter starts with a bare
// `import { expect } from 'vitest'`, which Node resolves relative to
// <repo>/node_modules/@testing-library/jest-dom/dist — it only finds vitest
// while npm hoists vitest to the repo root. A dependency bump that nests
// vitest into apps/web/node_modules leaves jest-dom orphaned at the root and
// every suite dies at load with "Cannot find package 'vitest'".
// `/matchers` imports no vitest, and the `vitest` specifier below resolves
// from this file's own workspace either way.
expect.extend(jestDomMatchers);

// NODE_ENV is pinned to 'development' in vite.config.ts (test.env): it must be
// set before module resolution, or react resolves to its production build,
// which has no act(). Assigning it here would already be too late.

// CI runners share CPUs: with the default 1 s window a waitFor can starve on
// busy parallel workers (a submit's microtask chain lands after the wait and
// the assertion times out). 5 s keeps the wait meaningful in that case and
// changes nothing about local runs, which resolve in milliseconds.
configure({ asyncUtilTimeout: 5000 });

// Node >= 22 ships a global `localStorage` accessor (webstorage). Inside
// vitest's jsdom environment it shadows jsdom's own window.localStorage and,
// without --localstorage-file, resolves to undefined - which made zustand's
// persist middleware throw on every store write. Install a minimal in-memory
// Storage whenever the global is missing or non-functional; per-worker
// instances match the "fresh browser profile" semantics the tests assume.
if (
  typeof localStorage === 'undefined' ||
  (() => {
    try {
      localStorage.setItem('__probe__', '1');
      localStorage.removeItem('__probe__');
      return false;
    } catch {
      return true;
    }
  })()
) {
  class MemoryStorage implements Storage {
    private map = new Map<string, string>();
    get length() {
      return this.map.size;
    }
    key(index: number) {
      return [...this.map.keys()][index] ?? null;
    }
    getItem(key: string) {
      return this.map.get(key) ?? null;
    }
    setItem(key: string, value: string) {
      this.map.set(key, String(value));
    }
    removeItem(key: string) {
      this.map.delete(key);
    }
    clear() {
      this.map.clear();
    }
  }
  Object.defineProperty(globalThis, 'localStorage', {
    value: new MemoryStorage(),
    configurable: true,
    writable: true,
  });
}
