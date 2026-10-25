/**
 * @file codeRunner
 * @description Unit coverage for the fenced-code execution library: registry
 * language mapping, output shaping helpers, TypeScript transpile outcomes,
 * skulpt error formatting and the worker driver source shape. Engine runs
 * themselves are browser-bound and covered by the component-level stubs.
 */

import { describe, expect, it, vi } from 'vitest';
import { formatLogArgs, truncateText } from '@/lib/code-runner/output';
import { getRunner, isRunnable, normalizeLanguageId } from '@/lib/code-runner/registry';
import { buildWorkerSource, formatWorkerError } from '@/lib/code-runner/javascriptRunner';
import { buildPythonWorkerSource, formatSkulptError } from '@/lib/code-runner/pythonRunner';
import { transpileTypeScript } from '@/lib/code-runner/typescriptRunner';

describe('registry language mapping', () => {
  it('normalizes case, whitespace and aliases', () => {
    expect(normalizeLanguageId(' Python ')).toBe('python');
    expect(normalizeLanguageId('js')).toBe('javascript');
    expect(normalizeLanguageId('TS')).toBe('typescript');
    expect(normalizeLanguageId('py')).toBe('python');
    expect(normalizeLanguageId('bash')).toBe('bash');
    expect(normalizeLanguageId(undefined)).toBe('');
  });

  it('marks exactly the browser-runnable families', () => {
    for (const lang of ['python', 'py', 'javascript', 'js', 'typescript', 'ts', 'tsx']) {
      expect(isRunnable(lang)).toBe(true);
    }
    for (const lang of ['bash', 'json', 'mermaid', '', undefined]) {
      expect(isRunnable(lang)).toBe(false);
    }
  });

  it('hands out distinct runners per family (tsx keeps the JSX transform)', () => {
    expect(getRunner('python')?.id).toBe('python');
    expect(getRunner('javascript')?.id).toBe('javascript');
    expect(getRunner('tsx')?.id).toBe('tsx');
    expect(getRunner('bash')).toBeUndefined();
  });
});

describe('output shaping', () => {
  it('truncateText reports whether the cap fired', () => {
    expect(truncateText('abc', 5)).toEqual({ text: 'abc', truncated: false });
    expect(truncateText('abcdef', 3)).toEqual({ text: 'abc', truncated: true });
  });

  it('formatLogArgs prints strings verbatim and objects JSON-ish', () => {
    expect(formatLogArgs(['hello', 42, true, null])).toBe('hello 42 true null');
    expect(formatLogArgs([{ a: 1 }])).toBe('{\n  "a": 1\n}');
    expect(formatLogArgs([[1, 2]])).toContain('1');
  });

  it('formatLogArgs survives circular structures and functions', () => {
    const circular: Record<string, unknown> = {};
    circular['self'] = circular;
    expect(formatLogArgs([circular])).toContain('[Circular]');
    expect(formatLogArgs([() => {}])).toContain('[Function');
  });
});

describe('typescript transpile', () => {
  it('strips types and lowers imports', async () => {
    const out = await transpileTypeScript('const x: number = 1;\nexport default x;\n');
    expect('code' in out).toBe(true);
    if ('code' in out) {
      expect(out.code).not.toContain(': number');
      expect(out.code).toContain('exports.');
      expect(out.code).toContain('default = x');
    }
  });

  it('reports parse failures as diagnostics, not throws', async () => {
    const out = await transpileTypeScript('const x: = ;');
    expect('error' in out ? out.error : '').toContain('TypeScript parse failed');
  });
});

describe('worker source and error formatting', () => {
  it('worker driver captures console and shims require', () => {
    const src = buildWorkerSource();
    expect(src).toContain('self.onmessage');
    expect(src).toContain('formatLogArgs');
    expect(src).toContain("Cannot load module '");
    expect(src).toContain('postMessage');
  });

  it('formatWorkerError renders name, message and trimmed frames', () => {
    const err = new Error('boom');
    expect(formatWorkerError(err)).toContain('Error: boom');
    expect(formatWorkerError('plain')).toBe('plain');
    expect(formatWorkerError(null)).toBe('Unknown error');
  });
});

