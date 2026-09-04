import { describe, expect, it } from 'vitest';
import {
  layoutRows,
  nodePos,
  snap,
  applyNodeDrag,
  anchorFor,
  CONNECTOR_GLYPH,
  NODE_W,
  NODE_H,
  GRID,
  type WfGraph,
  type WfNode,
} from '@/lib/workflows';

/** event -> function -> event, the minimal EPK shape. */
const linearGraph = (): WfGraph => ({
  start: 'e0',
  nodes: [
    { key: 'e0', type: 'event', label: 'Start' },
    { key: 'f1', type: 'function', kind: 'manual', label: 'Tun' },
    { key: 'e1', type: 'event', label: 'Ende' },
  ],
  edges: [
    { key: 'a', from: 'e0', to: 'f1' },
    { key: 'b', from: 'f1', to: 'e1' },
  ],
});

describe('layoutRows (EPK vertical auto-layout, #129)', () => {
  it('places each successor strictly below its predecessor', () => {
    const pos = layoutRows(linearGraph());
    expect(pos.get('f1')!.y).toBeGreaterThan(pos.get('e0')!.y);
    expect(pos.get('e1')!.y).toBeGreaterThan(pos.get('f1')!.y);
  });

  it('is deterministic for the same graph', () => {
    const g = linearGraph();
    expect([...layoutRows(g)]).toEqual([...layoutRows(g)]);
  });

  it('centres branches at the same depth around the tree midpoint', () => {
    const g: WfGraph = {
      start: 's',
      nodes: [
        { key: 's', type: 'connector', connector: 'xor', direction: 'split' },
        { key: 'a', type: 'function', kind: 'manual' },
        { key: 'b', type: 'function', kind: 'manual' },
      ],
      edges: [
        { key: 'e1', from: 's', to: 'a' },
        { key: 'e2', from: 's', to: 'b' },
      ],
    };
    const pos = layoutRows(g);
    expect(pos.get('a')!.y).toBe(pos.get('b')!.y);
    expect(pos.get('a')!.x).not.toBe(pos.get('b')!.x);
  });

  it('never places a node off the top/left of the canvas', () => {
    const pos = layoutRows(linearGraph());
    for (const p of pos.values()) {
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeGreaterThanOrEqual(0);
    }
  });
});

describe('nodePos', () => {
  it('uses the stored props.x/y when both are finite numbers', () => {
    const n: WfNode = { key: 'n', type: 'event', props: { x: 40, y: 80 } };
    expect(nodePos(n, new Map([['n', { x: 0, y: 0 }]]))).toEqual({ x: 40, y: 80 });
  });

  it('falls back to the auto-layout when props are missing, partial, or not numbers', () => {
    const auto = new Map([['n', { x: 5, y: 6 }]]);
    expect(nodePos({ key: 'n', type: 'event' }, auto)).toEqual({ x: 5, y: 6 });
    expect(nodePos({ key: 'n', type: 'event', props: { x: 40 } }, auto)).toEqual({ x: 5, y: 6 });
    expect(nodePos({ key: 'n', type: 'event', props: { x: 'nope', y: 1 } }, auto)).toEqual({
      x: 5,
      y: 6,
    });
  });
});

describe('snap', () => {
  it('rounds to the nearest grid step', () => {
    expect(snap(5, 16)).toBe(0);
    expect(snap(9, 16)).toBe(16);
    expect(snap(GRID * 3 + 1, GRID)).toBe(GRID * 3);
  });
});

describe('applyNodeDrag', () => {
  it('adds the delta to the current position and snaps the result', () => {
    const n: WfNode = { key: 'n', type: 'event', props: { x: 100, y: 100 } };
    expect(applyNodeDrag(n, 15, -7, new Map())).toEqual({ x: snap(115), y: snap(93) });
  });

  it('clamps to the top-left canvas edge — a node cannot be dragged off-canvas', () => {
    const n: WfNode = { key: 'n', type: 'event', props: { x: 0, y: 0 } };
    expect(applyNodeDrag(n, -50, -50, new Map())).toEqual({ x: 0, y: 0 });
  });

  it('falls back to the auto position for a node with no stored props yet', () => {
    const n: WfNode = { key: 'n', type: 'event' };
    const auto = new Map([['n', { x: 32, y: 48 }]]);
    expect(applyNodeDrag(n, GRID, 0, auto)).toEqual({ x: 32 + GRID, y: 48 });
  });
});

describe('anchorFor', () => {
  it('meets the flat top edge coming in and the flat bottom edge going out', () => {
    const pos = { x: 10, y: 20 };
    expect(anchorFor(pos, 'in')).toEqual({ x: 10 + NODE_W / 2, y: 20 });
    expect(anchorFor(pos, 'out')).toEqual({ x: 10 + NODE_W / 2, y: 20 + NODE_H });
  });
});

describe('CONNECTOR_GLYPH', () => {
  it('has the EPK operator glyph for every connector kind', () => {
    expect(CONNECTOR_GLYPH).toEqual({ and: '∧', or: '∨', xor: '⊕' });
  });
});
