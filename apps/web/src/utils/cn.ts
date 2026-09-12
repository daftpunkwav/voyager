/**
 * @file cn
 * @description className merge helper with clsx semantics.
 */

import clsx, { type ClassValue } from 'clsx';

/** Merge class names, semantically equivalent to clsx. */
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}
