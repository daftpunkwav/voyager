/**
 * @file types
 * @description Shared types for the code graph: nodes, edges, and index status.
 */

export type NodeStatus =
  'dead' | 'single' | 'entry' | 'test' | 'exported' | 'normal' | 'structural';

export interface CodeGraphNode {
  id: number;
  x: number;
  y: number;
  z: number;
  label: string;
  name: string;
  kind?: string;
  file_path?: string;
  qualified_name?: string;
  start_line?: number;
  end_line?: number;
  size: number;
  color: string;
  status?: NodeStatus;
  in_calls?: number;
  /** Relatedness to the selected node; undefined when nothing is selected. */
  relatedness?: number;
}

export interface CodeGraphEdge {
  source: number;
  target: number;
  type?: string;
  relation?: string;
}

export interface CodeGraphData {
  nodes: CodeGraphNode[];
  edges: CodeGraphEdge[];
  total_nodes?: number;
  linked_projects?: never[];
  stats?: {
    node_count: number;
    edge_count: number;
    total_nodes?: number;
  };
}

/** Aliases kept for compatibility with ported component naming. */
export type GraphNode = CodeGraphNode;
export type GraphEdge = CodeGraphEdge;
export type GraphData = CodeGraphData;

export interface GraphIndexStatus {
  project_id: string;
  engine_project: string;
  local_path?: string | null;
  head_sha?: string | null;
  branch?: string | null;
  status:
    | 'NONE'
    | 'QUEUED'
    | 'CLONING'
    | 'INDEXING'
    | 'READY'
    | 'STALE'
    | 'CLONE_FAILED'
    | 'INDEX_FAILED';
  /** The index_jobs model does not persist the mode; undefined when the data source omits it. */
  index_mode?: 'fast' | 'moderate' | 'full';
  node_count?: number | null;
  edge_count?: number | null;
  indexed_at?: string | null;
  error?: string | null;
  error_kind?: 'network' | 'service' | 'cancelled' | 'unknown' | null;
  cancel_requested?: boolean;
}
