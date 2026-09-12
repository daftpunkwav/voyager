/**
 * @file graph-viz/index
 * @description Shared R3F visualization root barrel for the L0 and L1 graph pages.
 *
 * Re-exports the 3D scene components, types and helpers from the code-graph
 * directory so GraphPage (L0) and CodeGraphPage (L1) share the same visual
 * root instead of duplicating implementations.
 */
export { GraphScene, computeCameraTarget } from '@/components/code-graph/GraphScene';
export type { CameraTarget } from '@/components/code-graph/GraphScene';
export { NodeCloud } from '@/components/code-graph/NodeCloud';
export { EdgeLines } from '@/components/code-graph/EdgeLines';
export { NodeLabels } from '@/components/code-graph/NodeLabels';
export {
  NodeTooltipContent,
  NodeTooltipTracker,
  NodeTooltip,
} from '@/components/code-graph/NodeTooltip';
export type {
  CodeGraphNode,
  CodeGraphEdge,
  CodeGraphData,
  GraphNode,
  GraphEdge,
  GraphData,
  GraphIndexStatus,
  NodeStatus,
} from '@/components/code-graph/types';
export { toRenderGraph } from '@/components/code-graph/renderGraph';
export { colorForLabel, colorForStatus, STATUS_LEGEND } from '@/components/code-graph/colors';
// Layout helpers (components/graph) export pure functions only; components are
// deliberately not re-exported from this barrel — UniverseGraphView imports this
// barrel itself, so re-exporting would create a barrel import cycle.
export { projectGraphToScene, projectIdFromSceneNode } from '@/components/graph/l0Layout3d';
