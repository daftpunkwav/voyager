/**
 * @file types/common.ts
 * @description Shared base types: pagination envelope and unified error shape.
 *
 * Domain-agnostic types referenced by multiple domain files live here.
 * Split out of api/types.ts; pages and hooks still import from the
 * @/api/types barrel.
 */

/** Generic pagination envelope. */
export interface PaginatedList<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

/** Unified error shape. */
export interface ApiError {
  code: string;
  message: string;
  status?: number;
  details?: Record<string, unknown>;
}
