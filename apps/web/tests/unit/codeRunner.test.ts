/**
 * @file codeRunner
 * @description Unit coverage for the fenced-code execution library: registry
 * language mapping, output shaping helpers, TypeScript transpile outcomes,
 * skulpt error formatting and the driver sources the worker installs. The
 * drivers run in a simulated worker scope (see helpers/workerHarness.ts), so
 * the engine runs themselves are covered here rather than in the browser.
 */

import { describe, expect, it, vi } from 'vitest';
import { formatLogArgs, truncateText } from '@/lib/code-runner/output';
import { getRunner, isRunnable, normalizeLanguageId } from '@/lib/code-runner/registry';
import {
  buildWorkerSource,
  formatWorkerError,
  runJavascript,
} from '@/lib/code-runner/javascriptRunner';
import { buildPythonWorkerSource, formatSkulptError } from '@/lib/code-runner/pythonRunner';
import { transpileTypeScript } from '@/lib/code-runner/typescriptRunner';
import {
  createWorkerHarness,
  installFakeWorker,
  SKULPT_ENGINE_URL,
  SKULPT_STDLIB_URL,
} from './helpers/workerHarness';

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

describe('worker driver execution', () => {
  it('runs the JavaScript driver and reports what the snippet printed', async () => {
    const harness = createWorkerHarness();
    await harness.deliver({ driver: buildWorkerSource() });
    await harness.deliver({ source: "console.log('hello from the driver');" });
    expect(harness.reports).toHaveLength(1);
    expect(harness.reports[0]).toMatchObject({
      ok: true,
      stdout: 'hello from the driver',
    });
  });

  it('reports a failing snippet as an error instead of a result', async () => {
    const harness = createWorkerHarness();
    await harness.deliver({ driver: buildWorkerSource() });
    await harness.deliver({ source: "throw new Error('boom');" });
    expect(harness.reports[0]).toMatchObject({ ok: false });
  });

  it('loads the Python engine from the vendored scripts and runs the snippet', async () => {
    const { engine, sources } = fakeSkulpt();
    const harness = createWorkerHarness({ engine });
    await harness.deliver({ driver: buildPythonWorkerSource() });
    await harness.deliver({ source: 'print(1)', maxOutputChars: 100 });
    // The engine is only there because the driver imported the vendored scripts.
    expect(harness.imports).toContain(SKULPT_ENGINE_URL);
    expect(harness.imports).toContain(SKULPT_STDLIB_URL);
    expect(sources).toEqual(['print(1)']);
    expect(harness.reports[0]).toMatchObject({ ok: true, output: 'through the worker\n' });
  });

  it('reports a failing Python run with the error the engine raised', async () => {
    const { engine } = fakeSkulpt();
    const harness = createWorkerHarness({ engine });
    await harness.deliver({ driver: buildPythonWorkerSource() });
    await harness.deliver({ source: 'raise ValueError("run failed")' });
    // The failure is described, not passed through: the exception itself does not clone.
    expect(harness.reports[0]).toMatchObject({ ok: false, error: { tp$name: 'ValueError' } });
  });
});

/** Engine stand-in for the skulpt surface the Python driver drives. */
function fakeSkulpt(): { engine: unknown; sources: string[] } {
  const sources: string[] = [];
  let output: (text: string) => void = () => {};
  const engine = {
    configure: (options: { output: (text: string) => void }) => {
      output = options.output;
    },
    builtinFiles: { files: {} },
    python3: {},
    misceval: { asyncToPromise: async (fn: () => unknown) => fn() },
    importMainWithBody: (_name: string, _dump: boolean, code: string) => {
      sources.push(code);
      if (code.includes('raise')) {
        throw Object.assign(new Error('run failed'), { tp$name: 'ValueError' });
      }
      output('through the worker\n');
    },
  };
  return { engine, sources };
}

/**
 * Load a fresh copy of the Python runner: it keeps its worker between runs,
 * so a test needs a runner that starts without one.
 */
async function loadPythonRunner(): Promise<typeof import('@/lib/code-runner/pythonRunner')> {
  vi.resetModules();
  return import('@/lib/code-runner/pythonRunner');
}

describe('runner execution', () => {
  it('runs a JavaScript snippet in the worker and reports what it printed', async () => {
    const { urls } = installFakeWorker();
    try {
      const handle = runJavascript("console.log('through the worker');");
      const result = await handle.done;
      expect(result.status).toBe('ok');
      expect(result.output).toContain('through the worker');
      expect(urls).toEqual(['/code-runner-worker.js']);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('runs a Python snippet in the worker and reports what it printed', async () => {
    const { runPython } = await loadPythonRunner();
    const { engine } = fakeSkulpt();
    const { urls, harnesses } = installFakeWorker({ engine });
    try {
      const handle = runPython("print('through the worker')");
      const result = await handle.done;
      expect(result.status).toBe('ok');
      expect(result.output).toContain('through the worker');
      expect(urls).toEqual(['/code-runner-worker.js']);
      // The engine is only there because the driver imported the vendored scripts.
      expect(harnesses.at(0)?.imports).toContain(SKULPT_ENGINE_URL);
      expect(harnesses.at(0)?.imports).toContain(SKULPT_STDLIB_URL);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('reports a Python failure with the error the engine raised', async () => {
    const { runPython } = await loadPythonRunner();
    const { engine } = fakeSkulpt();
    installFakeWorker({ engine });
    try {
      const handle = runPython('raise ValueError("run failed")');
      const result = await handle.done;
      expect(result.status).toBe('error');
      expect(result.error).toContain('ValueError');
    } finally {
      vi.unstubAllGlobals();
    }
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
