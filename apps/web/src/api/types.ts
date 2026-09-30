/**
 * @file types.ts
 * @description Barrel file for frontend domain types (9 domains: common, sources,
 * notes, graph, settings, llm, agent, usage, system).
 *
 * Types are declared against the real backend capability return shapes and
 * re-exported here, so existing `import type { ... } from '@/api/types'`
 * imports keep working. Data access lives in thin per-domain api/<domain>.ts
 * modules; cross-domain chat interaction goes through the bridge/chatSend
 * contract; the settings form domain calls callCapability directly.
 * (Code-graph render shapes live in components/code-graph/types — the former
 * types/codeGraph.ts declared a node/edge shape the graph store never
 * returns and had no consumers.)
 */

export * from './types/common';
export * from './types/sources';
export * from './types/notes';
export * from './types/graph';
export * from './types/settings';
export * from './types/llm';
export * from './types/agent';
export * from './types/usage';
export * from './types/system';
