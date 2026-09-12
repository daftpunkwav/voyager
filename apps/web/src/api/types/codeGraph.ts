/**
 * @file types/codeGraph.ts
 * @description Code-graph domain types (CodeGraph*: in-repository code structure graphs).
 *
 * Split out of api/types.ts; pages and hooks still import from the
 * @/api/types barrel.
 */

export interface CodeGraphNode {
  id: string;
  type: 'file' | 'function' | 'class' | 'module';
  name: string;
  path: string;
  language: string;
  size: number;
  complexity?: number;
}

export interface CodeGraphEdge {
  source: string;
  target: string;
  relation: 'imports' | 'calls' | 'extends' | 'implements';
}

export interface CodeGraphData {
  nodes: CodeGraphNode[];
  edges: CodeGraphEdge[];
  stats: { node_count: number; edge_count: number };
}
