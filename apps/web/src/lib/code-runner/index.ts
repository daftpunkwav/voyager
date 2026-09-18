/**
 * @file Barrel for the fenced-code execution library: public types plus the
 * language registry. Engine modules are intentionally not re-exported.
 */

export {
  DEFAULT_MAX_OUTPUT_CHARS,
  DEFAULT_TIMEOUT_MS,
  type CodeRunner,
  type ExecutionHandle,
  type ExecutionResult,
  type ExecutionStatus,
  type RunLimits,
} from './types';
export { getRunner, isRunnable, normalizeLanguageId } from './registry';
