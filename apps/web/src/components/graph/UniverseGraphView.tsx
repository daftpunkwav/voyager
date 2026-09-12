/**
 * @file UniverseGraphView
 * @description L0 3D universe view reusing the L1 GraphScene (engine-style point cloud with OrbitControls).
 *
 * Responsibilities:
 * - Project universe data through the L0 layout into GraphScene render data
 * - Reuse the shared GraphScene with OrbitControls and camera fly-to targets
 * - Guard node clicks against double-firing during camera animation
 */
import { useEffect, useMemo, useState } from 'react';
import type { GraphData, GraphNode } from '@/api/types';
import { GraphScene, computeCameraTarget } from '@/components/graph-viz';
import type { CameraTarget, CodeGraphNode } from '@/components/graph-viz';
import { useGraphStore } from '@/stores/graphStore';
import {
  applySelectionRelatedness,
  projectGraphToScene,
  projectIdFromSceneNode,
} from './l0Layout3d';
import { DEFAULT_DISPLAY_SETTINGS, type DisplaySettings } from '@/components/code-graph/density';

interface UniverseGraphViewProps {
  data: GraphData;
  onNodeClick: (node: GraphNode) => void;
  onNodeDoubleClick: (node: GraphNode) => void;
  /** Increment to reset the camera to the full-graph overview. */
  cameraResetTick?: number;
}

const UNIVERSE_DISPLAY: DisplaySettings = {
  ...DEFAULT_DISPLAY_SETTINGS,
  edgeBrightness: 0.42,
  nodeGlow: 0.9,
  bloom: 0.18,
};

export function UniverseGraphView({
  data,
  onNodeClick,
  onNodeDoubleClick,
  cameraResetTick = 0,
}: UniverseGraphViewProps) {
  const layoutMode = useGraphStore((s) => s.layoutMode);
  const selectedNodeId = useGraphStore((s) => s.selectedNodeId);
  const highlightNodeId = useGraphStore((s) => s.highlightNodeId);

  const baseScene = useMemo(() => projectGraphToScene(data, layoutMode), [data, layoutMode]);

  const sceneData = useMemo(
    () => applySelectionRelatedness(baseScene, data, selectedNodeId),
    [baseScene, data, selectedNodeId]
  );

  const highlightedIds = useMemo(() => {
    const focus = new Set<string>();
    if (selectedNodeId) focus.add(selectedNodeId);
    if (highlightNodeId) focus.add(highlightNodeId);
    if (focus.size === 0) return null;

    const neighbor = new Set<string>(focus);
    for (const e of data.edges) {
      if (focus.has(e.source)) neighbor.add(e.target);
      if (focus.has(e.target)) neighbor.add(e.source);
    }

    const ids = new Set<number>();
    for (const n of data.nodes) {
      if (!neighbor.has(n.id)) continue;
      const hit = sceneData.nodes.find((s) => s.qualified_name === n.id);
      if (hit) ids.add(hit.id);
    }
    return ids.size > 0 ? ids : null;
  }, [data.edges, data.nodes, sceneData.nodes, selectedNodeId, highlightNodeId]);

  const [cameraTarget, setCameraTarget] = useState<CameraTarget | null>(null);
  const [lastClickAt, setLastClickAt] = useState(0);

  useEffect(() => {
    if (cameraResetTick <= 0) return;
    const ids = new Set(sceneData.nodes.map((n) => n.id));
    setCameraTarget(computeCameraTarget(sceneData.nodes, ids));
  }, [cameraResetTick, sceneData.nodes]);

  const handleClick = (node: CodeGraphNode) => {
    const projectId = projectIdFromSceneNode(node, data);
    const project = data.nodes.find((n) => n.id === projectId);
    if (!project) return;
    const now = Date.now();
    if (now - lastClickAt < 320) {
      onNodeDoubleClick(project);
      setLastClickAt(0);
      return;
    }
    setLastClickAt(now);
    onNodeClick(project);
    setCameraTarget(computeCameraTarget(sceneData.nodes, new Set([node.id])));
  };

  return (
    <div className="universe-graph-3d" style={{ position: 'absolute', inset: 0 }}>
      <GraphScene
        data={sceneData}
        highlightedIds={highlightedIds}
        cameraTarget={cameraTarget}
        showLabels
        enableBloom
        display={UNIVERSE_DISPLAY}
        onNodeClick={handleClick}
        onBackgroundClick={() => {
          setCameraTarget(null);
          useGraphStore.getState().selectNode(null);
        }}
      />
    </div>
  );
}
