/**
 * @file types.ts
 * @description Barrel file for frontend domain types (10 domains: common, sources,
 * notes, graph, codeGraph, settings, llm, agent, usage, system).
 *
 * Types are declared against the real backend capability return shapes and
 * re-exported here, so existing `import type { ... } from '@/api/types'`
 * imports keep working. Data access lives in thin per-domain api/<domain>.ts
 * modules; cross-domain chat interaction goes through the bridge/chatSend
 * contract; the settings form domain calls callCapability directly.
 */

export * from './types/common';
export * from './types/sources';
export * from './types/notes';
export * from './types/graph';
export * from './types/codeGraph';
export * from './types/settings';
export * from './types/llm';
export * from './types/agent';
export * from './types/usage';
export * from './types/system';
