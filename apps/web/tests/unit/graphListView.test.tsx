/**
 * @file graphListView
 * @description Unit tests for the graph list rows: the row is a plain
 * container, the node summary is the control that selects it, and the "code
 * graph" entry is a separate control that stays keyboard reachable.
 */

import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { initI18n } from '@/i18n';
import type { GraphData } from '@/api/types';
import { GraphListView } from '@/pages/graph/GraphListView';

beforeAll(() => {
  initI18n();
});

// The row imports the similarity helper from the toolbar module; stubbing that
// module keeps the unit test off the graph store and the page provider.
vi.mock('@/components/graph/GraphControls', async () => {
  const { getSimilarNodes } = await import('@/components/graph/graphHelpers');
  return { getSimilarNodes };
});

const data: GraphData = {
  nodes: [
    {
      id: 'n1',
      name: 'voyager',
      stars: 12,
      kind: 'repo',
      category: 'tools',
      tags: ['a11y', 'web'],
    },
    { id: 'n2', name: 'guide', stars: 3, kind: 'doc' },
    { id: 'n3', name: 'sibling', stars: 5, kind: 'repo' },
  ],
  edges: [{ source: 'n1', target: 'n3', similarity: 0.8 }],
};

function renderList() {
  const onSelectNode = vi.fn();
  const onOpenResource = vi.fn();
  const onOpenCodeGraph = vi.fn();
  const view = render(
    <GraphListView
      data={data}
      selectedNodeId={null}
      onSelectNode={onSelectNode}
      onOpenResource={onOpenResource}
      onOpenCodeGraph={onOpenCodeGraph}
    />
  );
  const rows = Array.from(view.container.querySelectorAll('.graph-list-item'));
  return { rows, onSelectNode, onOpenResource, onOpenCodeGraph };
}

describe('graph list view rows', () => {
  it('keeps the code graph entry a focusable control outside the row selection control', () => {
    const { rows } = renderList();
    const row = rows[0];

    expect(row.querySelector('button button')).toBeNull();
    const entry = within(row).getByRole('button', { name: '代码图谱 →' });
    entry.focus();
    expect(document.activeElement).toBe(entry);
  });

  it('opens the code graph from the entry without selecting the node', () => {
    const { rows, onSelectNode, onOpenCodeGraph } = renderList();

    fireEvent.click(within(rows[0]).getByRole('button', { name: '代码图谱 →' }));
    expect(onOpenCodeGraph).toHaveBeenCalledWith(data.nodes[0]);
    expect(onSelectNode).not.toHaveBeenCalled();
  });

  it('selects the node from the row summary control', () => {
    const { rows, onSelectNode } = renderList();

    const controls = within(rows[0]).getAllByRole('button');
    expect(controls).toHaveLength(2);
    fireEvent.click(controls[0]);
    expect(onSelectNode).toHaveBeenCalledWith('n1');
  });

  it('opens the resource detail on double click of the row summary', () => {
    const { rows, onOpenResource } = renderList();

    fireEvent.doubleClick(within(rows[0]).getAllByRole('button')[0]);
    expect(onOpenResource).toHaveBeenCalledWith(data.nodes[0]);
  });

  it('offers no code graph entry for a non-repo node but still selects it', () => {
    const { rows, onSelectNode } = renderList();

    expect(within(rows[1]).queryByRole('button', { name: '代码图谱 →' })).toBeNull();
    fireEvent.click(within(rows[1]).getAllByRole('button')[0]);
    expect(onSelectNode).toHaveBeenCalledWith('n2');
  });

  it('marks the selected node row', () => {
    const view = render(
      <GraphListView
        data={data}
        selectedNodeId="n2"
        onSelectNode={vi.fn()}
        onOpenResource={vi.fn()}
        onOpenCodeGraph={vi.fn()}
      />
    );

    const rows = Array.from(view.container.querySelectorAll('.graph-list-item'));
    expect(rows[1].className).toContain('is-selected');
    expect(screen.getAllByRole('button', { name: '代码图谱 →' })).toHaveLength(2);
  });
});
