/**
 * Ambient augmentation that `@testing-library/jest-dom/vitest` used to supply
 * as a side effect of tests/setup.ts importing it.
 *
 * That entry can no longer be imported: its first statement is a bare
 * `import { expect } from 'vitest'`, which Node resolves relative to the repo
 * root's node_modules, so it breaks whenever npm nests vitest inside
 * apps/web/node_modules. setup.ts now registers the matchers through
 * `@testing-library/jest-dom/matchers`, which has no runtime dependency on
 * vitest — so the vitest-side type augmentation is declared here instead.
 */

import type { TestingLibraryMatchers } from '@testing-library/jest-dom/matchers';

declare module 'vitest' {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  interface Assertion<T = any> extends TestingLibraryMatchers<any, T> {}
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  interface AsymmetricMatchersContaining extends TestingLibraryMatchers<any, any> {}
}
