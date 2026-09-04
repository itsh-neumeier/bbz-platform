<script setup lang="ts">
/**
 * EPK process-chain canvas (E07-19 / #129). Renders `graph` in real EPK
 * notation — event = hexagon, function = rounded rectangle, connector = a
 * small circle with its ∧/∨/⊕ operator glyph — laid out vertically
 * top-to-bottom (`layoutRows`), one glyph-agnostic bounding box per node so
 * arrows always meet a flat top/bottom edge. Split vs. join is conveyed by
 * how many edges fan in/out of a connector, the standard EPK convention, not
 * a second icon.
 *
 * When `editable`, every node is a focusable, draggable canvas item: pointer
 * drag *or* arrow keys (Shift = ×4 grid) move it, writing the position to
 * `node.props.x`/`node.props.y` (an already-open schema field — no backend
 * change). `Delete`/`Backspace` removes the focused node via the `remove-node`
 * emit, so the parent's single `removeNode()` stays the one place edges/`start`
 * get cleaned up too. A node without a stored position falls back to the
 * auto-layout, so a fresh graph looks laid out with no manual work.
 *
 * Per-step moves (drag, keyboard nudge) are instant — no transition — so
 * repeated nudging stays snappy and immediately measurable. The "Auto-Layout"
 * bulk reflow is the one case worth animating; the parent triggers it via
 * `pulseTransition()` (exposed), which arms a transition for one tick and
 * disarms itself, rather than a standing transition every position write
 * would otherwise re-trigger.
 *
 * Colour is never the only signal (shape + label + glyph carry it), so the
 * neutral surface tones stay reserved for real alarm priorities elsewhere in
 * the app.
 *
 * `role="button"` on each node is the closest ARIA widget role for "a
 * focusable, keyboard-movable canvas item" — `eslint-plugin-vuejs-accessibility`
 * only allows an interactive handler on a role from the ARIA "widget"
 * superclass, which a purely structural `role="group"` is not. Enter/Space
 * intentionally stay no-ops: a node has no single "activate" action, only
 * position (arrows) and removal (Delete).
 */
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { prefersReducedMotion } from '@/a11y/reducedMotion';
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
  CANVAS_PADDING,
  type WfGraph,
  type WfNode,
} from '@/lib/workflows';

const props = defineProps<{ graph: WfGraph; editable: boolean }>();
const emit = defineEmits<{ 'remove-node': [key: string] }>();

const { t } = useI18n();

const svgEl = ref<SVGSVGElement | null>(null);
const focusedKey = ref<string | null>(null);
const draggingKey = ref<string | null>(null);
const reduced = prefersReducedMotion();

const animating = ref(false);
let animTimer: ReturnType<typeof setTimeout> | null = null;
/** Arms a brief transition for the next reflow (the "Auto-Layout" button),
 *  then disarms it — so it never lingers to catch a later per-step move. */
function pulseTransition(): void {
  if (reduced) return;
  animating.value = true;
  if (animTimer) clearTimeout(animTimer);
  animTimer = setTimeout(() => {
    animating.value = false;
  }, 220);
}
defineExpose({ pulseTransition });

const auto = computed(() => layoutRows(props.graph));
const positions = computed(() => {
  const map = new Map<string, { x: number; y: number }>();
  for (const n of props.graph.nodes) map.set(n.key, nodePos(n, auto.value));
  return map;
});
const posOf = (key: string): { x: number; y: number } =>
  positions.value.get(key) ?? { x: CANVAS_PADDING, y: CANVAS_PADDING };

const viewBox = computed(() => {
  let maxX = 0;
  let maxY = 0;
  for (const p of positions.value.values()) {
    maxX = Math.max(maxX, p.x + NODE_W);
    maxY = Math.max(maxY, p.y + NODE_H);
  }
  return { w: maxX + CANVAS_PADDING, h: maxY + CANVAS_PADDING };
});

const HEX_NOTCH = 20;
const CONNECTOR_R = 22;
/** Elongated hexagon: flat top/bottom edges (arrow anchors), pointed left/right
 *  — the classic EPK event shape — in the node's own local coordinates. */
const hexPoints = `${HEX_NOTCH},0 ${NODE_W - HEX_NOTCH},0 ${NODE_W},${NODE_H / 2} ${
  NODE_W - HEX_NOTCH
},${NODE_H} ${HEX_NOTCH},${NODE_H} 0,${NODE_H / 2}`;

