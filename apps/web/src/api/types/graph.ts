/**
 * @file types/graph.ts
 * @description Graph domain types (resource similarity graph: GraphData / GraphNode / GraphEdge).
 *
 * Split out of api/types.ts; pages and hooks still import from the
 * @/api/types barrel.
 */

import type { AgentMessage } from './agent';
import type { Project } from './sources';

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphNode {
  id: string;
  name: string;
  full_name?: string;
  language?: string | null;
  stars: number;
  category_id?: string | null;
  progress?: Project['progress'];
  foundation_score?: number;
  hubness?: number;
  cluster_id?: string | null;
  cluster_size?: number;
  description?: string | null;
  /** L0 resource-node extension: resource kind (repo/doc/web) and metadata. */
  kind?: 'repo' | 'doc' | 'web';
  tags?: string[];
  category?: string;
  status?: string;
  /** Library id of the L0 resource (qualified_name minus the kind prefix), for detail navigation. */
  resourceId?: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  similarity: number;
  relation?: string;
  reasons?: string[];
  edge_type?: string;
}

export interface GraphStats {
  node_count: number;
  edge_count: number;
  cluster_count: number;
  updated_ts: number;
}

export interface GraphGuideSession {
  session_id: string;
  messages: AgentMessage[];
}
