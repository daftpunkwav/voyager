import { configure } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// Vitest needs the development build; otherwise React Testing Library's act() is unavailable.
process.env.NODE_ENV = 'development';

// CI runners share CPUs: with the default 1 s window a waitFor can starve on
// busy parallel workers (a submit's microtask chain lands after the wait and
// the assertion times out). 5 s keeps the wait meaningful in that case and
// changes nothing about local runs, which resolve in milliseconds.
configure({ asyncUtilTimeout: 5000 });
