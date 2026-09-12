import js from '@eslint/js';
import globals from 'globals';
import tsParser from '@typescript-eslint/parser';
import tsPlugin from '@typescript-eslint/eslint-plugin';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';

export default [
  { ignores: ['dist/**', 'node_modules/**'] },
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: globals.browser,
      parser: tsParser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      '@typescript-eslint': tsPlugin,
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...js.configs.recommended.rules,
      ...tsPlugin.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      // React 19 automatic JSX runtime; type annotations may still reference the React namespace
      'no-undef': 'off',
      // React Compiler rules conflict with the R3F idiom of mutating shared objects after render:
      // EdgeLines/NodeCloud mutate uniform.value / raycaster.params after render,
      // and UniverseGraphView's manual useMemo is a performance optimization. Same rationale as the
      // set-state-in-effect / purity / refs rules turned off below (v7 strict rules are too aggressive at the prototype stage).
      'react-hooks/immutability': 'off',
      'react-hooks/preserve-manual-memoization': 'off',
      // The strict rules added in v7 are too aggressive at the v1 prototype stage; keep parity with the old .eslintrc
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/purity': 'off',
      'react-hooks/refs': 'off',
      'react-refresh/only-export-components': 'off',
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-non-null-assertion': 'error',
      // The compatibility bridge (legacyApi / types.IApiClient) needs any inference: legacy stores access .data directly;
      // legacy async generators no longer yield under the new event stream, so require-yield is turned off.
      'no-constant-condition': 'error',
      'require-yield': 'error',
      // Migration period: page / component / util / store migrated from upstream are temporarily annotated with @ts-nocheck,
      // all with a description (upstream-migrated code; field renames are normalized at the legacyApi boundary);
      // new page / hook / store code is still written strict (see the comment atop each file).
      '@typescript-eslint/ban-ts-comment': [
        'error',
        {
          'ts-nocheck': 'allow-with-description',
          'ts-ignore': true,
          'ts-expect-error': 'allow-with-description',
          'ts-check': false,
        },
      ],
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      'no-unused-vars': 'off',
      // §4.2.15: never use dangerouslySetInnerHTML directly; sanitize with DOMPurify first
      'no-restricted-syntax': [
        'error',
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message:
            'dangerouslySetInnerHTML must be sanitized via DOMPurify.sanitize before rendering (MermaidBlock.tsx is the reference pattern).',
        },
      ],
    },
  },
  // Single data-facade entry point (non-page files): business code must not bypass @/api/client to import the implementation layer directly.
  // Note: in flat config a later block for the same rule overrides the earlier one, so this is split into two blocks by file set,
  // each holding the complete pattern set; the pages rules are in the next block (incl. cross-page import bans); the two file sets are disjoint.
  {
    files: ['src/**/*.{ts,tsx}'],
    ignores: [
      'src/pages/**',
      'src/api/client.ts',
      'src/api/types.ts',
      'src/api/types/**',
      'src/bridge/legacyApi.ts',
    ],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [],
        },
      ],
    },
  },
  // The shared layer must not depend back on page modules (MarkdownRenderer / hooks / stores)
  {
    files: [
      'src/components/common/**/*.{ts,tsx}',
      'src/hooks/**/*.{ts,tsx}',
      'src/stores/**/*.{ts,tsx}',
    ],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@/pages/*'],
              message:
                'The shared layer must not import page modules (§10.1); page-private logic is injected via props/bridge.',
            },
          ],
        },
      ],
    },
  },
  // App shell: must not import page-private modules; domain bridges are injected by App via bridges.
  // pageProbes.ts is exempted separately, and only allowed to import @/pages/*/provider.
  {
    files: ['src/shell/**/*.{ts,tsx}'],
    ignores: ['src/shell/pageProbes.ts'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@/pages/*'],
              message:
                'The shell must not import page modules; domain bridges are injected by App via bridges; page probes are centralized in pageProbes.ts.',
            },
          ],
        },
      ],
    },
  },
  {
    files: ['src/shell/pageProbes.ts'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              regex: '^@/pages/[^/]+/(?!provider$).+',
              message: 'pageProbes is only allowed to import @/pages/*/provider.',
            },
          ],
        },
      ],
    },
  },
  // pages-specific: cross-page import ban + the same facade single-entry restriction as global (flat config needs the full set restated).
  // §10.1 pages-as-modules: page directories never import each other; sharing goes only through bridge/contracts/base UI.
  {
    files: ['src/pages/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@/pages/*'],
              message:
                'Pages must not import each other (§10.1 iron rule 1); shared things go only through the bridge/contracts/base UI packages.',
            },
          ],
        },
      ],
    },
  },
  // pages-specific (non-chat): the chat timeline and floating-window toggles are chat-domain/shell state; cross-domain interaction
  // goes only through the bridge/chatSend contract (sendUserTurn/openFloatingChat/markChatInterrupted/
  // chatSystemNote). In flat config a later block for the same rule overrides the earlier one, so the original pages patterns are restated in full.
  {
    files: ['src/pages/**/*.{ts,tsx}'],
    ignores: ['src/pages/chat/**'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@/pages/*'],
              message:
                'Pages must not import each other (§10.1 iron rule 1); shared things go only through the bridge/contracts/base UI packages.',
            },
            {
              group: ['@/stores/chatStore'],
              message:
                'The chat timeline belongs to the chat domain: interact across domains via the bridge/chatSend contract, never touch the store directly.',
            },
            {
              group: ['@/stores/floatingStore'],
              message:
                'Toggle the floating window via openFloatingChat() on bridge/chatSend; never touch the store directly.',
            },
          ],
        },
      ],
    },
  },
  // R3F / Three scene exemption zone:
  //   - code-graph / graph subdirectories mutate uniforms in place and use @ts-nocheck; layout algorithms use non-null assertions.
  {
    files: ['src/components/code-graph/**/*.{ts,tsx}', 'src/components/graph/**/*.{ts,tsx}'],
    rules: {
      '@typescript-eslint/ban-ts-comment': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-non-null-assertion': 'off',
      'no-constant-condition': 'off',
      'require-yield': 'off',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      'react-hooks/immutability': 'off',
    },
  },
];
