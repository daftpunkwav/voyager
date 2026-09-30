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

/** Project index status as derived from list_index_jobs (api/codeGraph maps
 *  the raw queue row; fields the queue does not persist are not declared). */
export interface GraphIndexStatus {
  project_id: string;
  /** The backend repo_path (the local clone directory). */
  engine_project: string;
  status:
    | 'NONE'
    | 'QUEUED'
    | 'CLONING'
    | 'INDEXING'
    | 'READY'
    | 'STALE'
    | 'CLONE_FAILED'
    | 'INDEX_FAILED';
  error?: string | null;
}
