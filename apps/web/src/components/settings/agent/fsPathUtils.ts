/**
 * @file fsPathUtils
 * @description Path validation helpers for additional filesystem roots (shared by read-only and read-write roots).
 */

/** Absolute-path check: Windows drive letters (C:\ or C:/), UNC (\\), or Unix (/) prefixes */
export function isAbsolutePath(line: string): boolean {
  return /^[A-Za-z]:[\\/]/.test(line) || line.startsWith('\\\\') || line.startsWith('/');
}
