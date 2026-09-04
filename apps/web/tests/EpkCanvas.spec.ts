import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import de from '@/i18n/de.json';
import EpkCanvas from '@/components/workflow/EpkCanvas.vue';
import { layoutRows, applyNodeDrag, GRID, type WfGraph } from '@/lib/workflows';

const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });

/** event -> XOR connector -> function, the minimal shape covering all three
 *  EPK node types. */
function graph(): WfGraph {
  return {
    start: 'e0',
    nodes: [
      { key: 'e0', type: 'event', label: 'Alarm' },
      { key: 'c0', type: 'connector', connector: 'xor', direction: 'split' },
      { key: 'f0', type: 'function', kind: 'manual', label: 'Prüfen' },
    ],
    edges: [
      { key: 'a', from: 'e0', to: 'c0' },
      { key: 'b', from: 'c0', to: 'f0' },
    ],
  };
}

function factory(graphValue: WfGraph, editable: boolean) {
  return mount(EpkCanvas, {
    props: { graph: graphValue, editable },
    global: { plugins: [i18n] },
  });
}

describe('EpkCanvas (E07-19 / #129)', () => {
  it('renders real EPK notation: hexagon event, rounded-rect function, connector circle + glyph', () => {
    const w = factory(graph(), true);
    expect(w.find('.wfp__node--event polygon').exists()).toBe(true);
    expect(w.find('.wfp__node--function rect').exists()).toBe(true);
    expect(w.find('.wfp__node--connector circle').exists()).toBe(true);
    expect(w.find('.wfp__glyph').text()).toBe('⊕'); // xor
  });

  it('drops role="img" when editable, so the focusable nodes stay in the a11y tree', () => {
    const editable = factory(graph(), true);
    expect(editable.find('.wfp').attributes('role')).toBeUndefined();
    const readonly = factory(graph(), false);
    expect(readonly.find('.wfp').attributes('role')).toBe('img');
  });

  it('moves the focused node with arrow keys, matching applyNodeDrag exactly', async () => {
    const g = graph();
    const w = factory(g, true);
    const auto = layoutRows(g);
    const expected = applyNodeDrag(g.nodes[2], GRID, 0, auto);

    await w.find('.wfp__node--function').trigger('keydown', { key: 'ArrowRight' });

    expect(g.nodes[2].props).toEqual(expected);
  });

  it('nudges by 4x the grid with Shift held', async () => {
    const g = graph();
    const w = factory(g, true);
    const auto = layoutRows(g);
    const expected = applyNodeDrag(g.nodes[2], 0, GRID * 4, auto);

    await w
      .find('.wfp__node--function')
      .trigger('keydown', { key: 'ArrowDown', shiftKey: true });

    expect(g.nodes[2].props).toEqual(expected);
  });

  it('emits remove-node and does not touch the graph itself on Delete', async () => {
    const g = graph();
    const w = factory(g, true);

    await w.find('.wfp__node--function').trigger('keydown', { key: 'Delete' });

    expect(w.emitted('remove-node')).toEqual([['f0']]);
    expect(g.nodes).toHaveLength(3); // the parent owns the actual removal
  });

  it('is not focusable and ignores keyboard input when read-only', async () => {
    const g = graph();
    const w = factory(g, false);
    const node = w.find('.wfp__node--event');

    expect(node.attributes('tabindex')).toBe('-1');
    await node.trigger('keydown', { key: 'ArrowRight' });

    expect(g.nodes[0].props).toBeUndefined();
  });
});