describe('python worker driver', () => {
  it('loads the vendored engine in the worker and reports the run back', () => {
    const src = buildPythonWorkerSource();
    expect(src).toContain("importScripts('/vendor/skulpt/skulpt.min.js')");
    expect(src).toContain("importScripts('/vendor/skulpt/skulpt-stdlib.js')");
    expect(src).toContain('importMainWithBody');
    expect(src).toContain('postMessage');
    // The engine never runs in the page: the driver only lives in the worker.
    expect(src).not.toContain('document.');
  });
});

/** Stand-in for the worker global scope a driver runs in. */
interface WorkerScope {
  onmessage: ((event: { data: unknown }) => Promise<void>) | null;
  postMessage: (message: unknown) => void;
  messages: unknown[];
  Sk?: unknown;
}

/** Install a driver source into a stand-in worker scope. */
function createWorkerScope(driverSource: string): WorkerScope {
  const scope: WorkerScope = {
    onmessage: null,
    postMessage: () => {},
    messages: [],
  };
  scope.postMessage = (message: unknown) => {
    scope.messages.push(message);
  };
  // The driver is a script that runs in the worker global scope.
  const install = new Function('self', driverSource);
  install(scope);
  return scope;
}

describe('worker driver execution', () => {
  it('runs the JavaScript driver and reports what the snippet printed', async () => {
    const scope = createWorkerScope(buildWorkerSource());
    expect(scope.onmessage).toBeTypeOf('function');
    await scope.onmessage?.({ data: { source: "console.log('hello from the driver');" } });
    expect(scope.messages).toHaveLength(1);
    expect(scope.messages[0]).toMatchObject({
      ok: true,
      stdout: 'hello from the driver',
    });
  });

  it('reports a failing snippet as an error instead of a result', async () => {
    const scope = createWorkerScope(buildWorkerSource());
    await scope.onmessage?.({ data: { source: "throw new Error('boom');" } });
    expect(scope.messages[0]).toMatchObject({ ok: false });
  });

  it('runs the Python driver against the engine interface it expects', async () => {
    const scope = createWorkerScope(buildPythonWorkerSource());
    const seen: { source?: string; limit?: number } = {};
    scope.Sk = {
      configure: () => {},
      builtinFiles: { files: {} },
      python3: {},
      misceval: { asyncToPromise: async (fn: () => unknown) => fn() },
      importMainWithBody: (_name: string, _dump: boolean, code: string) => {
        seen.source = code;
        throw Object.assign(new Error('run failed'), { tp$name: 'ValueError' });
      },
    };
    vi.stubGlobal('importScripts', () => {});
    try {
      await scope.onmessage?.({ data: { source: 'print(1)', maxOutputChars: 100 } });
    } finally {
      vi.unstubAllGlobals();
    }
    expect(seen.source).toBe('print(1)');
    // The failure is described, not passed through: the exception itself does not clone.
    expect(scope.messages[0]).toMatchObject({ ok: false, error: { tp$name: 'ValueError' } });
  });
});

describe('skulpt error formatting', () => {
  it('renders python-style tp$name plus first arg detail', () => {
    expect(
      formatSkulptError({ tp$name: 'NameError', args: { v: [{ v: "name 'x' is not defined" }] } })
    ).toBe("NameError: name 'x' is not defined");
    expect(formatSkulptError(new Error('engine gone'))).toContain('engine gone');
    expect(formatSkulptError(undefined)).toBe('Unknown error');
  });

  it('flags TimeLimitError as timeout shape via message contract', () => {
    const text = formatSkulptError({ tp$name: 'TimeLimitError', args: { v: [{ v: 'too long' }] } });
    expect(/TimeLimit|timed out/i.test(text) || text.startsWith('TimeLimitError')).toBe(true);
  });
});
