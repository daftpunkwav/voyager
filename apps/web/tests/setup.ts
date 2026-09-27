import { configure } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// NODE_ENV is pinned to 'development' in vite.config.ts (test.env): it must be
// set before module resolution, or react resolves to its production build,
// which has no act(). Assigning it here would already be too late.

// CI runners share CPUs: with the default 1 s window a waitFor can starve on
// busy parallel workers (a submit's microtask chain lands after the wait and
// the assertion times out). 5 s keeps the wait meaningful in that case and
// changes nothing about local runs, which resolve in milliseconds.
configure({ asyncUtilTimeout: 5000 });