function transformFor(key: string): string {
  const p = posOf(key);
  return `translate(${p.x}px, ${p.y}px)`;
}

function ariaLabel(n: WfNode): string {
  if (n.type === 'connector') {
    const kind = t(`wf.connectorAria.${n.connector ?? 'and'}`);
    const dir = n.direction === 'join' ? t('wf.join') : t('wf.split');
    return `${kind} (${dir})`;
  }
  return t('wf.nodeAria', { type: t('wf.type.' + n.type), label: n.label || n.key });
}

function edgePath(fromKey: string, toKey: string): string {
  const a = anchorFor(posOf(fromKey), 'out');
  const b = anchorFor(posOf(toKey), 'in');
  const midY = (a.y + b.y) / 2;
  return `M ${a.x} ${a.y} C ${a.x} ${midY}, ${b.x} ${midY}, ${b.x} ${b.y}`;
}
function edgeMid(fromKey: string, toKey: string): { x: number; y: number } {
  const a = anchorFor(posOf(fromKey), 'out');
  const b = anchorFor(posOf(toKey), 'in');
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

// --- pointer drag ----------------------------------------------------
let dragStart: { key: string; x: number; y: number; pos: { x: number; y: number } } | null = null;

function svgScale(): number {
  const el = svgEl.value;
  const rect = el?.getBoundingClientRect();
  return rect && rect.width > 0 ? viewBox.value.w / rect.width : 1;
}

function onPointerDown(e: PointerEvent, n: WfNode): void {
  if (!props.editable) return;
  (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
  dragStart = { key: n.key, x: e.clientX, y: e.clientY, pos: posOf(n.key) };
  draggingKey.value = n.key;
  e.preventDefault();
}
function onPointerMove(e: PointerEvent): void {
  if (!dragStart) return;
  const n = props.graph.nodes.find((x) => x.key === dragStart!.key);
  if (!n) return;
  const scale = svgScale();
  const dx = (e.clientX - dragStart.x) * scale;
  const dy = (e.clientY - dragStart.y) * scale;
  n.props = {
    ...n.props,
    x: Math.max(0, snap(dragStart.pos.x + dx)),
    y: Math.max(0, snap(dragStart.pos.y + dy)),
  };
}
function onPointerUp(): void {
  // pointer capture is released implicitly on pointerup/pointercancel (Pointer
  // Events spec) — nothing to release explicitly here.
  dragStart = null;
  draggingKey.value = null;
}

// --- keyboard alternative (E07-19 AC: every editor action works without a
// mouse) -----------------------------------------------------------------
function onKeyDown(e: KeyboardEvent, n: WfNode): void {
  if (!props.editable) return;
  const step = e.shiftKey ? GRID * 4 : GRID;
  let dx = 0;
  let dy = 0;
  switch (e.key) {
    case 'ArrowUp':
      dy = -step;
      break;
    case 'ArrowDown':
      dy = step;
      break;
    case 'ArrowLeft':
      dx = -step;
      break;
    case 'ArrowRight':
      dx = step;
      break;
    case 'Delete':
    case 'Backspace':
      e.preventDefault();
      emit('remove-node', n.key);
      return;
    default:
      return;
  }
  e.preventDefault();
  const next = applyNodeDrag(n, dx, dy, auto.value);
  n.props = { ...n.props, x: next.x, y: next.y };
}
</script>

<template>
  <div
    class="wfp"
    :class="{ 'wfp--animating': animating }"
    :role="editable ? undefined : 'img'"
    :aria-label="editable ? t('wf.canvasEditableAlt') : t('wf.previewAlt')"
  >
    <svg
      ref="svgEl"
      :viewBox="`0 0 ${viewBox.w} ${viewBox.h}`"
      :width="viewBox.w"
      :height="viewBox.h"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
    >
      <defs>
        <marker
          id="wf-arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="7"
          markerHeight="7"
          orient="auto-start-reverse"
        >
          <path
            d="M0 0 L10 5 L0 10 z"
            fill="currentColor"
          />
        </marker>
      </defs>

      <g class="wfp__edges">
        <template
          v-for="e in graph.edges"
          :key="e.key"
        >
          <path
            :d="edgePath(e.from, e.to)"
            class="wfp__edge"
            marker-end="url(#wf-arrow)"
          />
          <text
            v-if="e.branch"
            :x="edgeMid(e.from, e.to).x"
            :y="edgeMid(e.from, e.to).y - 4"
            text-anchor="middle"
            class="wfp__branch"
          >{{ e.branch }}</text>
        </template>
      </g>

      <g
        v-for="n in graph.nodes"
        :key="n.key"
        :class="[
          'wfp__node',
          `wfp__node--${n.type}`,
          { 'wfp__node--dragging': draggingKey === n.key, 'wfp__node--focused': focusedKey === n.key },
        ]"
        :style="{ transform: transformFor(n.key) }"
        :tabindex="editable ? 0 : -1"
        role="button"
        :aria-label="ariaLabel(n)"
        @pointerdown="onPointerDown($event, n)"
        @keydown="onKeyDown($event, n)"
        @focus="focusedKey = n.key"
        @blur="focusedKey === n.key && (focusedKey = null)"
      >
        <title>{{ n.label || n.key }}</title>

        <rect
          v-if="focusedKey === n.key"
          x="-4"
          y="-4"
          :width="NODE_W + 8"
          :height="NODE_H + 8"
          rx="12"
          class="wfp__focusring"
        />

        <polygon
          v-if="n.type === 'event'"
          :points="hexPoints"
        />
        <rect
          v-else-if="n.type === 'function'"
          x="0"
          y="0"
          :width="NODE_W"
          :height="NODE_H"
          rx="10"
        />
        <circle
          v-else
          :cx="NODE_W / 2"
          :cy="NODE_H / 2"
          :r="CONNECTOR_R"
        />

        <text
          v-if="n.type === 'connector'"
          :x="NODE_W / 2"
          :y="NODE_H / 2 + 7"
          text-anchor="middle"
          class="wfp__glyph"
        >{{ CONNECTOR_GLYPH[n.connector ?? 'and'] }}</text>
        <text
          v-if="n.type === 'connector' && n.label"
          :x="NODE_W / 2"
          :y="NODE_H + 14"
          text-anchor="middle"
          class="wfp__label wfp__label--below"
        >{{ n.label }}</text>
        <text
          v-else-if="n.type !== 'connector'"
          :x="NODE_W / 2"
          :y="NODE_H / 2 + 4"
          text-anchor="middle"
          class="wfp__label"
        >{{ n.label || n.key }}</text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.wfp {
  overflow-x: auto;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-surface);
  padding: 0.5rem;
  margin-bottom: 0.75rem;
}
.wfp__edge {
  fill: none;
  stroke: var(--bbz-text-muted);
  stroke-width: 1.5;
}
.wfp__branch {
  fill: var(--bbz-text-muted);
  font-size: 10px;
}
.wfp__node {
  cursor: default;
  outline: none;
}
/* Only the Auto-Layout bulk reflow animates (armed briefly via
   `pulseTransition()`); per-step drag/keyboard moves stay instant so they
   are immediately measurable and feel snappy under repeat nudging. */
.wfp--animating .wfp__node {
  transition: transform 0.18s ease;
}
.wfp__node--dragging {
  transition: none;
}
.wfp__node[tabindex='0'] {
  cursor: grab;
  touch-action: none;
}
.wfp__node--dragging {
  cursor: grabbing;
}
.wfp__node polygon,
.wfp__node rect:not(.wfp__focusring),
.wfp__node circle {
  fill: var(--bbz-surface);
  stroke: var(--bbz-border-strong);
  stroke-width: 1.5;
}
.wfp__node--function rect:not(.wfp__focusring) {
  fill: var(--bbz-surface-alt);
}
.wfp__node--connector circle {
  fill: var(--bbz-surface-alt);
}
.wfp__focusring {
  fill: none;
  stroke: var(--bbz-focus-color);
  stroke-width: var(--bbz-focus-width);
}
.wfp__glyph {
  fill: var(--bbz-text);
  font-size: 20px;
  font-weight: 600;
}
.wfp__label {
  fill: var(--bbz-text);
  font-size: 12px;
}
.wfp__label--below {
  fill: var(--bbz-text-muted);
  font-size: 10px;
}
</style>
